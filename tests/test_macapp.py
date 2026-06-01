"""Tests for the macOS desktop wrapper's non-GUI logic.

The GUI itself (pywebview / WKWebView) can't run headless, so these cover the
parts that can: PDF saving, port selection, and the embedded Flask server.
Skipped if the web dependencies aren't installed.
"""

import base64
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from macapp.app import FlaskServerThread, find_free_port, write_pdf
    HAVE_DEPS = True
except Exception:  # pragma: no cover - deps missing
    HAVE_DEPS = False

FAKE_PDF = b"%PDF-1.4 fake bytes"


@unittest.skipUnless(HAVE_DEPS, "web/desktop deps not installed")
class WritePdfTests(unittest.TestCase):
    def test_writes_decoded_bytes(self):
        with TemporaryDirectory() as d:
            out = Path(d) / "out.pdf"
            b64 = base64.b64encode(FAKE_PDF).decode()
            saved = write_pdf(out, b64)
            self.assertEqual(saved, out)
            self.assertEqual(out.read_bytes(), FAKE_PDF)

    def test_forces_pdf_suffix(self):
        with TemporaryDirectory() as d:
            out = Path(d) / "out"  # no suffix
            saved = write_pdf(out, base64.b64encode(FAKE_PDF).decode())
            self.assertEqual(saved.suffix, ".pdf")
            self.assertTrue(saved.exists())


@unittest.skipUnless(HAVE_DEPS, "web/desktop deps not installed")
class FreePortTests(unittest.TestCase):
    def test_returns_usable_port(self):
        port = find_free_port()
        self.assertIsInstance(port, int)
        self.assertGreater(port, 0)


@unittest.skipUnless(HAVE_DEPS, "web/desktop deps not installed")
class EmbeddedServerTests(unittest.TestCase):
    def test_server_serves_the_flask_app(self):
        server = FlaskServerThread()
        server.start()
        try:
            with urllib.request.urlopen(server.url, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read()
            self.assertIn(b"IPDF_CHOICES", body)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
