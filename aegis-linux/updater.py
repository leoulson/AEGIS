"""AEGIS signed application payloads. Standard library + OpenSSL; no package hooks."""
import contextlib
import datetime
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

APP_ID = 'org.aegis.offline'
UPDATER_VERSION = '1.1.0'
MAX_PACKAGE = 48 * 1024 * 1024
MAX_EXPANDED = 96 * 1024 * 1024
MAX_FILES = 512
MAX_MANIFEST = 256 * 1024
RESERVE = 16 * 1024 * 1024
RELEASE_API = 'https://api.github.com/repos/leoulson/AEGIS/releases/latest'
REQUIRED = {'app/index.html', 'app/medication-core.js', 'app/medication-ui.js',
            'app/updates.js', 'app/updates.css', 'app/medication.css',
            'app/vendor/icons.js', 'app/vendor/LICENSE-lucide'}


class UpdateError(RuntimeError):
    pass


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise UpdateError('Versão inválida: use MAJOR.MINOR.PATCH estável.')
    return tuple(map(int, value.split('.')))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def parse_json(raw):
    def unique(pairs):
        result = {}
        for key, val in pairs:
            if key in result:
                raise UpdateError('Campo JSON duplicado.')
            result[key] = val
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise UpdateError('JSON inválido.') from exc


def safe_path(name):
    p = PurePosixPath(name)
    if (not isinstance(name, str) or len(name) > 240 or not name.startswith('app/') or
            '\\' in name or ':' in name or p.is_absolute() or
            any(x in ('', '.', '..') for x in name.split('/')) or
            any(ord(c) < 32 for c in name)):
        raise UpdateError('Caminho de arquivo não permitido.')
    if p.suffix.lower() not in {'.html', '.js', '.css', '.svg', '.png', '.webp', '.ico', '.woff2'} and name != 'app/vendor/LICENSE-lucide':
        raise UpdateError('Tipo de arquivo não permitido no aplicativo.')
    return name


def sync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    with temp.open('wb') as out:
        out.write(canonical(value))
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)
    sync_dir(path.parent)


def openssl(args, **kwargs):
    try:
        return subprocess.run(['openssl'] + args, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30, **kwargs).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError('Assinatura inválida ou OpenSSL indisponível/incompatível.') from exc


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def public_id(public):
    return hashlib.sha256(Path(public).read_bytes()).hexdigest()


def verify_signature(raw, signature, key, directory):
    if not 384 <= len(signature) <= 1024:
        raise UpdateError('Assinatura RSA-PSS inválida (mínimo RSA 3072).')
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        msg, sig = Path(tmp) / 'manifest.json', Path(tmp) / 'manifest.sig'
        msg.write_bytes(raw)
        sig.write_bytes(signature)
        openssl(['dgst', '-sha256', '-verify', str(key), '-signature', str(sig),
                 '-sigopt', 'rsa_padding_mode:pss', '-sigopt', 'rsa_pss_saltlen:digest', str(msg)])


