"""Security-focused tests: url_fetcher policy, font sanitisation, zip-bomb
guard, numeric bounds, and the hardened web endpoints.
"""

import io
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from ipdf.converter import RenderOptions, ConversionError, render
from ipdf.security import (
    SecurityError,
    build_url_fetcher,
    check_archive_safety,
    sanitize_font_family,
)

try:
    from webapp.app import app as flask_app
    from webapp.app import _render_slots
    HAVE_FLASK = True
except Exception:  # pragma: no cover
    HAVE_FLASK = False


def _is_pdf(b):
    return b[:5] == b"%PDF-"


class UrlFetcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        self.addCleanup(self.tmp.cleanup)

    def test_data_uri_always_allowed(self):
        f = build_url_fetcher(self.base, allow_local_files=False, allow_remote=False)
        # Should not raise; the exact return shape varies across WeasyPrint
        # versions (dict vs URLFetcherResponse), so just assert we got something.
        result = f("data:text/plain;base64,aGVsbG8=")  # "hello"
        self.assertIsNotNone(result)

    def test_local_file_allowed_inside_base(self):
        f = build_url_fetcher(self.base, allow_local_files=True, allow_remote=False)
        result = f((self.base / "img.png").as_uri())
        self.assertTrue(result)

    def test_local_file_blocked_outside_base(self):
        f = build_url_fetcher(self.base, allow_local_files=True, allow_remote=False)
        with self.assertRaises(SecurityError):
            f("file:///etc/passwd")

    def test_local_file_blocked_when_disabled(self):
        f = build_url_fetcher(self.base, allow_local_files=False, allow_remote=False)
        with self.assertRaises(SecurityError):
            f((self.base / "img.png").as_uri())

    def test_remote_blocked_when_disabled(self):
        f = build_url_fetcher(self.base, allow_local_files=False, allow_remote=False)
        with self.assertRaises(SecurityError):
            f("http://example.com/x.png")

    def test_remote_private_and_metadata_blocked(self):
        f = build_url_fetcher(self.base, allow_local_files=False, allow_remote=True)
        for url in (
            "http://127.0.0.1/x",
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://10.0.0.1/",
            "http://192.168.1.1/",
        ):
            with self.assertRaises(SecurityError, msg=url):
                f(url)

    def test_unknown_scheme_blocked(self):
        f = build_url_fetcher(self.base, allow_local_files=True, allow_remote=True)
        with self.assertRaises(SecurityError):
            f("javascript:alert(1)")


class FontSanitisationTests(unittest.TestCase):
    def test_accepts_normal_families(self):
        self.assertEqual(
            sanitize_font_family('"My Font", sans-serif'), '"My Font", sans-serif'
        )
        self.assertEqual(sanitize_font_family("Helvetica Neue"), "Helvetica Neue")

    def test_rejects_injection(self):
        for bad in (
            "Arial; @import url(http://evil)",
            "a(url(x))",
            "X{ color:red }",
            "A;B",
            "Font</style><script>",
            "x" * 300,
        ):
            with self.assertRaises(SecurityError, msg=bad):
                sanitize_font_family(bad)

    def test_render_rejects_unsafe_literal_font(self):
        with TemporaryDirectory() as d:
            md = Path(d) / "a.md"
            md.write_text("# h\n")
            with self.assertRaises(ConversionError):
                render(md, RenderOptions(font="Arial; @import url(http://evil)"))


class ArchiveBombTests(unittest.TestCase):
    def _zip_with(self, name, data):
        buf = Path(self.d) / name
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("word/document.xml", data)
        return buf

    def setUp(self):
        self._t = TemporaryDirectory()
        self.d = self._t.name
        self.addCleanup(self._t.cleanup)

    def test_high_ratio_rejected(self):
        bomb = self._zip_with("bomb.docx", b"\x00" * (16 * 1024 * 1024))  # ~1000x
        with self.assertRaises(SecurityError):
            check_archive_safety(bomb)

    def test_total_size_cap_rejected(self):
        small = self._zip_with("d.docx", b"A" * 1024)
        with self.assertRaises(SecurityError):
            check_archive_safety(small, max_total_bytes=100)  # force the cap

    def test_normal_archive_passes(self):
        ok = self._zip_with("ok.docx", b"<xml>hello world</xml>" * 50)
        check_archive_safety(ok)  # should not raise

    def test_bad_zip_rejected(self):
        notzip = Path(self.d) / "x.docx"
        notzip.write_bytes(b"not a zip")
        with self.assertRaises(SecurityError):
            check_archive_safety(notzip)


class NumericBoundsTests(unittest.TestCase):
    def test_nan_and_out_of_range_rejected(self):
        for kw in (
            {"margin": float("nan")},
            {"margin": float("inf")},
            {"font_size": 999},
            {"font_size": 0},
            {"line_height": -1},
            {"margin": -0.5},
        ):
            with self.assertRaises(ConversionError, msg=str(kw)):
                RenderOptions(**kw).resolved()

    def test_in_range_accepted(self):
        RenderOptions(margin=0.5, font_size=12, line_height=1.4).resolved()


class SsrfIntegrationTests(unittest.TestCase):
    def test_markdown_file_reference_does_not_leak(self):
        with TemporaryDirectory() as d:
            secret = Path(d) / "secret.txt"
            secret.write_text("TOPSECRET-PAYLOAD-XYZ")
            md = Path(d) / "doc.md"
            md.write_text(f"# Title\n\n![x]({secret.as_uri()})\n\nbody\n")
            result = render(md, RenderOptions(allow_local_files=False))
            self.assertTrue(_is_pdf(result.pdf_bytes))
            self.assertNotIn(b"TOPSECRET", result.pdf_bytes)


@unittest.skipUnless(HAVE_FLASK, "Flask not installed")
class WebHardeningTests(unittest.TestCase):
    def setUp(self):
        flask_app.config.update(TESTING=True)
        self.client = flask_app.test_client()

    def _post(self, data):
        return self.client.post(
            "/convert", data=data, content_type="multipart/form-data"
        )

    def test_security_headers_present(self):
        resp = self.client.get("/")
        self.assertIn("Content-Security-Policy", resp.headers)
        self.assertNotIn("unsafe-inline", resp.headers["Content-Security-Policy"])
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")

    def test_unknown_font_rejected(self):
        resp = self._post(
            {"file": (io.BytesIO(b"# hi\n"), "a.md"), "font": "Comic; @import url(x)"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_bad_numbers_rejected(self):
        for field, value in (("margin", "nan"), ("font_size", "999"), ("margin", "-1")):
            resp = self._post(
                {"file": (io.BytesIO(b"# hi\n"), "a.md"), field: value}
            )
            self.assertEqual(resp.status_code, 400, f"{field}={value}")

    def test_busy_returns_503(self):
        sem = _render_slots
        acquired = 0
        while sem.acquire(blocking=False):
            acquired += 1
        try:
            resp = self._post({"file": (io.BytesIO(b"# hi\n"), "a.md")})
            self.assertEqual(resp.status_code, 503)
        finally:
            for _ in range(acquired):
                sem.release()


if __name__ == "__main__":
    unittest.main()
