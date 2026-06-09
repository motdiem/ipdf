"""Tests for the ipdf conversion pipeline.

Run with:  python -m pytest   (or: python -m unittest)
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ipdf import convert
from ipdf.cli import _parse_page_size, main
from ipdf.converter import (
    ConversionError,
    RenderOptions,
    detect_format,
    render,
)
from ipdf.styles import PAGE_PRESETS, build_css

SAMPLE_MD = """# Hello iPhone

Some **bold**, some *italic*, and `code`.

- one
- two

> a quote

```python
print("hi")
```
"""


def _write(dirpath, name, text):
    path = Path(dirpath) / name
    path.write_text(text, encoding="utf-8")
    return path


def _is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


class FormatDetectionTests(unittest.TestCase):
    def test_markdown_suffixes(self):
        self.assertEqual(detect_format(Path("a.md")), "markdown")
        self.assertEqual(detect_format(Path("a.markdown")), "markdown")

    def test_docx_suffix(self):
        self.assertEqual(detect_format(Path("a.docx")), "docx")

    def test_unsupported_suffix(self):
        with self.assertRaises(ConversionError):
            detect_format(Path("a.rtf"))


class PageSizeParsingTests(unittest.TestCase):
    def test_inches_default(self):
        w, h = _parse_page_size("3.5x7.6")
        self.assertAlmostEqual(w, 3.5)
        self.assertAlmostEqual(h, 7.6)

    def test_millimetres(self):
        w, h = _parse_page_size("90x195mm")
        self.assertAlmostEqual(w, 90 / 25.4, places=4)
        self.assertAlmostEqual(h, 195 / 25.4, places=4)

    def test_invalid(self):
        with self.assertRaises(Exception):
            _parse_page_size("not-a-size")


class CssTests(unittest.TestCase):
    def test_css_contains_page_size_and_theme_colour(self):
        css = build_css(
            page_width=3.5,
            page_height=7.58,
            margin=0.3,
            font_size=11,
            line_height=1.5,
            body_font="sans-serif",
            theme="dark",
        )
        self.assertIn("size: 3.5in 7.58in", css)
        self.assertIn("#1c1c1e", css)  # dark background


class RenderMarkdownTests(unittest.TestCase):
    def test_render_produces_pdf_and_title(self):
        with TemporaryDirectory() as d:
            src = _write(d, "doc.md", SAMPLE_MD)
            result = render(src)
            self.assertTrue(_is_pdf(result.pdf_bytes))
            self.assertEqual(result.title, "Hello iPhone")
            self.assertEqual(result.source_format, "markdown")
            self.assertIn("<strong>bold</strong>", result.html)
            self.assertIn("<em>italic</em>", result.html)

    def test_custom_options(self):
        with TemporaryDirectory() as d:
            src = _write(d, "doc.md", SAMPLE_MD)
            opts = RenderOptions(
                page_preset="iphone-max",
                theme="sepia",
                font="serif",
                font_size=13,
                hyphenate=False,
            )
            result = render(src, options=opts)
            self.assertTrue(_is_pdf(result.pdf_bytes))

    def test_unknown_preset_raises(self):
        with TemporaryDirectory() as d:
            src = _write(d, "doc.md", SAMPLE_MD)
            with self.assertRaises(ConversionError):
                render(src, options=RenderOptions(page_preset="nope"))

    def test_missing_file_raises(self):
        with self.assertRaises(ConversionError):
            render("does-not-exist.md")


class ConvertToDiskTests(unittest.TestCase):
    def test_convert_writes_pdf(self):
        with TemporaryDirectory() as d:
            src = _write(d, "doc.md", SAMPLE_MD)
            out = convert(src)
            self.assertTrue(out.exists())
            self.assertEqual(out.suffix, ".pdf")
            self.assertTrue(_is_pdf(out.read_bytes()))

    def test_convert_explicit_output(self):
        with TemporaryDirectory() as d:
            src = _write(d, "doc.md", SAMPLE_MD)
            out = Path(d) / "nested" / "result.pdf"
            convert(src, out)
            self.assertTrue(out.exists())


class CliTests(unittest.TestCase):
    def test_cli_end_to_end(self):
        with TemporaryDirectory() as d:
            src = _write(d, "doc.md", SAMPLE_MD)
            out = Path(d) / "out.pdf"
            code = main([str(src), "-o", str(out), "--theme", "dark", "-q"])
            self.assertEqual(code, 0)
            self.assertTrue(_is_pdf(out.read_bytes()))

    def test_cli_bad_input_returns_error_code(self):
        code = main(["nope.unknown", "-q"])
        self.assertEqual(code, 2)


class PresetSanityTests(unittest.TestCase):
    def test_presets_have_phoneish_aspect(self):
        for name, p in PAGE_PRESETS.items():
            ratio = p["height"] / p["width"]
            self.assertGreater(ratio, 1.5, f"{name} not portrait enough")
            self.assertLess(ratio, 2.5, f"{name} too tall")


if __name__ == "__main__":
    unittest.main()