def inspect_package(package, trust, work, installed=None, machine=None, system=None):
    """Validate all metadata and bytes without extracting or running supplied code."""
    try:
        if not 0 < Path(package).stat().st_size <= MAX_PACKAGE:
            raise UpdateError('Pacote vazio ou acima de 48 MiB.')
        with zipfile.ZipFile(package) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(infos) > MAX_FILES + 2 or len(names) != len(set(names)):
                raise UpdateError('Entradas duplicadas ou arquivos demais.')
            if sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise UpdateError('Expansão excessiva do pacote.')
            for info in infos:
                mode = info.external_attr >> 16
                if (info.is_dir() or info.flag_bits & 1 or
                        stat.S_IFMT(mode) not in (0, stat.S_IFREG) or
                        info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise UpdateError('Links, diretórios ou compressão não permitidos.')
                if info.filename not in ('manifest.json', 'manifest.sig'):
                    safe_path(info.filename)
            if not {'manifest.json', 'manifest.sig'} <= set(names):
                raise UpdateError('Formato de atualização ausente; ZIP antigo não é compatível.')
            if archive.getinfo('manifest.json').file_size > MAX_MANIFEST or archive.getinfo('manifest.sig').file_size > 1024:
                raise UpdateError('Manifesto ou assinatura acima do limite.')
            raw = archive.read('manifest.json')
            manifest = parse_json(raw)
            if not isinstance(manifest, dict) or set(manifest) != {'app_id', 'format', 'version', 'min_updater', 'systems', 'architectures', 'released_at', 'notes', 'key_id', 'files'}:
                raise UpdateError('Campos do manifesto inválidos.')
            kid = manifest['key_id']
            if not isinstance(kid, str) or not re.fullmatch('[a-f0-9]{64}', kid):
                raise UpdateError('Identificador de chave inválido.')
            key = Path(trust) / (kid + '.pem')
            if not key.is_file() or public_id(key) != kid:
                raise UpdateError('Chave desconhecida. Configure uma chave pública confiável fora do pacote.')
            verify_signature(raw, archive.read('manifest.sig'), key, work)
            if manifest['app_id'] != APP_ID or type(manifest['format']) is not int or manifest['format'] != 1:
                raise UpdateError('Aplicativo ou formato incompatível.')
            target_version = version(manifest['version'])
            if version(manifest['min_updater']) > version(UPDATER_VERSION):
                raise UpdateError('Versão mínima do atualizador incompatível.')
            if installed is not None and target_version <= version(installed):
                raise UpdateError('A atualização deve ser mais recente que a versão instalada.')
            for field in ('systems', 'architectures'):
                if not isinstance(manifest[field], list) or not manifest[field] or not all(isinstance(v, str) for v in manifest[field]):
                    raise UpdateError('Compatibilidade inválida.')
            if (system or platform.system()) not in manifest['systems'] or (machine or platform.machine()) not in manifest['architectures']:
                raise UpdateError('Arquitetura ou sistema incompatível com este dispositivo.')
            if not isinstance(manifest['notes'], str) or len(manifest['notes']) > 16000:
                raise UpdateError('Notas de versão inválidas.')
            try:
                datetime.date.fromisoformat(manifest['released_at'])
            except (TypeError, ValueError):
                raise UpdateError('Data da versão inválida.')
            files = manifest['files']
            if not isinstance(files, dict) or not REQUIRED <= set(files) or len(files) > MAX_FILES:
                raise UpdateError('Lista de arquivos incompleta.')
            if set(names) != set(files) | {'manifest.json', 'manifest.sig'}:
                raise UpdateError('Arquivos inesperados ou ausentes no pacote.')
            for name, expected in files.items():
                safe_path(name)
                if not isinstance(expected, dict) or set(expected) != {'sha256', 'size'} or type(expected['size']) is not int or not 0 <= expected['size'] <= MAX_EXPANDED or not re.fullmatch('[a-f0-9]{64}', str(expected['sha256'])):
                    raise UpdateError('Hash ou tamanho inválido.')
                if archive.getinfo(name).file_size != expected['size']:
                    raise UpdateError('Tamanho divergente: ' + name)
                digest = hashlib.sha256()
                with archive.open(name) as src:
                    for chunk in iter(lambda: src.read(65536), b''):
                        digest.update(chunk)
                if digest.hexdigest() != expected['sha256']:
                    raise UpdateError('Hash SHA-256 divergente: ' + name)
            return manifest
    except (zipfile.BadZipFile, EOFError, OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError('Pacote inválido, truncado ou ilegível.') from exc


class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in {'api.github.com', 'github.com', 'release-assets.githubusercontent.com'} or p.username or p.password or p.port not in (None, 443):
        raise UpdateError('Destino HTTPS não permitido.')


def fetch(url, output=None, limit=MAX_PACKAGE, expected=None, progress=lambda n: None):
    validate_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': 'AEGIS-Updater/1', 'Accept': 'application/vnd.github+json' if output is None else 'application/octet-stream'})
    started, count, chunks = time.monotonic(), 0, []
    try:
        with urllib.request.build_opener(HTTPSOnly()).open(req, timeout=15) as response:
            validate_url(response.geturl())
            length = response.headers.get('Content-Length')
            if length is not None and int(length) > limit:
                raise UpdateError('Download acima do limite.')
            with output.open('wb') if output else contextlib.nullcontext(None) as dest:
                while True:
                    if time.monotonic() - started > 120:
                        raise UpdateError('Tempo limite total do download excedido.')
                    block = response.read1(65536)
                    if not block:
                        break
                    count += len(block)
                    if count > limit:
                        raise UpdateError('Download acima do limite.')
                    if dest:
                        dest.write(block)
                    else:
                        chunks.append(block)
                    progress(count)
                if (length is not None and count != int(length)) or (expected is not None and count != expected):
                    raise UpdateError('Download interrompido ou tamanho divergente.')
                if dest:
                    dest.flush()
                    os.fsync(dest.fileno())
        return b''.join(chunks)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and url == RELEASE_API:
            raise UpdateError('Nenhuma Release estável publicada.') from exc
        raise UpdateError('Não foi possível obter a Release/download (HTTP %s).' % exc.code) from exc
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise UpdateError('Sem internet ou falha/interrupção no download. Tente novamente.') from exc
    finally:
        # Partial files must never become candidates.
        if output and count == 0:
            output.unlink(missing_ok=True)


def latest_release():
    release = parse_json(fetch(RELEASE_API, limit=512 * 1024))
    if not isinstance(release, dict) or release.get('draft') is not False or release.get('prerelease') is not False:
        raise UpdateError('Nenhuma Release estável disponível.')
    tag = release.get('tag_name', '')
    release_version = tag.removeprefix('v')
    version(release_version)
    name = 'aegis-' + release_version + '.aegis-update'
    assets = [a for a in release.get('assets', []) if a.get('name') == name]
    if len(assets) != 1:
        raise UpdateError('Release sem pacote assinado compatível. O ZIP antigo não é aceito.')
    asset = assets[0]
    if type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_PACKAGE:
        raise UpdateError('Tamanho do pacote da Release inválido.')
    expected_url = 'https://github.com/leoulson/AEGIS/releases/download/' + urllib.parse.quote(tag, safe='') + '/' + name
    if asset.get('browser_download_url') != expected_url:
        raise UpdateError('Pacote fora das Releases oficiais.')
    return {'version': release_version, 'url': expected_url, 'size': asset['size']}


class Manager:
    def __init__(self, home, trust, source):
        self.home, self.trust, self.source = Path(home), Path(trust), Path(source)
        self.home.mkdir(parents=True, exist_ok=True)
        self.versions = self.home / 'versions'
        self.versions.mkdir(exist_ok=True)
        self.statefile = self.home / 'state.json'

    @contextlib.contextmanager
    def lock(self):
        with (self.home / 'update.lock').open('a') as fd:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise UpdateError('Outra atualização está em andamento.') from exc
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)

    def space(self, required):
        if shutil.disk_usage(self.home).free < required + RESERVE:
            raise UpdateError('Espaço livre insuficiente para preparação e recuperação.')

    def state(self):
        if not self.statefile.exists():
            return {'current': None, 'previous': None, 'pending': None, 'trial': False, 'error': ''}
        return parse_json(self.statefile.read_bytes())

    def save(self, state):
        atomic_json(self.statefile, state)

    def slot(self, slot):
        if not re.fullmatch('[a-f0-9]{32}', slot or ''):
            raise UpdateError('Identificador de instalação inválido.')
        return self.versions / slot

    def info(self, slot):
        return parse_json((self.slot(slot) / 'manifest.json').read_bytes())

    def trusted(self):
        try:
            return (self.trust.is_dir() and shutil.which('openssl') is not None and
                    any(p.stem == public_id(p) for p in self.trust.glob('*.pem') if p.is_file()))
        except OSError:
            return False

    def prune(self, state):
        # Only our unreferenced immutable slots; never application/user data directories.
        retained = {state.get(k) for k in ('current', 'previous', 'pending')}
        for path in self.versions.iterdir():
            if re.fullmatch('[a-f0-9]{32}', path.name) and path.name not in retained and path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
        sync_dir(self.versions)

    def bootstrap(self):
        """Only seed from the locally installed, explicitly obtained bootstrap."""
        with self.lock():
            if self.statefile.exists():
                return
            files = {str(p.relative_to(self.source)): {'size': p.stat().st_size, 'sha256': file_hash(p)}
                     for p in sorted((self.source / 'app').rglob('*')) if p.is_file()}
            if not REQUIRED <= set(files):
                raise UpdateError('Instalação inicial incompleta.')
            self.space(sum(f['size'] for f in files.values()))
            slot = uuid.uuid4().hex
            dest = self.slot(slot)
            dest.mkdir()
            shutil.copytree(self.source / 'app', dest / 'app')
            manifest = {'version': '0.2.0', 'files': files, 'notes': 'Base local com central de atualizações; ainda não é uma Release publicada.'}
            atomic_json(dest / 'manifest.json', manifest)
            self.sync_tree(dest)
            self.save({'current': slot, 'previous': None, 'pending': None, 'trial': False, 'error': ''})

    def sync_tree(self, dest):
        for path in dest.rglob('*'):
            if path.is_file():
                with path.open('rb') as fd:
                    os.fsync(fd.fileno())
        for path in sorted((p for p in dest.rglob('*') if p.is_dir()), reverse=True):
            sync_dir(path)
        sync_dir(dest)
        sync_dir(self.versions)

    def validate_slot(self, slot):
        root, manifest = self.slot(slot), self.info(slot)
        if not REQUIRED <= set(manifest['files']):
            raise UpdateError('Instalação incompleta; restaure a versão anterior.')
        for name, info in manifest['files'].items():
            safe_path(name)
            p = root / name
            if p.is_symlink() or not p.is_file() or p.stat().st_size != info['size'] or file_hash(p) != info['sha256']:
                raise UpdateError('Falha na validação de inicialização: ' + name)
        return root

    def prepare(self, package, progress=lambda text: None):
        with self.lock():
            state = self.state()
            if state['trial'] or state['pending']:
                raise UpdateError('Conclua a inicialização ou cancele a atualização pendente antes de instalar outra.')
            self.prune(state)
            progress('Verificando assinatura, compatibilidade e arquivos…')
            manifest = inspect_package(package, self.trust, self.home, self.info(state['current'])['version'])
            self.space(sum(f['size'] for f in manifest['files'].values()) + Path(package).stat().st_size)
            slot = uuid.uuid4().hex
            dest = self.slot(slot)
            dest.mkdir()
            try:
                with zipfile.ZipFile(package) as archive:
                    for name in manifest['files']:
                        p = dest / safe_path(name)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(name) as src, p.open('xb') as out:
                            shutil.copyfileobj(src, out, 65536)
                atomic_json(dest / 'manifest.json', manifest)
                self.validate_slot(slot)
                self.sync_tree(dest)
                state['pending'] = slot
                state['error'] = ''
                progress('Preparação concluída. Feche e abra o AEGIS quando desejar aplicar.')
                self.save(state)
            except BaseException:
                # A committed state is authoritative even if a directory fsync failed.
                if self.state().get('pending') != slot:
                    shutil.rmtree(dest)
                raise
            return manifest

    def boot(self):
        with self.lock():
            state = self.state()
            if state['trial']:
                if not state['previous']:
                    raise UpdateError('Inicialização incompleta sem versão anterior.')
                state['current'], state['previous'] = state['previous'], None
                state['pending'], state['trial'] = None, False
                state['error'] = 'A nova versão não confirmou a inicialização. Versão anterior recuperada.'
                self.save(state)
            if state['pending']:
                try:
                    self.validate_slot(state['pending'])
                except (OSError, UpdateError):
                    state['pending'] = None
                    state['error'] = 'Atualização preparada inválida. Versão atual preservada; importe novamente o pacote.'
                    self.save(state)
                else:
                    state['previous'], state['current'] = state['current'], state['pending']
                    state['pending'], state['trial'] = None, True
                    self.save(state)
            try:
                root = self.validate_slot(state['current'])
                self.prune(state)
                return root
            except (OSError, UpdateError):
                if not state['previous']:
                    raise
                previous = self.validate_slot(state['previous'])
                state['current'], state['previous'] = state['previous'], None
                state['trial'] = False
                state['error'] = 'Arquivos da nova versão inválidos. Versão anterior recuperada.'
                self.save(state)
                self.prune(state)
                return previous

    def healthy(self, slot):
        with self.lock():
            state = self.state()
            if state['current'] == slot and state['trial']:
                state['trial'] = False
                self.save(state)

    def restore(self):
        with self.lock():
            state = self.state()
            if state['pending']:
                state['pending'] = None
                message = 'Atualização pendente cancelada. Versão atual preservada.'
            else:
                if not state['previous']:
                    raise UpdateError('Não há versão anterior restaurável.')
                self.validate_slot(state['previous'])
                # Restoration is also deferred: never mutate the running application's files.
                state['pending'] = state['previous']
                message = 'Restauração preparada. Feche e abra o AEGIS para aplicar.'
            self.save(state)
            return message

    def defer_trial(self):
        """User closed the loading window normally: defer, do not label it a crash."""
        with self.lock():
            state = self.state()
            if state['trial'] and state['previous']:
                state['pending'], state['current'], state['previous'] = state['current'], state['previous'], None
                state['trial'] = False
                self.save(state)
