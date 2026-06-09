"""Command line interface for ipdf."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import __version__
from .converter import ConversionError, RenderOptions, render
from .styles import FONT_STACKS, PAGE_PRESETS, THEMES

_SIZE_RE = re.compile(
    r"^\s*([0-9]*\.?[0-9]+)\s*[xX*]\s*([0-9]*\.?[0-9]+)\s*(in|mm|cm|pt)?\s*$"
)

_UNIT_TO_INCHES = {
    "in": 1.0,
    "mm": 1.0 / 25.4,
    "cm": 1.0 / 2.54,
    "pt": 1.0 / 72.0,
}


def _parse_page_size(value: str) -> tuple[float, float]:
    """Parse a ``WxH`` custom page size (default unit: inches) into inches."""
    match = _SIZE_RE.match(value)
    if not match:
        raise argparse.ArgumentTypeError(
            f"Invalid page size {value!r}. Use e.g. '3.5x7.6in', '90x195mm'."
        )
    width, height, unit = match.groups()
    factor = _UNIT_TO_INCHES[unit or "in"]
    return float(width) * factor, float(height) * factor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ipdf",
        description=(
            "Convert a Markdown or Word (.docx) document into a PDF tuned for "
            "comfortable reading on an iPhone."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  ipdf notes.md\n"
            "  ipdf report.docx -o report.pdf --theme dark\n"
            "  ipdf book.md --preset iphone-max --font serif --font-size 12\n"
            "  ipdf memo.md --page-size 90x195mm --margin 0.25\n"
        ),
    )
    parser.add_argument("input", help="Path to the .md / .markdown / .docx file")
    parser.add_argument(
        "-o",
        "--output",
        help="Output PDF path (default: same name as input with a .pdf suffix)",
    )

    layout = parser.add_argument_group("page & layout")
    layout.add_argument(
        "--preset",
        default="iphone",
        choices=sorted(PAGE_PRESETS),
        help="iPhone screen preset to size the page (default: iphone)",
    )
    layout.add_argument(
        "--page-size",
        type=_parse_page_size,
        metavar="WxH[unit]",
        help="Custom page size, overriding --preset (e.g. 3.5x7.6in, 90x195mm)",
    )
    layout.add_argument(
        "--margin",
        type=float,
        default=0.3,
        metavar="INCHES",
        help="Page margin in inches (default: 0.3)",
    )

    typo = parser.add_argument_group("typography")
    typo.add_argument(
        "--font",
        default="sans",
        metavar="NAME",
        help=(
            "Font: a preset (" + ", ".join(sorted(FONT_STACKS)) + ") "
            "or a literal family name (default: sans)"
        ),
    )
    typo.add_argument(
        "--font-size",
        type=float,
        metavar="PT",
        help="Body font size in points (default: preset-specific, ~11pt)",
    )
    typo.add_argument(
        "--line-height",
        type=float,
        default=1.5,
        metavar="N",
        help="Line height as a multiple of font size (default: 1.5)",
    )
    typo.add_argument(
        "--theme",
        default="light",
        choices=sorted(THEMES),
        help="Colour theme (default: light)",
    )
    typo.add_argument(
        "--no-hyphens",
        action="store_true",
        help="Disable automatic hyphenation",
    )
    typo.add_argument(
        "--title",
        help="Document title for PDF metadata (default: first H1 or file name)",
    )

    security = parser.add_argument_group("resource policy (security)")
    security.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow fetching remote http(s) resources referenced by the document "
        "(off by default; public hosts only, private/loopback IPs are blocked)",
    )
    security.add_argument(
        "--no-local-files",
        action="store_true",
        help="Disallow reading local files referenced by the document "
        "(by default, local files beside the source are allowed)",
    )

    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress non-error output"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    options = RenderOptions(
        page_preset=args.preset,
        margin=args.margin,
        font=args.font,
        font_size=args.font_size,
        line_height=args.line_height,
        theme=args.theme,
        hyphenate=not args.no_hyphens,
        title=args.title,
        allow_local_files=not args.no_local_files,
        allow_remote=args.allow_remote,
    )
    if args.page_size is not None:
        options.page_width, options.page_height = args.page_size

    try:
        result = render(args.input, options=options)
    except ConversionError as exc:
        print(f"ipdf: error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - unexpected failures
        print(f"ipdf: unexpected error: {exc}", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result.pdf_bytes)

    if not args.quiet:
        for warning in result.warnings:
            print(f"ipdf: warning: {warning}", file=sys.stderr)
        size_kb = len(result.pdf_bytes) / 1024
        print(
            f"Wrote {output_path} "
            f"({result.source_format} -> PDF, {size_kb:.0f} KB, "
            f"theme={args.theme}, preset={args.preset})"
        )

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
