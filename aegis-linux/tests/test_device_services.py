import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from updater import Manager, UpdateError, canonical, atomic_json
from device_services import Services, LaunchHistory, data_lock, DEFAULTS, validate_preferences, digest


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.manager = Manager(self.base / 'managed', self.base / 'trust', SOURCE)
        self.manager.bootstrap()
        self.svc = Services(self.manager, self.base / 'data')

    def package(self, manifest=True):
        directory = self.svc.data / 'packages' / 'reference'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'document.txt').write_text('Test document, no clinical content.')
        m = {'format': 1, 'package_id': 'reference', 'version': '1.0.0', 'files': {
            'document.txt': {'size': (directory / 'document.txt').stat().st_size,
                             'sha256': hashlib.sha256((directory / 'document.txt').read_bytes()).hexdigest()}}}
        if manifest:
            (directory / 'manifest.json').write_bytes(canonical(m))
        return directory

    def test_diagnostics_real_sources_and_missing_sensors(self):
        proc, sysroot, etc = [self.base / p for p in ['proc', 'sys', 'etc']]
        (proc / 'device-tree').mkdir(parents=True)
        sysroot.mkdir(); etc.mkdir()
        (proc / 'device-tree/model').write_bytes(b'Raspberry Pi fixture\0')
        (proc / 'meminfo').write_text('MemTotal: 1024 kB\nMemAvailable: 512 kB\n')
        (etc / 'os-release').write_text('PRETTY_NAME="Linux fixture"\n')
        d = self.svc.diagnostics(proc, sysroot, etc, force=True)
        self.assertEqual(d['model'], 'Raspberry Pi fixture')
        self.assertEqual(d['aegis_version'], '0.2.0')
        self.assertEqual(d['memory'], {'total': 1048576, 'available': 524288})
        self.assertEqual(d['storage']['total'], shutil.disk_usage(self.svc.data).total)
        self.assertEqual(d['os'], 'Linux fixture')
        self.assertIsNone(d['cpu_temperature_c'])
        zone = sysroot / 'class/thermal/thermal_zone0'
        zone.mkdir(parents=True)
        (zone / 'type').write_text('cpu-thermal')
        (zone / 'temp').write_text('42000')
        self.assertEqual(self.svc.diagnostics(proc, sysroot, etc, force=True)['cpu_temperature_c'], 42)
        self.assertEqual(self.svc.diagnostics()['updated_at'], self.svc.diagnostic['updated_at'])

    def test_diagnostics_missing_files_and_private_fields_excluded(self):
        self.svc.preferences(dict(DEFAULTS))
        (self.svc.data / 'annotations.json').write_text('{"patient":"PRIVATE"}')
        report = self.svc.diagnostics(self.base / 'missing', self.base / 'missing', self.base / 'missing', force=True)
        self.assertIsNone(report['model'])
        self.assertIsNone(report['memory']['available'])
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertNotIn(str(self.base), json.dumps(report))
        self.assertNotIn('annotations', json.dumps(report))

    def test_collection_intact_missing_divergent_unreadable_unverifiable(self):
        directory = self.package()
        def status():
            return self.svc.verify_collection()['packages'][0]
        self.assertEqual(status()['integrity'], 'intact')
        self.assertIn('autenticidade não verificada', status()['authenticity'])
        (directory / 'document.txt').write_text('altered')
        self.assertEqual(status()['files'][0]['status'], 'divergent')
        (directory / 'document.txt').unlink()
        self.assertEqual(status()['files'][0]['status'], 'missing')
        self.package()
        with patch('device_services.digest', side_effect=PermissionError('simulated')):
            self.assertEqual(status()['files'][0]['status'], 'unreadable')
        (directory / 'manifest.json').unlink()
        self.assertEqual(status()['integrity'], 'unverifiable')
        self.assertFalse((directory / 'manifest.json').exists())

    def test_collection_cancel_changed_extra_and_path_safety(self):
        directory = self.package()
        def cancel(*_):
            self.svc.cancel.set()
        result = self.svc.verify_collection(cancel)
        self.assertFalse(result['complete'])
        self.assertEqual(result['packages'][0]['integrity'], 'incomplete')
        with patch('device_services.digest', side_effect=UpdateError('changed')):
            self.assertEqual(self.svc.verify_collection()['packages'][0]['files'][0]['status'], 'changed_or_unsafe')
        (directory / 'extra.txt').write_text('unlisted')
        self.assertEqual(self.svc.verify_collection()['packages'][0]['integrity'], 'damaged')
        m = json.loads((directory / 'manifest.json').read_text())
        m['files']['../escape'] = m['files'].pop('document.txt')
        (directory / 'manifest.json').write_bytes(canonical(m))
        self.assertEqual(self.svc.verify_collection()['packages'][0]['integrity'], 'unverifiable')

    def test_detects_mutation_during_streaming_read(self):
        path = self.base / 'large'
        path.write_bytes(b'a' * 150000)
        changed = False
        def mutate(_):
            nonlocal changed
            if not changed:
                changed = True
                with path.open('ab') as out:
                    out.write(b'changed')
        with self.assertRaisesRegex(UpdateError, 'alterado'):
            digest(path, progress=mutate)

    def test_operations_lock_preferences_and_collection(self):
        with data_lock(self.svc.data):
            with self.assertRaisesRegex(UpdateError, 'em uso'):
                self.svc.preferences(dict(DEFAULTS))
            with self.assertRaisesRegex(UpdateError, 'em uso'):
                self.svc.verify_collection()

    def make_data(self):
        db = self.svc.data / 'library.sqlite3'
        with contextlib.closing(sqlite3.connect(db)) as connection:
            connection.execute('create table documents (id text, body text)')
            connection.execute("insert into documents values ('1', 'Personal test data')")
            connection.commit()
        self.svc.preferences(dict(DEFAULTS))
        personal = self.svc.data / 'personal'
        personal.mkdir()
        (personal / 'document.txt').write_text('saved personal document')
        (self.svc.data / 'favorites.json').write_text('[1,2]')
        for folder in ['models', 'packages']:
            (self.svc.data / folder).mkdir()
            (self.svc.data / folder / 'untouched').write_text('do not include or modify')

    def backup(self):
        dest = self.base / ('backup-' + str(len(list(self.base.glob('*.aegis-backup')))) + '.aegis-backup')
        self.svc.create_backup(dest, '0.2.0')
        return dest

    def rewrite(self, backup, transform):
        with zipfile.ZipFile(backup) as z:
            entries = {i.filename: z.read(i.filename) for i in z.infolist()}
        transform(entries)
        dest = self.base / 'changed.aegis-backup'
        with zipfile.ZipFile(dest, 'w') as z:
            for k, v in entries.items():
                z.writestr(k, v)
        return dest

    def test_backup_consistent_sqlite_and_explicit_scope(self):
        self.make_data()
        path = self.backup()
        m = self.svc.inspect_backup(path, '0.2.0')
        self.assertIn('library.sqlite3', m['files'])
        self.assertIn('personal/document.txt', m['files'])
        self.assertNotIn('models/untouched', m['files'])
        self.assertNotIn('packages/untouched', m['files'])
        with zipfile.ZipFile(path) as z:
            extracted = self.base / 'snapshot.sqlite3'
            extracted.write_bytes(z.read('library.sqlite3'))
        with contextlib.closing(sqlite3.connect(extracted)) as db:
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('select count(*) from documents').fetchone()[0], 1)

    def test_existing_backup_destination_is_never_deleted_or_overwritten(self):
        destination = self.base / 'existing.aegis-backup'
        destination.write_bytes(b'preserve existing user backup')
        with self.assertRaises(FileExistsError):
            self.svc.create_backup(destination, '0.2.0')
        self.assertEqual(destination.read_bytes(), b'preserve existing user backup')
        with data_lock(self.svc.data):
            with self.assertRaises(UpdateError):
                self.svc.create_backup(destination, '0.2.0')
        self.assertEqual(destination.read_bytes(), b'preserve existing user backup')

    def test_restore_preserves_additional_files_and_creates_safety_copy(self):
        self.make_data()
        original = self.backup()
        (self.svc.data / 'personal/document.txt').write_text('newer data')
        (self.svc.data / 'personal/additional.txt').write_text('preserved')
        result = self.svc.restore_backup(original, '0.2.0')
        self.assertIn('restaurados', result['message'])
        self.assertEqual((self.svc.data / 'personal/document.txt').read_text(), 'saved personal document')
        self.assertEqual((self.svc.data / 'personal/additional.txt').read_text(), 'preserved')
        safety = self.manager.home / 'safety-backups' / result['safety_backup']
        self.assertTrue(safety.is_file())
        with zipfile.ZipFile(safety) as z:
            self.assertEqual(z.read('personal/document.txt'), b'newer data')
        self.assertEqual((self.svc.data / 'models/untouched').read_text(), 'do not include or modify')

    def test_restore_interruption_and_resume(self):
        self.make_data()
        backup = self.backup()
        (self.svc.data / 'favorites.json').write_text('[99]')
        real_replace = os.replace
        calls = 0
        def interrupted(src, dst):
            nonlocal calls
            if Path(dst).parent == self.svc.data:
                calls += 1
                if calls == 2:
                    raise OSError('simulated power failure')
            return real_replace(src, dst)
        with patch('device_services.os.replace', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.svc.restore_backup(backup, '0.2.0')
        self.assertTrue(self.svc.journal.exists())
        restarted = Services(self.manager, self.svc.data)
        self.assertTrue(restarted.resume_restore())
        self.assertFalse(restarted.journal.exists())
        self.assertEqual((self.svc.data / 'favorites.json').read_text(), '[1,2]')
        self.assertFalse(restarted.resume_restore())
        self.assertEqual(len(list((self.manager.home / 'safety-backups').iterdir())), 1)

    def test_backup_incompatible_corrupt_and_malicious_paths(self):
        self.make_data()
        backup = self.backup()
        def change_manifest(d):
            m = json.loads(d['manifest.json']);m['format'] = 99;d['manifest.json'] = canonical(m)
        with self.assertRaisesRegex(UpdateError, 'incompatível'):
            self.svc.inspect_backup(self.rewrite(backup, change_manifest), '0.2.0')
        with self.assertRaisesRegex(UpdateError, 'incompatível'):
            self.svc.inspect_backup(backup, '9.0.0')
        broken = self.rewrite(backup, lambda d: d.update({'favorites.json': b'[]'}))
        with self.assertRaises(UpdateError):
            self.svc.inspect_backup(broken, '0.2.0')
        for name in ['/tmp/escape', '../escape', 'personal/../../escape', 'app/execute.py', 'preferences.json/child', 'models/model']:
            with self.subTest(name=name):
                broken = self.rewrite(backup, lambda d: d.update({name: b'evil'}))
                with self.assertRaises(UpdateError):
                    self.svc.inspect_backup(broken, '0.2.0')
        truncated = self.base / 'truncated'
        truncated.write_bytes(backup.read_bytes()[:40])
        with self.assertRaises(UpdateError):
            self.svc.inspect_backup(truncated, '0.2.0')

    def test_restore_insufficient_space_and_invalid_configuration_no_overwrite(self):
        self.make_data()
        backup = self.backup()
        before = (self.svc.data / 'favorites.json').read_bytes()
        with patch('device_services.shutil.disk_usage', return_value=shutil._ntuple_diskusage(100, 100, 0)):
            with self.assertRaisesRegex(UpdateError, 'Espaço'):
                self.svc.restore_backup(backup, '0.2.0')
        self.assertEqual(before, (self.svc.data / 'favorites.json').read_bytes())
        self.assertFalse(self.svc.journal.exists())
        def invalid_preferences(entries):
            malicious = b'{"format":1,"execute":"arbitrary code"}'
            entries['preferences.json'] = malicious
            m = json.loads(entries['manifest.json'])
            m['files']['preferences.json'] = {'size': len(malicious), 'sha256': hashlib.sha256(malicious).hexdigest()}
            entries['manifest.json'] = canonical(m)
        invalid = self.rewrite(backup, invalid_preferences)
        with self.assertRaises(UpdateError):
            self.svc.restore_backup(invalid, '0.2.0')
        self.assertEqual(before, (self.svc.data / 'favorites.json').read_bytes())
        self.assertFalse(self.svc.journal.exists())

    def test_preferences_atomic_persistent_corrupt_and_migrated(self):
        p = dict(DEFAULTS, text_size=200, high_contrast=True, reduced_motion=True)
        self.svc.preferences(p)
        self.assertEqual(Services(self.manager, self.svc.data).preferences(), p)
        self.svc.prefs.write_text('not json')
        self.assertEqual(self.svc.preferences()['text_size'], 100)
        self.assertEqual(len(list(self.svc.data.glob('preferences.problem-*.json'))), 1)
        self.svc.prefs.write_text(json.dumps(dict(DEFAULTS, format=0, text_size=150)))
        self.assertEqual(self.svc.preferences()['format'], 1)
        self.assertEqual(self.svc.preferences()['text_size'], 150)
        self.assertFalse(self.svc.prefs.with_suffix('.tmp').exists())

    def test_shortcuts_deduplication_order_unknown_and_no_commands(self):
        p = validate_preferences(dict(DEFAULTS, shortcuts=['recovery','calculator','calculator','removed','rm -rf /']))
        self.assertEqual(p['shortcuts'], ['recovery', 'calculator'])
        self.svc.preferences(p)
        self.assertEqual(self.svc.preferences()['shortcuts'], ['recovery', 'calculator'])
        with self.assertRaises(UpdateError):
            validate_preferences(dict(DEFAULTS, high_contrast='eval(1)'))

    def test_normal_close_and_crash_markers_do_not_loop(self):
        h = LaunchHistory(self.manager.home)
        self.assertFalse(h.needs_recovery())
        h.begin();h.ready();h.end(True)
        self.assertFalse(LaunchHistory(self.manager.home).needs_recovery())
        h.begin()
        self.assertTrue(LaunchHistory(self.manager.home).needs_recovery())
        h.end(False);h.begin();h.end(False)
        self.assertTrue(h.needs_recovery())
        h.acknowledge()
        self.assertFalse(h.needs_recovery())

    def test_backup_rejects_symlinks_duplicates_and_excessive_expansion(self):
        import stat
        self.make_data()
        backup = self.backup()
        target = self.rewrite(backup, lambda d: None)
        with zipfile.ZipFile(target, 'a') as z:
            link = zipfile.ZipInfo('personal/link')
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(link, '/tmp/escape')
        with self.assertRaises(UpdateError):
            self.svc.inspect_backup(target, '0.2.0')
        target = self.rewrite(backup, lambda d: None)
        with zipfile.ZipFile(target, 'a') as z:
            with self.assertWarns(UserWarning):
                z.writestr('manifest.json', '{}')
        with self.assertRaises(UpdateError):
            self.svc.inspect_backup(target, '0.2.0')
        with patch('device_services.EXPANDED_LIMIT', 1):
            with self.assertRaises(UpdateError):
                self.svc.inspect_backup(backup, '0.2.0')

    def test_corrupt_restore_journal_and_startup_record_are_bounded_errors(self):
        self.svc.journal.write_text('[]')
        with self.assertRaises(UpdateError):
            self.svc.resume_restore()
        history_path = self.manager.home / 'launch-status.json'
        history_path.write_text('{"format":1,"failures":"broken"}')
        self.assertFalse(LaunchHistory(self.manager.home).needs_recovery())
        self.assertFalse(LaunchHistory(self.manager.home).state['running'])

    def test_signed_collection_reuses_existing_trust(self):
        import subprocess
        from updater import openssl, public_id
        directory = self.package()
        private, public = self.base / 'private.pem', self.base / 'public.pem'
        openssl(['genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072', '-out', str(private)])
        public.write_bytes(openssl(['pkey', '-in', str(private), '-pubout']))
        manifest = json.loads((directory / 'manifest.json').read_text())
        manifest['key_id'] = public_id(public)
        (directory / 'manifest.json').write_bytes(canonical(manifest))
        openssl(['dgst','-sha256','-sign',str(private),'-out',str(directory / 'manifest.sig'),'-sigopt','rsa_padding_mode:pss','-sigopt','rsa_pss_saltlen:digest',str(directory / 'manifest.json')])
        self.assertIn('Chave desconhecida', self.svc.verify_collection()['packages'][0]['authenticity'])
        self.manager.trust.mkdir()
        (self.manager.trust / (public_id(public) + '.pem')).write_bytes(public.read_bytes())
        self.assertIn('Assinatura verificada', self.svc.verify_collection()['packages'][0]['authenticity'])
        (directory / 'manifest.sig').write_bytes(b'x' * 384)
        result = self.svc.verify_collection()['packages'][0]
        self.assertEqual(result['integrity'], 'intact')
        self.assertEqual(result['authenticity'], 'Assinatura inválida')

    def test_collection_builder_from_original_source(self):
        import subprocess
        source = self.base / 'original'
        source.mkdir()
        (source / 'reference.txt').write_text('original nonclinical bytes')
        output = self.base / 'manifest-output'
        command = [sys.executable, str(SOURCE.parent / 'tools/build-collection-manifest.py'), '--source', str(source), '--output', str(output), '--package-id', 'test-original', '--version', '1.0.0']
        subprocess.run(command, check=True, capture_output=True)
        manifest = json.loads((output / 'manifest.json').read_text())
        self.assertEqual(manifest['files']['reference.txt']['sha256'], hashlib.sha256(b'original nonclinical bytes').hexdigest())
        (source / 'manifest.json').write_text('{}')
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_logs_do_not_store_raw_user_text(self):
        self.svc.event('a secret token or patient content')
        self.assertEqual(self.svc.logs(), [])
        self.svc.event('backup_created')
        self.assertEqual(set(self.svc.logs()[0]), {'at','code'})


if __name__ == '__main__':
    unittest.main()
