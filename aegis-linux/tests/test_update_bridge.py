"""Loopback authorization and job boundaries, all state in temporary directories."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from updater import Manager, UpdateError
from update_bridge import Bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = Manager(self.root / 'managed', self.root / 'trust', SOURCE)
        self.manager.bootstrap()
        self.bridge = Bridge(self.manager, self.manager.boot())
        self.url = self.bridge.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.bridge.close)

    def request(self, method, path, body=None, authenticated=True, origin=None, host=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.bridge.server.server_port, timeout=5)
        headers = {}
        if authenticated:
            headers.update({'X-Aegis-Token': self.bridge.token, 'Origin': origin or self.bridge.origin})
        if host:
            headers['Host'] = host
        raw = json.dumps(body).encode() if isinstance(body, dict) else body
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        code, data, response_headers = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return code, data, response_headers

    def done(self):
        deadline = time.monotonic() + 5
        while self.bridge.status()['job']['busy'] and time.monotonic() < deadline:
            threading.Event().wait(.01)
        self.assertFalse(self.bridge.status()['job']['busy'])

    def test_loopback_static_and_no_directory_or_trust_exposure(self):
        self.assertEqual(self.bridge.server.server_address[0], '127.0.0.1')
        code, data, headers = self.request('GET', '/')
        self.assertEqual(code, 200)
        self.assertIn(self.bridge.token.encode(), data)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        for path in ['/../updater.py', '/%2e%2e/updater.py', '/vendor/', '/trusted-keys/private.pem']:
            self.assertEqual(self.request('GET', path)[0], 404)

    def test_requires_token_origin_and_exact_host(self):
        self.assertEqual(self.request('GET', '/api/status', authenticated=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/restore', {}, authenticated=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/restore', {}, origin='https://evil.example')[0], 403)
        self.assertEqual(self.request('GET', '/', host='evil.example')[0], 403)
        self.assertEqual(self.request('GET', '/api/status')[0], 200)

    def test_invalid_import_and_install_id_do_not_mutate(self):
        before = self.manager.state()
        self.assertEqual(self.request('POST', '/api/import', b'not a package')[0], 202)
        self.done()
        self.assertTrue(self.bridge.status()['job']['error'])
        self.assertIsNone(self.bridge.status()['candidate'])
        self.assertFalse(self.bridge.package.exists())
        self.assertEqual(self.manager.state(), before)
        self.assertEqual(self.request('POST', '/api/install', {'id': 'invented'})[0], 202)
        self.done()
        self.assertIn('Confira novamente', self.bridge.status()['job']['message'])
        self.assertEqual(self.manager.state(), before)

    def test_busy_operations_and_no_silent_online_install(self):
        release = threading.Event()
        entered = threading.Event()
        def blocking():
            entered.set()
            release.wait(5)
            raise UpdateError('Sem internet simulada')
        try:
            with patch.object(self.bridge, 'check', side_effect=blocking):
                self.assertEqual(self.request('POST', '/api/check', {})[0], 202)
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.request('POST', '/api/import', b'x')[0], 400)
                self.assertEqual(self.request('POST', '/api/restore', {})[0], 400)
                self.assertIsNone(self.manager.state()['pending'])
        finally:
            release.set()
        self.done()
        self.assertTrue(self.bridge.status()['job']['error'])


if __name__ == '__main__':
    unittest.main()
