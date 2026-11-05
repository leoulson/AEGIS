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

from updater import (MAX_PACKAGE, MAX_EXPANDED, UpdateError, fetch,
                     file_hash, inspect_package, latest_release, version)


class Bridge:
    def __init__(self, manager, root):
        self.manager, self.root = manager, Path(root)
        self.token = secrets.token_urlsafe(32)
        self.guard = threading.Lock()
        self.ready = threading.Event()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.job = {'busy': False, 'message': '', 'progress': 0, 'error': False}
        self.candidate = None
        self.temp = tempfile.TemporaryDirectory(prefix='session-', dir=manager.home)
        self.package = Path(self.temp.name) / 'candidate.aegis-update'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.handler())
        self.server.daemon_threads = True
        self.origin = 'http://127.0.0.1:%d' % self.server.server_port

    def status(self):
        state = self.manager.state()
        with self.guard:
            return {'installed': self.manager.info(state['current'])['version'],
                    'previous': self.manager.info(state['previous'])['version'] if state['previous'] else None,
                    'pending': self.manager.info(state['pending'])['version'] if state['pending'] else None,
                    'trust_ready': self.manager.trusted(), 'recovery': state['error'],
                    'candidate': self.candidate, 'job': dict(self.job)}

    def message(self, message, progress=0):
        with self.guard:
            self.job.update(message=message, progress=progress)

    def reserve(self):
        with self.guard:
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

    def submit(self, task):
        self.reserve()
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
                    if self.path == '/api/status':
                        self.reply(200, bridge.status())
                        return
                    name = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
                    name = 'index.html' if name == '/' else name.lstrip('/')
                    target = bridge.root / 'app' / name
                    app = (bridge.root / 'app').resolve()
                    if not target.resolve().is_relative_to(app) or not target.is_file():
                        self.reply(404, {'error': 'Arquivo não encontrado.'})
                        return
                    raw = target.read_bytes()
                    if name == 'index.html':
                        raw = raw.replace(b'</head>', ('<script>globalThis.AEGIS_START_ERRORS=[];addEventListener("error",()=>AEGIS_START_ERRORS.push(true));addEventListener("unhandledrejection",()=>AEGIS_START_ERRORS.push(true));globalThis.AEGIS_SESSION=' + json.dumps(bridge.token) + ';</script></head>').encode())
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
                    if length < 0 or length > (MAX_PACKAGE if self.path == '/api/import' else 4096):
                        raise UpdateError('Tamanho da operação inválido ou acima de 48 MiB.')
                    if self.path == '/api/import':
                        bridge.reserve()
                        try:
                            bridge.discard()
                            bridge.manager.space(length + MAX_EXPANDED)
                            started, remaining = time.monotonic(), length
                            with bridge.package.open('xb') as out:
                                while remaining:
                                    if time.monotonic() - started > 120:
                                        raise UpdateError('Tempo limite da importação excedido.')
                                    block = self.rfile.read(min(65536, remaining))
                                    if not block:
                                        raise UpdateError('Importação interrompida.')
                                    out.write(block)
                                    remaining -= len(block)
                            bridge.executor.submit(bridge.finish, bridge.preview)
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
                        if self.path == '/api/check':
                            bridge.submit(bridge.check)
                        elif self.path == '/api/install':
                            bridge.submit(lambda: bridge.install(body.get('id')))
                        elif self.path == '/api/restore':
                            bridge.submit(bridge.restore)
                        elif self.path == '/api/ready':
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
