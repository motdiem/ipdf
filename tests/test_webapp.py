"""Tests for the Flask web frontend (uses the test client, no browser needed).

Skipped automatically if Flask isn't installed.

Run with:  python -m unittest tests.test_webapp
"""

import io
import unittest

try:
    from webapp.app import app
    HAVE_FLASK = True
except Exception:  # pragma: no cover - flask not installed
    HAVE_FLASK = False

SAMPLE_MD = b"# Web Title\n\nSome **bold** and *italic* text.\n\n- a\n- b\n"


@unittest.skipUnless(HAVE_FLASK, "Flask not installed")
class WebAppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_index_serves_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"IPDF_CHOICES", resp.data)

    def test_options_endpoint(self):
        resp = self.client.get("/api/options")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("presets", data)
        self.assertIn("themes", data)
        self.assertIn("fonts", data)

    def _post(self, data):
        return self.client.post(
            "/convert", data=data, content_type="multipart/form-data"
        )

    def test_convert_markdown_returns_pdf(self):
        resp = self._post(
            {
                "file": (io.BytesIO(SAMPLE_MD), "note.md"),
                "theme": "dark",
                "preset": "iphone-max",
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/pdf")
        self.assertTrue(resp.data.startswith(b"%PDF-"))
        self.assertIn("note.pdf", resp.headers.get("Content-Disposition", ""))

    def test_convert_rejects_unknown_extension(self):
        resp = self._post({"file": (io.BytesIO(b"hi"), "bad.rtf")})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported", resp.get_json()["error"])

    def test_convert_requires_file(self):
        resp = self._post({"theme": "light"})
        self.assertEqual(resp.status_code, 400)

    def test_convert_rejects_bad_option(self):
        resp = self._post(
            {"file": (io.BytesIO(SAMPLE_MD), "note.md"), "preset": "nope"}
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
