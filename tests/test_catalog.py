import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from aegis.catalog import validate, compile_catalog, normalize
from aegis.__main__ import initialize, search, read, policy

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'content/editorial.json').read_text())

    def test_real_initial_material_and_no_fictitious_review(self):
        validate(self.catalog, ROOT)
        self.assertEqual(len(self.catalog['cards']), 7)
        self.assertEqual(len(self.catalog['areas']), 6)
        self.assertEqual({c['id'] for c in self.catalog['cards']}, {'avaliacao-inicial','febre','dispneia','dor-toracica','desidratacao','hipoglicemia','guia-calculadora'})
        for card in self.catalog['cards']:
            self.assertEqual(card['editorial']['state'], 'pending_professional_review')
            self.assertIsNone(card['editorial']['reviewer'])
            self.assertIsNone(card['editorial']['reviewed_on'])
        self.assertTrue(any(s['id'].startswith('ms-') for s in self.catalog['sources']))
        self.assertTrue(any(s['id'].startswith('sci-') for s in self.catalog['sources']))

    def test_validation_rejects_duplicate_ids_missing_fields_and_bad_reference(self):
        for mutate in [lambda c: c['cards'].append(copy.deepcopy(c['cards'][0])),
                       lambda c: c['cards'][0].pop('population'),
                       lambda c: c['cards'][0]['sections']['initial_assessment'][0]['citations'][0].update(source_id='invented'),
                       lambda c: c['cards'][0]['sections']['initial_assessment'][0].update(citations=[]),
                       lambda c: c['cards'][0]['editorial'].update(state='approved'),
                       lambda c: c['cards'][0]['editorial'].update(reviewer='Invented clinician'),
                       lambda c: c['cards'][0]['editorial'].update(state='reviewed'),
                       lambda c: c['sources'][0].update(url='javascript:alert(1)'),
                       lambda c: c['sources'][0].update(verified=False)]:
            with self.subTest(mutate=mutate):
                broken = copy.deepcopy(self.catalog);mutate(broken)
                with self.assertRaises(ValueError):
                    validate(broken, ROOT)

    def test_generated_terminal_and_file_catalog_are_identical_and_current(self):
        expected = compile_catalog(self.catalog, ROOT)
        terminal = json.loads((ROOT / 'content/catalog.json').read_text())
        raw = (ROOT / 'aegis-linux/app/catalog-data.js').read_text().split('globalThis.AegisCatalog = ', 1)[1]
        browser = json.loads(raw.removesuffix(';\n'))
        self.assertEqual(terminal, expected)
        self.assertEqual(browser, terminal)
        subprocess.run([sys.executable, 'tools/build-catalog.py', '--check'], cwd=ROOT, check=True, capture_output=True)

    def test_calculator_files_remain_exactly_the_consulted_code(self):
        source = next(s for s in self.catalog['sources'] if s['id'] == 'aegis-calculator')
        for file, expected in source['verification']['files'].items():
            self.assertEqual(hashlib.sha256((ROOT / file).read_bytes()).hexdigest(), expected)

    def test_editorial_gate_search_areas_full_text_and_offline_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'library.sqlite3'
            self.assertEqual(initialize(db, ROOT / 'content/catalog.json'), 7)
            self.assertEqual(search(db, 'osmolaridade'), [])
            self.assertEqual(search(db, '%', include_pending=True), [])
            result = search(db, 'osmolaridade', include_pending=True)
            self.assertEqual([r['id'] for r in result], ['desidratacao'])
            self.assertTrue(all(r['editorial_state'] == 'pending_professional_review' for r in result))
            self.assertEqual(search(db, '', area='mulher', include_pending=True), [])
            self.assertEqual(len(search(db, '', area='urgencia', include_pending=True)), 4)
            self.assertEqual(search(db, '', state='draft', include_pending=True), [])
            with self.assertRaisesRegex(ValueError, 'não liberada'):
                read(db, 'desidratacao')
            doc = read(db, 'desidratacao', include_pending=True)
            self.assertIn('osmolaridade', doc['body'])
            self.assertIn('Hahn S, Kim Y, Garner P', doc['body'])
            self.assertIn('Consulta documental', doc['body'])
            self.assertIn('não realizada', doc['body'].lower())
            self.assertEqual(policy(db)['title'], self.catalog['policy']['title'])

    def test_reimport_preserves_user_documents_and_does_not_duplicate_editorial_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, legacy = Path(tmp) / 'library.sqlite3', Path(tmp) / 'user.json'
            legacy.write_text(json.dumps([{'id':'desidratacao','title':'Personal reference','category':'Personal','source':'user','reviewed':'unverified','body':'keep my content'}]))
            initialize(db, legacy)
            for _ in range(2):
                initialize(db, ROOT / 'content/catalog.json')
            self.assertEqual(read(db, 'desidratacao')['body'], 'keep my content')
            self.assertEqual(len(search(db, '', include_pending=True)), 8)
            self.assertEqual(read(db, 'editorial:desidratacao', include_pending=True)['id'], 'desidratacao')

    def test_device_inventory_includes_imported_editorial_cards(self):
        sys.path.insert(0, str(ROOT / 'aegis-linux'))
        from updater import Manager
        from device_services import Services
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / 'data'
            initialize(data / 'library.sqlite3', ROOT / 'content/catalog.json')
            services = Services(Manager(base / 'managed', base / 'trust', ROOT / 'aegis-linux'), data)
            self.assertEqual(services.diagnostics(force=True)['documents'], 7)

    def test_cli_default_guard_and_explicit_editorial_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = [sys.executable, '-m', 'aegis', '--db', str(Path(tmp) / 'library.sqlite3')]
            subprocess.run(base + ['init'], cwd=ROOT, check=True, capture_output=True)
            blocked = subprocess.run(base + ['read','hipoglicemia'], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn('--include-pending', blocked.stderr)
            result = subprocess.run(base + ['search','torácica','--area','urgencia','--state','pending_professional_review','--include-pending'], cwd=ROOT, check=True, capture_output=True, text=True)
            self.assertIn('dor-toracica', result.stdout)
            self.assertIn('Pendente de revisão profissional', result.stdout)

    def test_search_normalization_and_safe_generated_data(self):
        self.assertEqual(normalize('ATENÇÃO'), 'atencao')
        spec = importlib.util.spec_from_file_location('builder', ROOT / 'tools/build-catalog.py')
        builder = importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        from unittest.mock import patch
        changed = copy.deepcopy(self.catalog)
        changed['cards'][0]['title'] = '</script><img src=x onerror=alert(1)>'
        with patch.object(builder.json, 'loads', return_value=changed):
            # Validation does not execute any text. Check JS escaping at the generation boundary.
            generated = builder.artifacts()[ROOT / 'aegis-linux/app/catalog-data.js']
        self.assertNotIn(b'</script>', generated)
        self.assertNotIn(b'<img', generated)


if __name__ == '__main__':
    unittest.main()
