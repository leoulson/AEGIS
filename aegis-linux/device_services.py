"""Offline device services. No elevated commands, patient content in diagnostics or hooks."""
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import sqlite3
import stat
import tempfile
import threading
import time
import uuid
import zipfile

from updater import (APP_ID, UpdateError, atomic_json, canonical, file_hash,
                     parse_json, public_id, sync_dir, verify_signature, version)

TOOLS = ['calculator', 'updates', 'diagnostics', 'collection', 'backups', 'accessibility', 'recovery']
DEFAULT_SHORTCUTS = ['calculator', 'diagnostics', 'collection']
DEFAULTS = {'format': 1, 'text_size': 100, 'high_contrast': False, 'reduced_motion': False,
            'shortcuts': DEFAULT_SHORTCUTS}
BACKUP_LIMIT = 128 * 1024 * 1024
EXPANDED_LIMIT = 256 * 1024 * 1024
MAX_FILES = 4096
RESERVE = 16 * 1024 * 1024
DATA_FILES = {'library.sqlite3', 'preferences.json', 'favorites.json', 'annotations.json',
              'settings.json', 'history.json'}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


@contextlib.contextmanager
def data_lock(root, shared=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.data.lock').open('a') as fd:
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UpdateError('Dados em uso por outra operação. Aguarde e tente novamente.') from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


def relative(name):
    if (not isinstance(name, str) or not name or len(name) > 240 or '\\' in name or ':' in name or
            any(ord(c) < 32 for c in name) or PurePosixPath(name).is_absolute() or
            any(p in ('', '.', '..') for p in name.split('/'))):
        raise UpdateError('Caminho não permitido.')
    return name


def data_name(name):
    relative(name)
    if name not in DATA_FILES and not name.startswith('personal/'):
        raise UpdateError('Arquivo fora do alcance permitido para dados pessoais.')
    if name.endswith(('-wal', '-shm', '-journal')):
        raise UpdateError('Arquivos auxiliares SQLite não são backups consistentes.')
    return name


def regular(root, name):
    relative(name)
    root = Path(root).resolve()
    p = root
    for part in name.split('/'):
        p = p / part
        if p.is_symlink():
            raise UpdateError('Links não são permitidos.')
    if not p.resolve().is_relative_to(root):
        raise UpdateError('Caminho fora do diretório permitido.')
    return p


def digest(path, cancel=None, progress=lambda n: None):
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise UpdateError('Arquivo não regular.')
    h = hashlib.sha256()
    with path.open('rb') as src:
        opened = os.fstat(src.fileno())
        for block in iter(lambda: src.read(65536), b''):
            if cancel is not None and cancel.is_set():
                raise InterruptedError('Verificação cancelada.')
            h.update(block)
            progress(len(block))
        end = os.fstat(src.fileno())
    after = path.stat()
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if not stamp(before) == stamp(opened) == stamp(end) == stamp(after):
        raise UpdateError('Arquivo alterado durante a leitura.')
    return h.hexdigest(), after.st_size


def validate_preferences(value):
    if not isinstance(value, dict):
        raise UpdateError('Configuração inválida.')
    # The only migration supported is the documented local prototype format 0.
    if type(value.get('format')) is int and value.get('format') == 0:
        value = dict(DEFAULTS, **{k: v for k, v in value.items() if k in DEFAULTS and k != 'format'})
    if type(value.get('format')) is not int or value.get('format') != 1 or set(value) != set(DEFAULTS):
        raise UpdateError('Formato de configuração incompatível.')
    if type(value['text_size']) is not int or value['text_size'] not in (100, 125, 150, 200):
        raise UpdateError('Tamanho de texto inválido.')
    if any(type(value[k]) is not bool for k in ('high_contrast', 'reduced_motion')):
        raise UpdateError('Preferência de acessibilidade inválida.')
    shortcuts = value['shortcuts']
    if not isinstance(shortcuts, list) or len(shortcuts) > 32 or not all(isinstance(k, str) for k in shortcuts):
        raise UpdateError('Lista de atalhos inválida.')
    result = dict(value)
    result['shortcuts'] = list(dict.fromkeys(k for k in shortcuts if k in TOOLS))
    return result


class Services:
    def __init__(self, manager, data=None):
        self.manager = manager
        self.data = Path(data) if data is not None else manager.home.parent / 'aegis'
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.packages = self.data / 'packages'
        self.prefs = self.data / 'preferences.json'
        self.cancel = threading.Event()
        self.verification = None
        self.diagnostic = None
        self.diagnostic_time = 0
        self.backup_candidate = None
        self.backup_download = None
        self.journal = manager.home / 'restore-journal.json'
        self.recovery_reason = ''
        self.events = manager.home / 'technical-events.json'

    def event(self, code):
        try:
            with data_lock(self.manager.home):
                self._event(code)
        except (OSError, UpdateError):
            self.recovery_reason = self.recovery_reason or 'Registro técnico indisponível; o diagnóstico ainda pode ser consultado.'

    def _event(self, code):
        # Strict enumerated messages: no raw exception, path, user text or environment dump.
        allowed = {'configuration_reset', 'verification_completed', 'verification_interrupted',
                   'backup_created', 'restore_started', 'restore_completed', 'restore_resumed',
                   'startup_started', 'startup_ready', 'startup_failed', 'normal_exit', 'recovery_opened'}
        if code not in allowed:
            return
        # All callers serialize through an operation or application lock.
        try:
            old = parse_json(self.events.read_bytes()) if self.events.exists() else []
            if not isinstance(old, list):
                old = []
        except (OSError, UpdateError):
            old = []
        atomic_json(self.events, (old + [{'at': now(), 'code': code}])[-100:])

    def logs(self):
        try:
            entries = parse_json(self.events.read_bytes())
            return [{k: e[k] for k in ('at', 'code')} for e in entries if set(e) == {'at', 'code'}][-100:]
        except (OSError, UpdateError, TypeError, AttributeError, KeyError):
            return []

    def preferences(self, value=None):
        with data_lock(self.data):
            if value is not None:
                normalized = validate_preferences(value)
                atomic_json(self.prefs, normalized)
                os.chmod(self.prefs, 0o600)
                return normalized
            if not self.prefs.exists():
                return dict(DEFAULTS, shortcuts=list(DEFAULT_SHORTCUTS))
            try:
                if self.prefs.stat().st_size > 65536:
                    raise UpdateError('Configuração acima do limite.')
                raw = parse_json(self.prefs.read_bytes())
                normalized = validate_preferences(raw)
                if raw != normalized:
                    atomic_json(self.prefs, normalized)
                    self.recovery_reason = 'Preferências migradas; atalhos duplicados ou de ferramentas indisponíveis foram removidos.'
                return normalized
            except (UpdateError, ValueError, TypeError):
                # Preserve an unusable file rather than silently overwriting user choices.
                os.replace(self.prefs, self.data / ('preferences.problem-' + uuid.uuid4().hex + '.json'))
                sync_dir(self.data)
                self.event('configuration_reset')
                self.recovery_reason = 'Preferências inválidas preservadas em cópia local; padrões carregados.'
                return dict(DEFAULTS, shortcuts=list(DEFAULT_SHORTCUTS))

    def package_dirs(self):
        if not self.packages.exists():
            return []
        if self.packages.is_symlink():
            raise UpdateError('A pasta de pacotes não pode ser um link.')
        return sorted(self.packages.iterdir())

    def manifest(self, directory):
        path = regular(directory, 'manifest.json')
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise UpdateError('Sem manifesto verificável.')
        m = parse_json(path.read_bytes())
        required = {'format', 'package_id', 'version', 'files'}
        if not isinstance(m, dict) or not required <= set(m) or set(m) - required - {'key_id'} or type(m['format']) is not int or m['format'] != 1:
            raise UpdateError('Manifesto incompatível.')
        if not isinstance(m['package_id'], str) or not re.fullmatch('[a-zA-Z0-9._-]{1,80}', m['package_id']):
            raise UpdateError('Identificador de pacote inválido.')
        version(m['version'])
        if not isinstance(m['files'], dict) or len(m['files']) > MAX_FILES or not m['files']:
            raise UpdateError('Lista de arquivos inválida.')
        for name, info in m['files'].items():
            relative(name)
            if name in ('manifest.json', 'manifest.sig') or not isinstance(info, dict) or set(info) != {'size', 'sha256'} or type(info['size']) is not int or info['size'] < 0 or not re.fullmatch('[a-f0-9]{64}', str(info['sha256'])):
                raise UpdateError('Entrada inválida no manifesto.')
        return m

    def authenticity(self, directory, manifest):
        sig = directory / 'manifest.sig'
        if not sig.exists():
            return 'Não assinada; autenticidade não verificada'
        kid = manifest.get('key_id', '')
        if not isinstance(kid, str) or not re.fullmatch('[a-f0-9]{64}', kid):
            return 'Assinatura inválida'
        key = self.manager.trust / (kid + '.pem')
        try:
            if not key.is_file() or public_id(key) != kid:
                return 'Chave desconhecida; autenticidade não verificada'
        except OSError:
            return 'Chave indisponível; autenticidade não verificada'
        try:
            if sig.is_symlink() or sig.stat().st_size > 1024:
                return 'Assinatura inválida'
            verify_signature((directory / 'manifest.json').read_bytes(), sig.read_bytes(), key, self.manager.home)
            return 'Assinatura verificada com chave previamente confiável'
        except (OSError, UpdateError):
            return 'Assinatura inválida'

    def verify_collection(self, progress=lambda text, n: None, reset_cancel=True):
        if reset_cancel:
            self.cancel.clear()
        result = {'at': now(), 'complete': False, 'packages': [], 'summary': {},
                  'guidance': 'Não há reinstalador de pacotes do acervo nesta versão. Obtenha novamente o pacote original e seu manifesto por canal confiável. Preserve documentos pessoais e solicite a substituição ao responsável; nenhum arquivo foi apagado ou reparado.'}
        with data_lock(self.data):
            directories = self.package_dirs()
            for index, directory in enumerate(directories):
                if self.cancel.is_set():
                    break
                package = {'id': directory.name, 'integrity': 'unverifiable', 'authenticity': 'Não verificada', 'files': [], 'reinstall': False}
                result['packages'].append(package)
                try:
                    if directory.is_symlink() or not directory.is_dir():
                        raise UpdateError('Pacote não é um diretório regular.')
                    manifest = self.manifest(directory)
                    reference_hash = file_hash(directory / 'manifest.json')
                    package['id'] = manifest['package_id']
                    package['authenticity'] = self.authenticity(directory, manifest)
                except (OSError, UpdateError):
                    package['reason'] = 'Pacote sem manifesto verificável; integridade anterior desconhecida.'
                    continue
                package['integrity'] = 'intact'
                expected = manifest['files']
                checked = {}
                for number, (name, info) in enumerate(expected.items()):
                    if self.cancel.is_set():
                        package['integrity'] = 'incomplete'
                        break
                    progress('Verificando pacote %d de %d, arquivo %d de %d…' % (index + 1, len(directories), number + 1, len(expected)), int((index + number / len(expected)) / max(1, len(directories)) * 95))
                    status = 'intact'
                    try:
                        path = regular(directory, name)
                        hashed, size = digest(path, self.cancel)
                        check_stat = path.stat()
                        checked[name] = (check_stat.st_ino, check_stat.st_size, check_stat.st_mtime_ns, check_stat.st_ctime_ns)
                        if size != info['size'] or hashed != info['sha256']:
                            status = 'divergent'
                    except FileNotFoundError:
                        status = 'missing'
                    except InterruptedError:
                        status = 'incomplete'
                    except UpdateError:
                        status = 'changed_or_unsafe'
                    except OSError:
                        status = 'unreadable'
                    package['files'].append({'path': name, 'status': status})
                    if status != 'intact':
                        package['integrity'] = 'incomplete' if status == 'incomplete' else 'damaged'
                        package['reinstall'] = status != 'incomplete'
                    if self.cancel.is_set():
                        package['integrity'] = 'incomplete'
                        break
                try:
                    actual = set()
                    for base, dirs, files in os.walk(directory, followlinks=False, onerror=lambda _: (_ for _ in ()).throw(OSError())):
                        if self.cancel.is_set():
                            package['integrity'] = 'incomplete'
                            break
                        for d in dirs:
                            if (Path(base) / d).is_symlink():
                                raise UpdateError('Diretório link não permitido.')
                        for f in files:
                            actual.add((Path(base) / f).relative_to(directory).as_posix())
                            if len(actual) > MAX_FILES + 2:
                                raise UpdateError('Arquivos demais.')
                    for extra in sorted(actual - set(expected) - {'manifest.json', 'manifest.sig'}):
                        package['files'].append({'path': extra, 'status': 'unexpected'})
                        package['integrity'], package['reinstall'] = 'damaged', True
                    for name, before in checked.items():
                        after = regular(directory, name).stat()
                        if before != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                            package['integrity'] = 'incomplete'
                            for entry in package['files']:
                                if entry['path'] == name:
                                    entry['status'] = 'changed_or_unsafe'
                    if reference_hash != file_hash(directory / 'manifest.json'):
                        package['integrity'] = 'incomplete'
                except (OSError, UpdateError):
                    package['integrity'] = 'incomplete'
            # Existing SQLite has no publisher-supplied manifest. Never manufacture a baseline.
            if (self.data / 'library.sqlite3').exists():
                result['packages'].append({'id': 'biblioteca-sqlite-existente', 'integrity': 'unverifiable',
                    'authenticity': 'Não verificada', 'files': [], 'reinstall': False,
                    'reason': 'Banco existente sem manifesto de origem; não equivale a pacote íntegro.'})
            result['complete'] = not self.cancel.is_set() and all(p['integrity'] != 'incomplete' for p in result['packages'])
            for p in result['packages']:
                key = p['integrity']
                result['summary'][key] = result['summary'].get(key, 0) + 1
            if self.cancel.is_set():
                result['summary']['interrupted'] = 1
            atomic_json(self.data / 'integrity-result.json', result)
        self.verification = result
        self.event('verification_completed' if result['complete'] else 'verification_interrupted')
        return result

    def read_text(self, path):
        try:
            return Path(path).read_text(errors='replace').strip('\x00\n ')
        except OSError:
            return None

    def diagnostics(self, proc=Path('/proc'), sys=Path('/sys'), etc=Path('/etc'), force=False):
        if self.diagnostic is not None and not force and time.monotonic() - self.diagnostic_time < 15:
            return self.diagnostic
        model = self.read_text(proc / 'device-tree/model') or self.read_text(sys / 'firmware/devicetree/base/model')
        os_name = None
        raw = self.read_text(etc / 'os-release')
        if raw:
            for line in raw.splitlines():
                if line.startswith('PRETTY_NAME='):
                    os_name = line.partition('=')[2].strip('"')
        memory = {}
        for line in (self.read_text(proc / 'meminfo') or '').splitlines():
            match = re.fullmatch(r'(MemTotal|MemAvailable):\s+(\d+) kB', line)
            if match:
                memory[match[1]] = int(match[2]) * 1024
        temperature = None
        for zone in sorted((sys / 'class/thermal').glob('thermal_zone*')):
            if (self.read_text(zone / 'type') or '').lower() in {'cpu-thermal', 'cpu_thermal', 'bcm2835_thermal', 'x86_pkg_temp', 'soc_thermal'}:
                try:
                    t = int(self.read_text(zone / 'temp')) / 1000
                    if -20 <= t <= 150:
                        temperature = t
                        break
                except (ValueError, TypeError):
                    pass
        try:
            disk = shutil.disk_usage(self.data)
            storage = {'total': disk.total, 'used': disk.used, 'available': disk.free}
        except OSError:
            storage = None
        installed = None
        app_ok = False
        try:
            state = self.manager.state()
            installed = self.manager.info(state['current'])['version']
            # Presence is a basic component observation, not an integrity claim.
            app_ok = (self.manager.slot(state['current']) / 'app/index.html').is_file()
        except (OSError, UpdateError, KeyError, TypeError):
            pass
        last = None
        try:
            raw = parse_json((self.data / 'integrity-result.json').read_bytes())
            dt.datetime.fromisoformat(raw['at'])
            last = {'at': raw['at'], 'complete': raw['complete'] is True,
                    'summary': {k: v for k, v in raw['summary'].items() if k in
                                {'intact', 'damaged', 'unverifiable', 'incomplete', 'interrupted'} and type(v) is int and v >= 0}}
        except (OSError, UpdateError, KeyError, TypeError, ValueError, AttributeError):
            pass
        package_count, documents = None, None
        try:
            package_count = len(self.package_dirs())
            documents = 0
            for directory in self.package_dirs():
                if directory.is_dir() and not directory.is_symlink():
                    for base, dirs, files in os.walk(directory, followlinks=False):
                        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
                        documents += len([f for f in files if f not in ('manifest.json', 'manifest.sig')])
                        if documents > MAX_FILES * 100:
                            raise OSError('Inventory limit')
            db = self.data / 'library.sqlite3'
            if db.is_file():
                with contextlib.closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=1)) as connection:
                    documents += connection.execute('SELECT count(*) FROM documents').fetchone()[0]
        except (OSError, sqlite3.Error, UpdateError):
            documents = None
        result = {'format': 1, 'updated_at': now(), 'model': model, 'architecture': platform.machine(),
                  'aegis_version': installed, 'os': os_name, 'storage': storage,
                  'memory': {'total': memory.get('MemTotal'), 'available': memory.get('MemAvailable')},
                  'cpu_temperature_c': temperature, 'packages': package_count, 'documents': documents,
                  'last_verification': last, 'components': {'python': platform.python_version(),
                  'sqlite': sqlite3.sqlite_version, 'openssl': bool(shutil.which('openssl')),
                  'browser': any(shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable')),
                  'interface_file_present': app_ok, 'restore_pending': self.journal.exists()}}
        self.diagnostic, self.diagnostic_time = result, time.monotonic()
        return result

    def space(self, size):
        if shutil.disk_usage(self.data).free < size + RESERVE or shutil.disk_usage(self.manager.home).free < size + RESERVE:
            raise UpdateError('Espaço insuficiente; é necessária uma cópia de segurança antes de restaurar.')

    def data_paths(self):
        paths = [self.data / name for name in sorted(DATA_FILES) if (self.data / name).exists()]
        personal = self.data / 'personal'
        if personal.is_symlink():
            raise UpdateError('Links não são permitidos nos dados de backup.')
        if personal.exists():
            for base, dirs, files in os.walk(personal, followlinks=False):
                if any((Path(base) / d).is_symlink() for d in dirs):
                    raise UpdateError('Links não são permitidos nos dados de backup.')
                paths.extend(Path(base) / f for f in files)
                if len(paths) > MAX_FILES:
                    raise UpdateError('Backup acima do limite de arquivos.')
        return paths

    def snapshot(self, destination, app_version, progress=lambda text, n: None):
        # Caller owns data_lock. No files outside this explicit allowlist enter the backup.
        if sum(p.stat().st_size for p in self.data_paths()) > EXPANDED_LIMIT:
            raise UpdateError('Dados acima do limite de 256 MiB para este formato de backup.')
        self.space(sum(p.stat().st_size for p in self.data_paths()) * 3)
        with tempfile.TemporaryDirectory(prefix='snapshot-', dir=self.manager.home) as tmp:
            stage = Path(tmp)
            entries, total = {}, 0
            for index, p in enumerate(self.data_paths()):
                name = data_name(p.relative_to(self.data).as_posix())
                regular(self.data, name)
                out = stage / name
                out.parent.mkdir(parents=True, exist_ok=True)
                if name == 'library.sqlite3':
                    with contextlib.closing(sqlite3.connect(p.as_uri() + '?mode=ro', uri=True, timeout=2)) as src, contextlib.closing(sqlite3.connect(out)) as dest:
                        started = time.monotonic()
                        def backup_progress(status, remaining, total):
                            if total * 4096 > EXPANDED_LIMIT or time.monotonic() - started > 120:
                                raise UpdateError('Snapshot SQLite excedeu o limite de tamanho ou tempo; feche outros escritores e tente novamente.')
                        src.backup(dest, pages=64, progress=backup_progress, sleep=.01)
                        if dest.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                            raise UpdateError('Banco de dados inconsistente.')
                else:
                    first, _ = digest(p)
                    shutil.copyfile(p, out)
                    if digest(p)[0] != first or file_hash(out) != first:
                        raise UpdateError('Dados alterados durante o backup. Tente novamente.')
                size = out.stat().st_size
                total += size
                if total > EXPANDED_LIMIT:
                    raise UpdateError('Backup acima do limite expandido de 256 MiB.')
                entries[name] = {'sha256': file_hash(out), 'size': size}
                progress('Criando snapshot consistente…', min(90, index * 5))
            manifest = {'app_id': APP_ID, 'format': 1, 'data_format': 1, 'app_version': app_version,
                        'created_at': now(), 'origin': 'AEGIS — backup local de dados',
                        'scope': 'user-data-v1', 'files': entries}
            created = False
            try:
                with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                    created = True
                    archive.writestr('manifest.json', canonical(manifest))
                    for name in entries:
                        archive.write(stage / name, name)
                if destination.stat().st_size > BACKUP_LIMIT:
                    destination.unlink()
                    raise UpdateError('Backup acima do limite de 128 MiB.')
                with destination.open('rb') as fd:
                    os.fsync(fd.fileno())
                os.chmod(destination, 0o600)
                sync_dir(destination.parent)
            except BaseException:
                if created:
                    destination.unlink(missing_ok=True)
                raise
        return manifest

    def create_backup(self, destination, app_version, progress=lambda text, n: None):
        self.backup_download = None
        with data_lock(self.data):
            if self.journal.exists():
                raise UpdateError('Há uma restauração incompleta; use o modo de recuperação.')
            manifest = self.snapshot(destination, app_version, progress)
        self.backup_download = destination
        self.event('backup_created')
        return manifest

    def inspect_backup(self, path, installed):
        try:
            if not 0 < path.stat().st_size <= BACKUP_LIMIT:
                raise UpdateError('Backup vazio ou acima de 128 MiB.')
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                names = [i.filename for i in infos]
                if len(infos) > MAX_FILES + 1 or len(names) != len(set(names)) or sum(i.file_size for i in infos) > EXPANDED_LIMIT:
                    raise UpdateError('Backup duplicado ou expansão excessiva.')
                for info in infos:
                    if (info.is_dir() or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG) or
                            info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                        raise UpdateError('Links ou entradas especiais não são permitidos.')
                    if info.filename != 'manifest.json':
                        data_name(info.filename)
                if archive.getinfo('manifest.json').file_size > 2 * 1024 * 1024:
                    raise UpdateError('Manifesto de backup acima do limite.')
                m = parse_json(archive.read('manifest.json'))
                fields = {'app_id', 'format', 'data_format', 'app_version', 'created_at', 'origin', 'scope', 'files'}
                if not isinstance(m, dict) or set(m) != fields or m['app_id'] != APP_ID or type(m['format']) is not int or m['format'] != 1 or type(m['data_format']) is not int or m['data_format'] != 1 or m['scope'] != 'user-data-v1':
                    raise UpdateError('Backup incompatível.')
                if version(m['app_version'])[0] != version(installed)[0]:
                    raise UpdateError('Versão principal do aplicativo incompatível com o backup.')
                dt.datetime.fromisoformat(m['created_at'])
                if not isinstance(m['origin'], str) or len(m['origin']) > 160 or not isinstance(m['files'], dict) or set(names) != set(m['files']) | {'manifest.json'}:
                    raise UpdateError('Manifesto do backup inválido.')
                for name, expected in m['files'].items():
                    data_name(name)
                    if not isinstance(expected, dict) or set(expected) != {'size', 'sha256'} or type(expected['size']) is not int or expected['size'] < 0 or not re.fullmatch('[a-f0-9]{64}', str(expected['sha256'])):
                        raise UpdateError('Hash/tamanho inválido no backup.')
                    if archive.getinfo(name).file_size != expected['size']:
                        raise UpdateError('Tamanho divergente no backup.')
                    h = hashlib.sha256()
                    with archive.open(name) as src:
                        for chunk in iter(lambda: src.read(65536), b''):
                            h.update(chunk)
                    if h.hexdigest() != expected['sha256']:
                        raise UpdateError('Hash divergente no backup.')
                return m
        except (OSError, zipfile.BadZipFile, ValueError, KeyError, TypeError, EOFError) as exc:
            if isinstance(exc, UpdateError):
                raise
            raise UpdateError('Backup inválido, truncado ou incompatível.') from exc

    def validate_data(self, stage, files):
        for name, info in files.items():
            path = regular(stage, data_name(name))
            if digest(path) != (info['sha256'], info['size']):
                raise UpdateError('Falha de integridade na preparação da restauração.')
            if name == 'preferences.json':
                if path.stat().st_size > 65536:
                    raise UpdateError('Preferências do backup acima do limite.')
                validate_preferences(parse_json(path.read_bytes()))
            elif name.endswith('.json') and name in DATA_FILES:
                if path.stat().st_size > 2 * 1024 * 1024:
                    raise UpdateError('Configuração JSON do backup acima de 2 MiB.')
                parse_json(path.read_bytes())  # Data only; never imported as Python/JS/config code.
            elif name == 'library.sqlite3':
                with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
                    db.execute('PRAGMA trusted_schema=OFF')
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise UpdateError('SQLite do backup não é consistente.')

    def restore_backup(self, path, installed, progress=lambda text, n: None):
        with data_lock(self.data):
            if self.journal.exists():
                raise UpdateError('Retome primeiro a restauração interrompida.')
            m = self.inspect_backup(path, installed)
            self.space(sum(i['size'] for i in m['files'].values()) * 2 + sum(p.stat().st_size for p in self.data_paths()) * 3)
            for suffix in ('-wal', '-shm', '-journal'):
                if (self.data / ('library.sqlite3' + suffix)).exists():
                    raise UpdateError('SQLite em uso ou com journal pendente. Feche os outros programas antes de restaurar.')
            for name in m['files']:
                target = regular(self.data, data_name(name))
                if target.exists() and not target.is_file():
                    raise UpdateError('Um destino do backup não é um arquivo regular. Nenhum dado foi substituído.')
                for parent in target.parents:
                    if parent == self.data:
                        break
                    if parent.exists() and not parent.is_dir():
                        raise UpdateError('Pasta de destino incompatível. Nenhum dado foi substituído.')
            work_id = uuid.uuid4().hex
            stage = self.manager.home / ('restore-' + work_id)
            stage.mkdir(mode=0o700)
            try:
                with zipfile.ZipFile(path) as archive:
                    for name in m['files']:
                        out = stage / data_name(name)
                        out.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(name) as src, out.open('xb') as dest:
                            shutil.copyfileobj(src, dest, 65536)
                self.validate_data(stage, m['files'])
                self.manager.sync_tree(stage)
                backups = self.manager.home / 'safety-backups'
                backups.mkdir(exist_ok=True, mode=0o700)
                safety = backups / (work_id + '.aegis-backup')
                self.snapshot(safety, installed, progress)
                journal = {'format': 1, 'stage': work_id, 'files': m['files'], 'safety': safety.name}
                atomic_json(self.journal, journal)
                self.event('restore_started')
                self.apply_journal(journal, progress)
            except BaseException:
                if not self.journal.exists():
                    shutil.rmtree(stage, ignore_errors=True)
                raise
        self.event('restore_completed')
        return {'message': 'Dados restaurados. A cópia anterior foi preservada em safety-backups.', 'safety_backup': safety.name}

    def apply_journal(self, journal, progress=lambda text, n: None):
        if (not isinstance(journal, dict) or set(journal) != {'format', 'stage', 'files', 'safety'} or
                type(journal.get('format')) is not int or journal['format'] != 1 or
                not isinstance(journal.get('stage'), str) or not re.fullmatch('[a-f0-9]{32}', journal['stage']) or
                not isinstance(journal['files'], dict) or len(journal['files']) > MAX_FILES):
            raise UpdateError('Registro de recuperação inválido; mantenha os arquivos e consulte o responsável.')
        stage = self.manager.home / ('restore-' + journal['stage'])
        if stage.is_symlink() or not stage.is_dir():
            raise UpdateError('Preparação da restauração indisponível; preserve o backup de segurança.')
        for name, info in journal['files'].items():
            data_name(name)
            if not isinstance(info, dict) or set(info) != {'size', 'sha256'} or type(info['size']) is not int or info['size'] < 0 or not re.fullmatch('[a-f0-9]{64}', str(info['sha256'])):
                raise UpdateError('Registro de restauração corrompido.')
        self.validate_data(stage, journal['files'])
        self.space(sum(info['size'] for info in journal['files'].values()))
        for index, name in enumerate(journal['files']):
            source = regular(stage, data_name(name))
            destination = regular(self.data, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name('.restore-' + uuid.uuid4().hex)
            try:
                with source.open('rb') as src, temp.open('xb') as out:
                    shutil.copyfileobj(src, out, 65536)
                    out.flush()
                    os.fsync(out.fileno())
                os.chmod(temp, 0o600)
                os.replace(temp, destination)
                sync_dir(destination.parent)
            finally:
                temp.unlink(missing_ok=True)
            progress('Restaurando dados com cópia de segurança…', int((index + 1) / max(1, len(journal['files'])) * 95))
        self.journal.unlink()
        sync_dir(self.manager.home)
        shutil.rmtree(stage)

    def resume_restore(self):
        if not self.journal.exists():
            return False
        with data_lock(self.data):
            self.apply_journal(parse_json(self.journal.read_bytes()))
        self.event('restore_resumed')
        return True


class LaunchHistory:
    """Small durable lifecycle record; a normal browser close never increments failures."""
    def __init__(self, home):
        self.path = Path(home) / 'launch-status.json'
        try:
            self.state = parse_json(self.path.read_bytes()) if self.path.exists() else {}
            if (not isinstance(self.state, dict) or self.state.get('format', 1) != 1 or
                    any(type(self.state.get(k, False)) is not bool for k in ('running', 'ready')) or
                    type(self.state.get('failures', 0)) is not int or self.state.get('failures', 0) < 0 or
                    not isinstance(self.state.get('reason', ''), str)):
                raise UpdateError('Registro de inicialização inválido.')
        except (OSError, UpdateError):
            self.state = {'reason': 'Registro de inicialização indisponível.'}
        self.state = dict({'format': 1, 'running': False, 'ready': False, 'failures': 0, 'reason': ''}, **self.state)

    def needs_recovery(self):
        return self.state['running'] or self.state['failures'] >= 2

    def begin(self):
        self.state.update(running=True, ready=False)
        atomic_json(self.path, self.state)

    def ready(self):
        self.state['ready'] = True
        atomic_json(self.path, self.state)

    def end(self, normal):
        self.state.update(running=False, failures=0 if normal else self.state['failures'] + 1,
                          reason='' if normal else 'A interface não confirmou uma inicialização saudável ou encerrou com erro.')
        atomic_json(self.path, self.state)

    def acknowledge(self):
        self.state.update(running=False, failures=0, reason='')
        atomic_json(self.path, self.state)
