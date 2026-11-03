import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aegis", SOURCE / "aegis.py")
aegis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aegis)
REQUIRE_LINUX = aegis.require_linux


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="aegis-test-", dir=SOURCE / "tests")
        Path(self.workspace.name).resolve().relative_to((SOURCE / "tests").resolve())
        self.addCleanup(self.workspace.cleanup)
        self.base = Path(self.workspace.name)
        self.target = self.base / "data" / "aegis-prototipo"
        self.menu = self.base / "applications" / "aegis-prototipo.desktop"
        self.start = self.base / "autostart" / "aegis-prototipo.desktop"
        for name, value in [("locations", (self.target, self.menu, self.start)),
                            ("require_linux", None), ("browser_path", "/usr/bin/chromium")]:
            mocked = patch.object(aegis, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_install_creates_app_but_not_autostart(self):
        aegis.install()
        self.assertTrue((self.target / "app/index.html").is_file())
        self.assertIn("X-AEGIS-Prototype=true", self.menu.read_text(encoding="utf-8"))
        self.assertFalse(self.start.exists())

    def test_duplicate_install_preserves_existing_files(self):
        self.target.mkdir(parents=True)
        existing = self.target / "personal.txt"
        existing.write_text("preserve", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            aegis.install()
        self.assertEqual(existing.read_text(), "preserve")
        self.assertFalse(self.menu.exists())

    def test_install_requires_browser_before_writing(self):
        with patch.object(aegis, "browser_path", return_value=None):
            with self.assertRaises(RuntimeError):
                aegis.install()
        self.assertFalse(self.target.exists())

    def test_autostart_enable_disable(self):
        aegis.install()
        aegis.autostart(True)
        self.assertIn('--kiosk', self.start.read_text(encoding="utf-8"))
        aegis.autostart(False)
        self.assertFalse(self.start.exists())
        self.assertTrue(self.menu.exists())

    def test_unowned_autostart_is_never_changed(self):
        self.start.parent.mkdir(parents=True)
        self.start.write_text("personal entry", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            aegis.autostart(False)
        self.assertEqual(self.start.read_text(), "personal entry")

    def test_launch_uses_file_uri_and_preserves_sandbox(self):
        args = aegis.command(SOURCE, "/usr/bin/chromium", True, self.base / "profile with spaces")
        self.assertIn("--kiosk", args)
        self.assertTrue(args[-1].startswith("file:///"))
        self.assertNotIn("--no-sandbox", args)
        self.assertNotIn("--disable-web-security", args)
        self.assertTrue(any("profile with spaces" in item for item in args))

    def test_desktop_argument_escapes_special_characters(self):
        value = aegis.desktop_arg('/home/A B/$user/100%/a"b')
        self.assertEqual(value, '"/home/A B/\\\\$user/100%%/a\\\\"b"')
        with self.assertRaises(RuntimeError):
            aegis.desktop_arg("path\nExec=bad")

    def test_windows_install_is_rejected(self):
        with patch.object(aegis.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(RuntimeError, "Execute esta operação no Linux"):
                REQUIRE_LINUX()
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
