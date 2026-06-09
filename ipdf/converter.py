"""Core conversion pipeline: Markdown / DOCX -> HTML -> iPhone-optimised PDF."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .styles import (
    DEFAULT_FONT,
    DEFAULT_PRESET,
    DEFAULT_THEME,
    FONT_STACKS,
    PAGE_PRESETS,
    THEMES,
    build_css,
)

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".text"}
DOCX_SUFFIXES = {".docx"}


class ConversionError(Exception):
    """Raised when an input cannot be converted (bad format, missing file...)."""


@dataclass
class RenderOptions:
    """Typographic and layout knobs for a single conversion."""

    page_preset: str = DEFAULT_PRESET
    # Explicit overrides; when None the preset value is used.
    page_width: Optional[float] = None   # inches
    page_height: Optional[float] = None  # inches
    margin: float = 0.3                  # inches
    font: str = DEFAULT_FONT             # key in FONT_STACKS or a literal family
    font_size: Optional[float] = None    # pt; None -> preset default
    line_height: float = 1.5
    theme: str = DEFAULT_THEME
    hyphenate: bool = True
    title: Optional[str] = None

    def resolved(self) -> "ResolvedOptions":
        if self.page_preset not in PAGE_PRESETS:
            raise ConversionError(
                f"Unknown page preset {self.page_preset!r}. "
                f"Choose from: {', '.join(sorted(PAGE_PRESETS))}."
            )
        if self.theme not in THEMES:
            raise ConversionError(
                f"Unknown theme {self.theme!r}. "
                f"Choose from: {', '.join(sorted(THEMES))}."
            )
        preset = PAGE_PRESETS[self.page_preset]
        width = self.page_width if self.page_width is not None else preset["width"]
        height = self.page_height if self.page_height is not None else preset["height"]
        font_size = self.font_size if self.font_size is not None else preset["font_size"]
        body_font = FONT_STACKS.get(self.font, self.font)
        return ResolvedOptions(
            page_width=width,
            page_height=height,
            margin=self.margin,
            font_size=font_size,
            line_height=self.line_height,
            body_font=body_font,
            theme=self.theme,
            hyphenate=self.hyphenate,
            title=self.title,
        )


@dataclass
class ResolvedOptions:
    page_width: float
    page_height: float
    margin: float
    font_size: float
    line_height: float
    body_font: str
    theme: str
    hyphenate: bool
    title: Optional[str]


@dataclass
class ConversionResult:
    pdf_bytes: bytes
    html: str
    title: str
    source_format: str
    warnings: list = field(default_factory=list)


def detect_format(path: Path) -> str:
    """Return ``"markdown"`` or ``"docx"`` based on the file extension."""
    suffix = path.suffix.lower()
    if suffix in MARKDOWN_SUFFIXES:
        return "markdown"
    if suffix in DOCX_SUFFIXES:
        return "docx"
    raise ConversionError(
        f"Unsupported input {path.name!r}. Expected a Markdown "
        f"({', '.join(sorted(MARKDOWN_SUFFIXES))}) or DOCX (.docx) file."
    )


# ---------------------------------------------------------------------------
# Format -> HTML body
# ---------------------------------------------------------------------------
def _markdown_to_html(path: Path) -> tuple[str, list]:
    import markdown

    text = path.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=[
            "extra",        # tables, fenced code, def lists, footnotes, attr lists
            "sane_lists",
            "smarty",       # curly quotes / dashes -> nicer reading
            "admonition",
            "toc",
        ],
        output_format="html",
    )
    body = md.convert(text)
    return body, []


def _docx_to_html(path: Path) -> tuple[str, list]:
    import mammoth

    with path.open("rb") as fh:
        result = mammoth.convert_to_html(fh)
    warnings = [str(m) for m in result.messages]
    return result.value, warnings


def _build_body(path: Path, source_format: str) -> tuple[str, list]:
    if source_format == "markdown":
        return _markdown_to_html(path)
    if source_format == "docx":
        return _docx_to_html(path)
    raise ConversionError(f"Unhandled source format: {source_format!r}")


# ---------------------------------------------------------------------------
# Title detection
# ---------------------------------------------------------------------------
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _derive_title(body_html: str, fallback: str) -> str:
    match = _H1_RE.search(body_html)
    if match:
        text = _TAG_RE.sub("", match.group(1))
        text = html_lib.unescape(text).strip()
        if text:
            return text
    return fallback


# ---------------------------------------------------------------------------
# Assemble the full HTML document
# ---------------------------------------------------------------------------
def _assemble_document(body_html: str, title: str, css: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{html_lib.escape(title)}</title>\n"
        f"<style>{css}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<article>{body_html}</article>\n"
        "</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render(
    input_path: str | Path,
    options: Optional[RenderOptions] = None,
) -> ConversionResult:
    """Convert ``input_path`` to a PDF, returning bytes + metadata in memory."""
    from weasyprint import HTML  # imported lazily; it is the heavy dependency

    options = options or RenderOptions()
    resolved = options.resolved()

    path = Path(input_path)
    if not path.exists():
        raise ConversionError(f"Input file not found: {path}")
    if not path.is_file():
        raise ConversionError(f"Input path is not a file: {path}")

    source_format = detect_format(path)
    body_html, warnings = _build_body(path, source_format)

    title = resolved.title or _derive_title(body_html, path.stem)

    css = build_css(
        page_width=resolved.page_width,
        page_height=resolved.page_height,
        margin=resolved.margin,
        font_size=resolved.font_size,
        line_height=resolved.line_height,
        body_font=resolved.body_font,
        theme=resolved.theme,
    )
    if not resolved.hyphenate:
        css += "\nbody, article { hyphens: manual; -webkit-hyphens: manual; }\n"

    document_html = _assemble_document(body_html, title, css)

    # base_url lets relative image paths in Markdown resolve next to the source.
    pdf_bytes = HTML(
        string=document_html,
        base_url=str(path.resolve().parent),
    ).write_pdf()

    return ConversionResult(
        pdf_bytes=pdf_bytes,
        html=document_html,
        title=title,
        source_format=source_format,
        warnings=warnings,
    )


def convert(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    options: Optional[RenderOptions] = None,
) -> Path:
    """Convert ``input_path`` to a PDF on disk and return the output path."""
    path = Path(input_path)
    result = render(path, options=options)

    if output_path is None:
        output_path = path.with_suffix(".pdf")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result.pdf_bytes)
    return output_path
