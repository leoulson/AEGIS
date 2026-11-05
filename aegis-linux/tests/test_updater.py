import contextlib
import hashlib
import http.client
import importlib.util
import io
import json
import multiprocessing
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import updater as u
spec = importlib.util.spec_from_file_location('build_update', SOURCE.parent / 'tools/build-update.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def hold_lock(home, trust, source, ready, release):
    with u.Manager(home, trust, source).lock():
        ready.set()
        release.wait(10)


class UpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Disposable test keys only. Nothing written to checkout or real user locations.
        cls.fixture = tempfile.TemporaryDirectory()
        cls.base = Path(cls.fixture.name)
        cls.private, cls.public = cls.base / 'private.pem', cls.base / 'public.pem'
        u.openssl(['genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072', '-out', str(cls.private)])
        cls.public.write_bytes(u.openssl(['pkey', '-in', str(cls.private), '-pubout']))
        cls.package = builder.build(SOURCE, cls.base / 'out', '0.3.0', 'Versão de TESTE, não publicar.',
                                    '2026-11-04', cls.private, cls.public, [platform.machine()])

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trust = self.root / 'trusted'
        self.trust.mkdir()
        (self.trust / (u.public_id(self.public) + '.pem')).write_bytes(self.public.read_bytes())
        self.manager = u.Manager(self.root / 'application', self.trust, SOURCE)
        self.manager.bootstrap()
        self.original = self.manager.state()['current']

    def inspect(self, package=None, **kwargs):
        return u.inspect_package(package or self.package, self.trust, self.root, **kwargs)

    def rewrite(self, change=None, entries=None, sign=False):
        with zipfile.ZipFile(self.package) as z:
            data = {i.filename: z.read(i.filename) for i in z.infolist()}
        if change:
            manifest = json.loads(data['manifest.json'])
            change(manifest)
            data['manifest.json'] = u.canonical(manifest)
        if entries:
            entries(data)
        if sign:
            msg, sig = self.root / 'msg', self.root / 'sig'
            msg.write_bytes(data['manifest.json'])
            u.openssl(['dgst', '-sha256', '-sign', str(self.private), '-out', str(sig),
                       '-sigopt', 'rsa_padding_mode:pss', '-sigopt', 'rsa_pss_saltlen:digest', str(msg)])
            data['manifest.sig'] = sig.read_bytes()
        target = self.root / 'changed.aegis-update'
        with zipfile.ZipFile(target, 'w') as z:
            for name, raw in data.items():
                z.writestr(name, raw)
        return target

    def test_valid_package_and_no_extraction_at_preview(self):
        manifest = self.inspect(installed='0.2.0')
        self.assertEqual(manifest['version'], '0.3.0')
        self.assertEqual(list(self.manager.versions.iterdir()), [self.manager.slot(self.original)])

    def test_invalid_signature(self):
        package = self.rewrite(change=lambda m: m.update(notes='Adulterado'))
        with self.assertRaisesRegex(u.UpdateError, 'Assinatura'):
            self.inspect(package)

    def test_unknown_key_and_no_keys_from_package(self):
        package = self.rewrite(change=lambda m: m.update(key_id='0' * 64))
        with self.assertRaisesRegex(u.UpdateError, 'Chave desconhecida'):
            self.inspect(package)
        for p in self.trust.iterdir():
            p.unlink()
        with self.assertRaisesRegex(u.UpdateError, 'Chave desconhecida'):
            self.inspect()

    def test_hash_mismatch(self):
        package = self.rewrite(entries=lambda d: d.update({'app/index.html': b'x' * len(d['app/index.html'])}))
        with self.assertRaisesRegex(u.UpdateError, 'SHA-256 divergente'):
            self.inspect(package)

    def test_truncated_package(self):
        package = self.root / 'truncated'
        package.write_bytes(self.package.read_bytes()[:100])
        with self.assertRaisesRegex(u.UpdateError, 'truncado'):
            self.inspect(package)

    def test_incompatible_architecture_os_updater_and_version(self):
        for field, value, message in [('architectures', ['not-a-real-arch'], 'Arquitetura'),
                                       ('systems', ['OtherOS'], 'sistema'),
                                       ('min_updater', '99.0.0', 'mínima'),
                                       ('format', 2, 'formato'), ('app_id', 'another.app', 'Aplicativo')]:
            with self.subTest(field=field):
                package = self.rewrite(change=lambda m: m.update({field: value}), sign=True)
                with self.assertRaisesRegex(u.UpdateError, message):
                    self.inspect(package)
        with self.assertRaisesRegex(u.UpdateError, 'mais recente'):
            self.inspect(installed='0.3.0')
        for bad in ['1.2', 'v1.2.3', '1.2.3-beta', '01.2.3']:
            with self.assertRaises(u.UpdateError):
                u.version(bad)

    def test_absolute_parent_duplicate_symlink_unexpected_and_bomb(self):
        for name in ['/tmp/escape', '../escape', 'app/../../escape', 'app//escape.js', 'app/./escape.js', 'app\\escape.js', 'app/hook.sh']:
            with self.subTest(name=name):
                package = self.rewrite(entries=lambda d: d.update({name: b'no'}))
                with self.assertRaises(u.UpdateError):
                    self.inspect(package)
        package = self.rewrite(entries=lambda d: d.update({'app/unexpected.js': b'no'}))
        with self.assertRaisesRegex(u.UpdateError, 'inesperados'):
            self.inspect(package)
        with zipfile.ZipFile(package, 'a') as z:
            link = zipfile.ZipInfo('app/link.js')
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(link, '/tmp/escape')
        with self.assertRaisesRegex(u.UpdateError, 'Links'):
            self.inspect(package)
        package = self.rewrite()
        with zipfile.ZipFile(package, 'a') as z:
            with self.assertWarns(UserWarning):
                z.writestr('app/index.html', b'duplicate')
        with self.assertRaisesRegex(u.UpdateError, 'duplicadas'):
            self.inspect(package)
        with patch.object(u, 'MAX_EXPANDED', 10):
            with self.assertRaisesRegex(u.UpdateError, 'Expansão'):
                self.inspect()
        self.assertFalse((self.root / 'escape').exists())

    def test_insufficient_space_leaves_current_untouched(self):
        with patch.object(u.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(100, 99, 1)):
            with self.assertRaisesRegex(u.UpdateError, 'Espaço livre'):
                self.manager.prepare(self.package)
        self.assertEqual(self.manager.state()['current'], self.original)
        self.assertIsNone(self.manager.state()['pending'])

    def test_concurrent_process_installation_lock(self):
        ready, release = multiprocessing.Event(), multiprocessing.Event()
        process = multiprocessing.Process(target=hold_lock, args=(self.manager.home, self.trust, SOURCE, ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaisesRegex(u.UpdateError, 'andamento'):
                self.manager.prepare(self.package)
        finally:
            release.set()
            process.join(5)
        self.assertEqual(process.exitcode, 0)

    def test_atomic_activation_failure_and_recovery_after_power_loss(self):
        self.manager.prepare(self.package)
        pending = self.manager.state()['pending']
        original_replace = os.replace
        def fail(source, target):
            if Path(target) == self.manager.statefile:
                raise OSError('simulated power failure before activation')
            return original_replace(source, target)
        with patch.object(u.os, 'replace', side_effect=fail):
            with self.assertRaises(OSError):
                self.manager.boot()
        self.assertEqual(self.manager.state()['current'], self.original)
        self.assertEqual(self.manager.state()['pending'], pending)
        self.manager.boot()  # trial committed, crash before ready
        self.assertTrue(self.manager.state()['trial'])
        root = self.manager.boot()
        self.assertEqual(root, self.manager.slot(self.original))
        self.assertFalse(self.manager.state()['trial'])
        self.assertIn('recuperada', self.manager.state()['error'])

    def test_failure_during_preparation_preserves_current(self):
        with patch.object(self.manager, 'sync_tree', side_effect=OSError('simulated fsync failure')):
            with self.assertRaises(OSError):
                self.manager.prepare(self.package)
        self.assertEqual(self.manager.state()['current'], self.original)
        self.assertIsNone(self.manager.state()['pending'])
        self.assertEqual(len(list(self.manager.versions.iterdir())), 1)

    def test_corrupt_pending_version_recovers_without_activation(self):
        self.manager.prepare(self.package)
        (self.manager.slot(self.manager.state()['pending']) / 'app/index.html').write_text('broken')
        self.assertEqual(self.manager.boot(), self.manager.slot(self.original))
        self.assertIn('preservada', self.manager.state()['error'])

    def test_restore_previous_and_preserve_user_data(self):
        data = self.root / 'persistent-data'
        data.mkdir()
        for name in ['library.sqlite3', 'favorites.json', 'annotations.json', 'settings.json', 'history.json', 'model.gguf']:
            (data / name).write_bytes(b'untouched user bytes ' + name.encode())
        before = {p.name: p.read_bytes() for p in data.iterdir()}
        self.manager.prepare(self.package)
        self.assertEqual(self.manager.state()['current'], self.original)
        active = self.manager.boot()
        self.manager.healthy(active.name)
        self.assertEqual(self.manager.info(self.manager.state()['current'])['version'], '0.3.0')
        self.assertIn('preparada', self.manager.restore())
        self.assertEqual(self.manager.info(self.manager.state()['current'])['version'], '0.3.0')
        restored = self.manager.boot()
        self.manager.healthy(restored.name)
        self.assertEqual(restored, self.manager.slot(self.original))
        self.assertEqual(before, {p.name: p.read_bytes() for p in data.iterdir()})

    def test_cancel_pending_and_no_previous(self):
        with self.assertRaisesRegex(u.UpdateError, 'Não há versão'):
            self.manager.restore()
        self.manager.prepare(self.package)
        with self.assertRaisesRegex(u.UpdateError, 'pendente'):
            self.manager.prepare(self.package)
        self.assertIn('cancelada', self.manager.restore())
        self.assertEqual(self.manager.state()['current'], self.original)

    def test_network_offline_and_download_failures(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = urllib.error.URLError('offline')
        with patch.object(u.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(u.UpdateError, 'Sem internet'):
                u.latest_release()
        class Response(io.BytesIO):
            headers = {'Content-Length': '100'}
            def geturl(self):
                return 'https://github.com/leoulson/AEGIS/releases/download/v0.3.0/aegis-0.3.0.aegis-update'
        opener.open.side_effect = None
        opener.open.return_value = Response(b'only a few bytes')
        with patch.object(u.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(u.UpdateError, 'interrompido'):
                u.fetch(Response().geturl(), self.root / 'partial')
        opener.open.return_value = Response(b'x' * 101)
        with patch.object(u.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(u.UpdateError, 'limite'):
                u.fetch(Response().geturl(), self.root / 'partial', limit=5)
        opener.open.return_value = Response(b'data')
        with patch.object(u.urllib.request, 'build_opener', return_value=opener), patch.object(u.time, 'monotonic', side_effect=[0, 121]):
            with self.assertRaisesRegex(u.UpdateError, 'Tempo limite'):
                u.fetch(Response().geturl(), self.root / 'partial')
        with self.assertRaisesRegex(u.UpdateError, 'HTTPS'):
            u.validate_url('http://github.com/malicious')
        with self.assertRaisesRegex(u.UpdateError, 'HTTPS'):
            u.validate_url('https://evil.example/a')

    def test_stable_official_release_only_and_no_legacy_zip(self):
        release = {'draft': False, 'prerelease': False, 'tag_name': 'v0.3.0', 'assets': [
            {'name': 'aegis-0.3.0.aegis-update', 'size': 2000,
             'browser_download_url': 'https://github.com/leoulson/AEGIS/releases/download/v0.3.0/aegis-0.3.0.aegis-update'}]}
        with patch.object(u, 'fetch', return_value=u.canonical(release)):
            self.assertEqual(u.latest_release()['version'], '0.3.0')
        for changes in [{'prerelease': True}, {'draft': True}, {'assets': []}, {'tag_name': 'main'}]:
            with patch.object(u, 'fetch', return_value=u.canonical(dict(release, **changes))):
                with self.assertRaises(u.UpdateError):
                    u.latest_release()
        with self.assertRaises(u.UpdateError):
            self.inspect(SOURCE.parent / 'downloads/AEGIS-Linux-atualizado.zip')

    def test_missing_releases(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError(u.RELEASE_API, 404, 'not found', {}, None)
        with patch.object(u.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(u.UpdateError, 'Nenhuma Release'):
                u.latest_release()


if __name__ == '__main__':
    unittest.main()
