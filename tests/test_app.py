import json
import tempfile
import unittest
from pathlib import Path
from aegis.__main__ import initialize, read, search

class AegisTests(unittest.TestCase):
    def test_offline_import_search_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'library.db'
            src = Path(tmp) / 'docs.json'
            src.write_text(json.dumps([{'id':'x','title':'Teste offline','category':'Demo','source':'local','reviewed':'2026-11-03','body':'Sem rede'}]), encoding='utf-8')
            self.assertEqual(initialize(db, src), 1)
            self.assertEqual(search(db, 'offline')[0]['id'], 'x')
            self.assertEqual(read(db, 'x')['body'], 'Sem rede')
            self.assertIsNone(read(db, 'missing'))

if __name__ == '__main__':
    unittest.main()
