"""Disposable on-device bridge for browser QA. Never serves a real installation."""
import importlib.util
import json
import sqlite3
import contextlib
import hashlib
from pathlib import Path
import platform
import shutil
import signal
import sys
import tempfile
import threading

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import updater as u
import update_bridge as ipc


def main():
    with tempfile.TemporaryDirectory(prefix='aegis-browser-qa-') as tmp:
        root = Path(tmp)
        private, public = root / 'private.pem', root / 'public.pem'
        u.openssl(['genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072', '-out', str(private)])
        public.write_bytes(u.openssl(['pkey', '-in', str(private), '-pubout']))
        spec = importlib.util.spec_from_file_location('builder', SOURCE.parent / 'tools/build-update.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        package = builder.build(SOURCE, root / 'packages', '0.3.0', 'Pacote de teste offline. <img src=x onerror=alert(1)>', '2026-11-04', private, public, [platform.machine()])
        private.unlink()  # No private key is needed by the running updater.
        mode = root / 'mode'
        mode.write_text('available')
        def latest():
            if mode.read_text() == 'offline':
                raise u.UpdateError('Sem internet. Tente novamente.')
            if mode.read_text() == 'none':
                raise u.UpdateError('Nenhuma Release estável publicada.')
            return {'version': '0.3.0', 'size': package.stat().st_size, 'url': 'https://github.com/leoulson/AEGIS/releases/download/v0.3.0/aegis-0.3.0.aegis-update'}
        def fetch(url, output, **kwargs):
            if mode.read_text() == 'download-fail':
                output.write_bytes(b'interrupted')
                raise u.UpdateError('Download interrompido.')
            shutil.copyfile(package, output)
        ipc.latest_release, ipc.fetch = latest, fetch
        manager = u.Manager(root / 'application', root / 'trusted', SOURCE)
        manager.trust.mkdir()
        manager.bootstrap()
        bridge = ipc.Bridge(manager, manager.boot())
        # Nonclinical fixtures, exclusively inside this test's temporary directory.
        data = bridge.services.data
        with contextlib.closing(sqlite3.connect(data / 'library.sqlite3')) as db:
            db.execute('create table documents (id text, body text)')
            db.execute("insert into documents values ('qa', 'test only')")
            db.commit()
        personal = data / 'personal'
        personal.mkdir()
        (personal / 'qa.txt').write_text('personal QA fixture')
        package_dir = data / 'packages' / 'qa'
        package_dir.mkdir(parents=True)
        (package_dir / 'reference.txt').write_bytes(b'Nonclinical test document.')
        (package_dir / 'manifest.json').write_bytes(u.canonical({'format':1, 'package_id':'qa', 'version':'1.0.0', 'files':{'reference.txt':{'size':len(b'Nonclinical test document.'),'sha256':hashlib.sha256(b'Nonclinical test document.').hexdigest()}}}))
        recovery = ipc.Bridge(manager, SOURCE, recovery=True)
        recovery_url = recovery.start()
        url = bridge.start()
        print(json.dumps({'url': url, 'package': str(package), 'public': str(public),
                          'trust_target': str(manager.trust / (u.public_id(public) + '.pem')),
                          'mode': str(mode), 'home': str(manager.home), 'recovery_url': recovery_url, 'data': str(data)}), flush=True)
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        stop.wait()
        bridge.close()
        recovery.close()


if __name__ == '__main__':
    main()
