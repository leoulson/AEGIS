"""Authenticated IPC for the on-device Chromium window, bound only to loopback."""
import concurrent.futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import tempfile
import threading
import time
import urllib.parse

from device_services import Services, BACKUP_LIMIT

from updater import (MAX_PACKAGE, MAX_EXPANDED, UpdateError, fetch,
                     file_hash, inspect_package, latest_release, version)


class Bridge:
    def __init__(self, manager, root, recovery=False, services=None):
        self.manager, self.root = manager, Path(root)
        self.recovery = recovery
        self.services = services or Services(manager)
        self.restart = threading.Event()
        self.next_mode = None
        self.asset_root = manager.source / 'recovery' if recovery else self.root / 'app'
        try:
            self.preferences_cache = self.services.preferences()
        except (OSError, UpdateError):
            from device_services import DEFAULTS
            self.preferences_cache = dict(DEFAULTS)
        self.token = secrets.token_urlsafe(32)
        self.guard = threading.Lock()
        self.ready = threading.Event()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.job = {'busy': False, 'message': '', 'progress': 0, 'error': False}
        self.candidate = None
        self.temp = tempfile.TemporaryDirectory(prefix='session-', dir=manager.home)
        self.package = Path(self.temp.name) / 'candidate.aegis-update'
        self.backup_package = Path(self.temp.name) / 'import.aegis-backup'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.handler())
        self.server.daemon_threads = True
        self.origin = 'http://127.0.0.1:%d' % self.server.server_port

    def status(self):
        if not self.job['busy']:
            try:
                self.preferences_cache = self.services.preferences()
            except (OSError, UpdateError):
                pass
        try:
            state = self.manager.state()
        except (OSError, UpdateError):
            state = {'current': None, 'previous': None, 'pending': None, 'error': 'Estado do aplicativo ilegível; recuperação independente aberta.'}
        def info(slot):
            try:
                return self.manager.info(slot)['version'] if slot else None
            except (OSError, UpdateError, KeyError):
                return None
        with self.guard:
            return {'installed': info(state['current']),
                    'previous': info(state['previous']),
                    'pending': info(state['pending']),
                    'trust_ready': self.manager.trusted(), 'recovery': state['error'],
                    'candidate': self.candidate, 'job': dict(self.job), 'recovery_mode': self.recovery,
                    'diagnostic': self.services.diagnostic, 'verification': self.services.verification,
                    'preferences': self.preferences_cache, 'notice': self.services.recovery_reason,
                    'backup_candidate': self.services.backup_candidate,
                    'backup_ready': bool(self.services.backup_download),
                    'logs': self.services.logs(), 'restore_incomplete': self.services.journal.exists()}

    def message(self, message, progress=0):
        with self.guard:
            self.job.update(message=message, progress=progress)

    def reserve(self):
        with self.guard:
            if self.restart.is_set():
                raise UpdateError('O aplicativo está encerrando esta sessão.')
            if self.job['busy']:
                raise UpdateError('Outra operação está em andamento.')
            self.job = {'busy': True, 'message': 'Iniciando…', 'progress': 0, 'error': False}

    def finish(self, task):
        try:
            task()
            with self.guard:
                self.job['progress'] = 100
        except Exception as exc:
            with self.guard:
                self.job.update(error=True, message=str(exc) if isinstance(exc, (UpdateError, OSError)) else 'Falha inesperada. A versão atual foi preservada.')
        finally:
            with self.guard:
                self.job['busy'] = False

    def submit(self, task, operation='update'):
        self.reserve()
        with self.guard:
            self.job['operation'] = operation
        self.executor.submit(self.finish, task)

    def discard(self):
        with self.guard:
            self.candidate = None
        self.package.unlink(missing_ok=True)

    def preview(self, release=None):
        self.message('Verificando assinatura e arquivos do pacote…', 80)
        try:
            state = self.manager.state()
            manifest = inspect_package(self.package, self.manager.trust, self.manager.home,
                                       installed=self.manager.info(state['current'])['version'])
            if release and manifest['version'] != release['version']:
                raise UpdateError('Versão assinada não corresponde à Release.')
            candidate = {k: manifest[k] for k in ('version', 'notes', 'released_at', 'architectures', 'systems', 'min_updater')}
            candidate.update(id=secrets.token_urlsafe(24), size=self.package.stat().st_size, verified=True)
            self.candidate_hash = file_hash(self.package)
            with self.guard:
                self.candidate = candidate
            self.message('Pacote autêntico e compatível. Confira os detalhes antes de instalar.', 100)
        except Exception:
            self.discard()
            raise

    def check(self):
        self.discard()
        self.message('Consultando Releases estáveis oficiais…', 5)
        release = latest_release()
        current = self.manager.info(self.manager.state()['current'])['version']
        if version(release['version']) <= version(current):
            self.message('A versão instalada está atualizada; nenhuma versão estável mais recente.', 100)
            return
        self.manager.space(release['size'] + MAX_EXPANDED)
        try:
            fetch(release['url'], self.package, expected=release['size'],
                  progress=lambda n: self.message('Baixando pacote para conferência…', 10 + int(n / release['size'] * 65)))
            self.preview(release)
        except Exception:
            self.discard()
            raise

    def install(self, candidate_id):
        with self.guard:
            candidate = self.candidate
        if not candidate or candidate_id != candidate['id']:
            raise UpdateError('Confira novamente o pacote antes de instalar.')
        if file_hash(self.package) != self.candidate_hash:
            self.discard()
            raise UpdateError('O pacote mudou após a conferência. Importe ou consulte novamente.')
        self.manager.prepare(self.package, lambda text: self.message(text, 90))
        self.discard()

    def restore(self):
        self.message(self.manager.restore(), 100)
        self.discard()

    def installed(self):
        installed = self.status()['installed']
        if installed is None:
            raise UpdateError('Versão local ilegível. Repare o supervisor antes de restaurar dados.')
        return installed

    def preview_backup(self):
        self.services.backup_candidate = None
        try:
            manifest = self.services.inspect_backup(self.backup_package, self.installed())
            self.backup_hash = file_hash(self.backup_package)
            self.services.backup_candidate = {k: manifest[k] for k in ('app_version', 'created_at', 'origin', 'scope')}
            self.services.backup_candidate.update(id=secrets.token_urlsafe(24), files=len(manifest['files']),
                size=sum(f['size'] for f in manifest['files'].values()), authenticity='Hashes conferidos; autenticidade não comprovada.')
            self.message('Backup conferido. Revise origem, data e alcance antes de restaurar.', 100)
        except Exception:
            self.backup_package.unlink(missing_ok=True)
            raise

    def create_backup(self):
        target = Path(self.temp.name) / ('dados-' + secrets.token_hex(8) + '.aegis-backup')
        self.services.create_backup(target, self.installed(), self.message)
        self.message('Backup consistente criado. Use Salvar backup para escolher o destino.', 100)

    def restore_data(self, candidate_id):
        if not self.recovery:
            raise UpdateError('Feche a interface principal e abra o modo de recuperação para restaurar dados.')
        candidate = self.services.backup_candidate
        if not candidate or candidate['id'] != candidate_id or file_hash(self.backup_package) != self.backup_hash:
            raise UpdateError('Confira novamente o backup antes de restaurar.')
        result = self.services.restore_backup(self.backup_package, self.installed(), self.message)
        self.services.backup_candidate = None
        self.preferences_cache = self.services.preferences()
        self.message(result['message'], 100)

    def handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def log_message(self, *args):
                pass  # Never log authentication tokens, bodies or local file names.

            def setup(self):
                super().setup()
                self.connection.settimeout(15)

            def reply(self, code, body, kind='application/json'):
                if isinstance(body, dict):
                    body = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(body)

            def authorized(self, api=False):
                if self.headers.get('Host') != urllib.parse.urlsplit(bridge.origin).netloc:
                    return False
                if api:
                    if not secrets.compare_digest(self.headers.get('X-Aegis-Token', ''), bridge.token):
                        return False
                    origin = self.headers.get('Origin')
                    if (self.command == 'POST' and origin != bridge.origin) or (origin and origin != bridge.origin):
                        return False
                return True

            def do_GET(self):
                if not self.authorized(self.path.startswith('/api/')):
                    self.reply(403, {'error': 'Sessão local inválida.'})
                    return
                try:
                    if self.path in ('/api/diagnostic-report', '/api/backup-download'):
                        if self.path == '/api/diagnostic-report':
                            if bridge.services.diagnostic is None:
                                raise UpdateError('Atualize o diagnóstico antes de exportar.')
                            data = json.dumps(bridge.services.diagnostic, ensure_ascii=False, indent=2).encode()
                            self.reply(200, data, 'application/json')
                        else:
                            path = bridge.services.backup_download
                            if not path or not path.is_file():
                                raise UpdateError('Crie um backup antes de salvar.')
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/octet-stream')
                            self.send_header('Content-Length', str(path.stat().st_size))
                            self.send_header('Cache-Control', 'no-store')
                            self.end_headers()
                            with path.open('rb') as src:
                                import shutil
                                shutil.copyfileobj(src, self.wfile, 65536)
                        return
                    if self.path == '/api/status':
                        self.reply(200, bridge.status())
                        return
                    name = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
                    name = 'index.html' if name == '/' else name.lstrip('/')
                    # Shared UI utilities are part of the trusted supervisor, not the update slot.
                    base = bridge.asset_root
                    if name.startswith('support/'):
                        base = bridge.manager.source / 'recovery'
                        name = name.removeprefix('support/')
                    target = base / name
                    app = base.resolve()
                    if not target.resolve().is_relative_to(app) or not target.is_file():
                        self.reply(404, {'error': 'Arquivo não encontrado.'})
                        return
                    raw = target.read_bytes()
                    if name == 'index.html':
                        if not bridge.recovery:
                            raw = raw.replace(b'</head>', b'<link rel="stylesheet" href="/support/common.css"><script src="/support/common.js"></script></head>')
                        raw = raw.replace(b'<head>', ('<head><script>globalThis.AEGIS_START_ERRORS=[];addEventListener("error",()=>AEGIS_START_ERRORS.push(true));addEventListener("unhandledrejection",()=>AEGIS_START_ERRORS.push(true));globalThis.AEGIS_SESSION=' + json.dumps(bridge.token) + ';globalThis.AEGIS_RECOVERY=' + json.dumps(bridge.recovery) + ';</script>').encode())
                    self.reply(200, raw, mimetypes.guess_type(name)[0] or 'application/octet-stream')
                except (OSError, UpdateError):
                    self.reply(500, {'error': 'Falha ao ler a instalação.'})

            def do_POST(self):
                if not self.authorized(True):
                    self.reply(403, {'error': 'Sessão local inválida.'})
                    return
                try:
                    if self.headers.get('Transfer-Encoding'):
                        raise UpdateError('Use tamanho explícito para a operação.')
                    length = int(self.headers.get('Content-Length', '-1'))
                    if length < 0 or length > (BACKUP_LIMIT if self.path == '/api/backup-import' else MAX_PACKAGE if self.path == '/api/import' else 4096):
                        raise UpdateError('Tamanho da operação inválido ou acima de 48 MiB.')
                    if self.path in ('/api/import', '/api/backup-import'):
                        bridge.reserve()
                        try:
                            is_backup = self.path == '/api/backup-import'
                            if is_backup:
                                bridge.services.backup_candidate = None
                                bridge.backup_package.unlink(missing_ok=True)
                            else:
                                bridge.discard()
                            bridge.manager.space(length + (256 * 1024 * 1024 if is_backup else MAX_EXPANDED))
                            started, remaining = time.monotonic(), length
                            with (bridge.backup_package if is_backup else bridge.package).open('xb') as out:
                                while remaining:
                                    if time.monotonic() - started > 120:
                                        raise UpdateError('Tempo limite da importação excedido.')
                                    block = self.rfile.read(min(65536, remaining))
                                    if not block:
                                        raise UpdateError('Importação interrompida.')
                                    out.write(block)
                                    remaining -= len(block)
                            bridge.executor.submit(bridge.finish, bridge.preview_backup if is_backup else bridge.preview)
                        except Exception as exc:
                            bridge.discard()
                            with bridge.guard:
                                bridge.job.update(busy=False, error=True, message='Importação interrompida: ' + str(exc))
                            raise
                    else:
                        raw = self.rfile.read(length)
                        if len(raw) != length:
                            raise UpdateError('Operação interrompida.')
                        body = json.loads(raw or b'{}')
                        if not isinstance(body, dict):
                            raise UpdateError('Operação JSON inválida.')
                        if self.path == '/api/preferences':
                            bridge.preferences_cache = bridge.services.preferences(body)
                        elif self.path == '/api/diagnostics':
                            bridge.submit(lambda: (bridge.services.diagnostics(), bridge.message('Diagnóstico atualizado.', 100)))
                        elif self.path == '/api/collection-verify':
                            bridge.services.cancel.clear()
                            bridge.submit(lambda: (bridge.services.verify_collection(bridge.message, reset_cancel=False), bridge.message('Verificação concluída.' if not bridge.services.cancel.is_set() else 'Verificação interrompida; os resultados não são uma aprovação completa.', 100)), operation='collection')
                        elif self.path == '/api/collection-cancel':
                            bridge.services.cancel.set()
                        elif self.path == '/api/backup-create':
                            bridge.submit(bridge.create_backup)
                        elif self.path == '/api/backup-restore':
                            bridge.submit(lambda: bridge.restore_data(body.get('id')))
                        elif self.path == '/api/resume-restore':
                            if not bridge.recovery:
                                raise UpdateError('Operação exclusiva do modo de recuperação.')
                            bridge.submit(lambda: (bridge.services.resume_restore(), bridge.message('Restauração retomada e concluída.', 100)))
                        elif self.path in ('/api/restart', '/api/recovery'):
                            with bridge.guard:
                                if bridge.job['busy']:
                                    raise UpdateError('Aguarde a operação terminar antes de reiniciar.')
                            if bridge.services.journal.exists() and self.path == '/api/restart':
                                raise UpdateError('Conclua a restauração interrompida antes de abrir o aplicativo.')
                            with bridge.guard:
                                if bridge.job['busy']:
                                    raise UpdateError('Aguarde a operação terminar.')
                                bridge.next_mode = 'recovery' if self.path == '/api/recovery' else 'normal'
                                bridge.restart.set()
                        elif self.path == '/api/check':
                            bridge.submit(bridge.check)
                        elif self.path == '/api/install':
                            bridge.submit(lambda: bridge.install(body.get('id')))
                        elif self.path == '/api/restore':
                            bridge.submit(bridge.restore)
                        elif self.path == '/api/ready':
                            if not bridge.recovery:
                                bridge.manager.healthy(bridge.root.name)
                            bridge.ready.set()
                        else:
                            self.reply(404, {'error': 'Operação desconhecida.'})
                            return
                    self.reply(202, {'ok': True})
                except (UpdateError, OSError, ValueError) as exc:
                    self.reply(400, {'error': str(exc)})

        return Handler

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.origin + '/'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.executor.shutdown(wait=True)
        self.temp.cleanup()
