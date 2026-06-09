"""Styling primitives and the CSS template used to render iPhone-friendly PDFs.

The numbers here are tuned for *on-screen* reading rather than print. The guiding
idea: a reader views the PDF on an iPhone with "fit to width", so what matters is
the ratio between the body font size and the page width (not the absolute physical
page size). A small page with a relatively large font means the text appears big
and the line length stays short (~35-45 characters), which is the comfortable
reading "measure" for a phone-width column.
"""

from string import Template

# ---------------------------------------------------------------------------
# Page presets. Heights are derived from the screen aspect ratio of each model
# so that a single PDF page maps roughly to a single screenful in portrait.
# Sizes are in inches. The physical size is arbitrary for on-screen reading;
# the font-size-to-width ratio is what actually drives legibility.
# ---------------------------------------------------------------------------
PAGE_PRESETS = {
    # name            width  height  body font (pt)
    "iphone":      {"width": 3.50, "height": 7.58, "font_size": 11.0},  # 6.1" class, 19.5:9
    "iphone-mini": {"width": 3.40, "height": 7.36, "font_size": 11.0},  # mini, 19.5:9
    "iphone-max":  {"width": 3.80, "height": 8.23, "font_size": 12.0},  # Pro Max, 19.5:9
    "iphone-se":   {"width": 3.40, "height": 6.03, "font_size": 11.0},  # SE / classic 16:9
}

DEFAULT_PRESET = "iphone"

# ---------------------------------------------------------------------------
# Font stacks. The first available family on the rendering machine wins; the
# generic family at the end guarantees a fallback. Sans-serif is the default
# because it reads best on the relatively low DPI of a phone at small sizes.
# ---------------------------------------------------------------------------
FONT_STACKS = {
    "sans": '"Helvetica Neue", Helvetica, Arial, "Liberation Sans", '
            '"DejaVu Sans", sans-serif',
    "serif": '"Iowan Old Style", Charter, "Bitstream Charter", Georgia, '
             '"Liberation Serif", "DejaVu Serif", serif',
    "mono": '"SF Mono", "DejaVu Sans Mono", "Liberation Mono", Menlo, '
            'Consolas, monospace',
}

DEFAULT_FONT = "sans"

# Monospace stack reused for code blocks regardless of the body font choice.
MONO_STACK = FONT_STACKS["mono"]

# ---------------------------------------------------------------------------
# Colour themes. Each theme defines the handful of colours the stylesheet needs.
# ---------------------------------------------------------------------------
THEMES = {
    "light": {
        "bg": "#ffffff",
        "fg": "#1a1a1a",
        "muted": "#6b6b6b",
        "heading": "#000000",
        "link": "#0a66c2",
        "rule": "#e2e2e2",
        "code_bg": "#f4f4f6",
        "code_fg": "#1a1a1a",
        "quote_bar": "#d0d0d0",
        "quote_fg": "#444444",
        "table_border": "#dddddd",
        "table_head_bg": "#f4f4f6",
    },
    "dark": {
        "bg": "#1c1c1e",
        "fg": "#e6e6ea",
        "muted": "#9a9aa2",
        "heading": "#ffffff",
        "link": "#5ab0ff",
        "rule": "#3a3a3e",
        "code_bg": "#2c2c2f",
        "code_fg": "#f2f2f4",
        "quote_bar": "#48484c",
        "quote_fg": "#bcbcc2",
        "table_border": "#3a3a3e",
        "table_head_bg": "#2c2c2f",
    },
    "sepia": {
        "bg": "#faf3e3",
        "fg": "#3a3128",
        "muted": "#7c7059",
        "heading": "#2b2319",
        "link": "#9a5b2c",
        "rule": "#e4d9bf",
        "code_bg": "#f1e7cf",
        "code_fg": "#3a3128",
        "quote_bar": "#d8c9a4",
        "quote_fg": "#5f5440",
        "table_border": "#e0d4b6",
        "table_head_bg": "#f1e7cf",
    },
}

DEFAULT_THEME = "light"


# string.Template is used (rather than str.format / f-strings) because CSS is
# full of literal { } braces; $-substitution keeps the template readable.
_CSS_TEMPLATE = Template(
    """
@page {
    size: ${page_width}in ${page_height}in;
    margin: ${margin}in ${margin}in;
    background: ${bg};
}

html {
    /* Avoid runaway font scaling and keep colours sane. */
    -weasy-hyphens: auto;
}

body {
    background: ${bg};
    color: ${fg};
    font-family: ${body_font};
    font-size: ${font_size}pt;
    line-height: ${line_height};
    margin: 0;
    padding: 0;
    /* Ragged-right with hyphenation reads best in a narrow column. */
    text-align: left;
    hyphens: auto;
    -webkit-hyphens: auto;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

article {
    /* Long words / URLs should wrap instead of overflowing the page. */
    overflow-wrap: break-word;
}

/* ------------------------------- headings ------------------------------- */
h1, h2, h3, h4, h5, h6 {
    color: ${heading};
    font-weight: 700;
    line-height: 1.25;
    margin: 1.1em 0 0.45em;
    -weasy-hyphens: none;
    hyphens: none;
}
h1 { font-size: 1.7em; margin-top: 0; }
h2 { font-size: 1.4em; }
h3 { font-size: 1.2em; }
h4 { font-size: 1.05em; }
h5 { font-size: 1.0em; text-transform: uppercase; letter-spacing: 0.03em; }
h6 { font-size: 0.9em; color: ${muted}; text-transform: uppercase; letter-spacing: 0.03em; }

/* keep a heading attached to the text that follows it */
h1, h2, h3, h4, h5, h6 { break-after: avoid; }

/* ------------------------------- text ----------------------------------- */
p { margin: 0 0 0.75em; }

strong, b { font-weight: 700; }
em, i { font-style: italic; }
strong em, em strong { font-weight: 700; font-style: italic; }
mark { background: ${quote_bar}; color: ${fg}; padding: 0 0.1em; }
small { font-size: 0.85em; color: ${muted}; }
sub, sup { font-size: 0.7em; line-height: 0; }

a { color: ${link}; text-decoration: none; }

/* ------------------------------- lists ---------------------------------- */
ul, ol { margin: 0 0 0.75em; padding-left: 1.3em; }
li { margin: 0.15em 0; }
li > ul, li > ol { margin: 0.15em 0; }
dl { margin: 0 0 0.75em; }
dt { font-weight: 700; }
dd { margin: 0 0 0.4em 1.2em; }

/* task lists (markdown checkboxes) */
li input[type="checkbox"] { margin-right: 0.4em; }

/* ----------------------------- blockquote ------------------------------- */
blockquote {
    margin: 0.8em 0;
    padding: 0.1em 0 0.1em 0.9em;
    border-left: 3px solid ${quote_bar};
    color: ${quote_fg};
}
blockquote p:last-child { margin-bottom: 0; }

/* ------------------------------- code ----------------------------------- */
code, kbd, samp, pre {
    font-family: ${mono_font};
}
code {
    background: ${code_bg};
    color: ${code_fg};
    padding: 0.1em 0.3em;
    border-radius: 3px;
    font-size: 0.88em;
    word-wrap: break-word;
}
pre {
    background: ${code_bg};
    color: ${code_fg};
    padding: 0.7em 0.8em;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 0.82em;
    line-height: 1.4;
    /* Wrap long lines so nothing is clipped off the narrow page. */
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
}
pre code {
    background: transparent;
    padding: 0;
    border-radius: 0;
    font-size: inherit;
}

/* ------------------------------- media ---------------------------------- */
img {
    max-width: 100%;
    height: auto;
}
figure { margin: 0.9em 0; }
figcaption { font-size: 0.82em; color: ${muted}; text-align: center; }

/* --------------------------------- hr ----------------------------------- */
hr {
    border: none;
    border-top: 1px solid ${rule};
    margin: 1.2em 0;
}

/* ------------------------------- tables --------------------------------- */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.8em 0;
    font-size: 0.82em;
}
th, td {
    border: 1px solid ${table_border};
    padding: 0.35em 0.5em;
    text-align: left;
    vertical-align: top;
}
thead th { background: ${table_head_bg}; }

/* ------------------------------ footnotes ------------------------------- */
.footnote, .footnotes { font-size: 0.82em; color: ${muted}; }
.footnotes hr { margin-top: 1.6em; }
sup.footnote-ref a, a.footnote-ref { text-decoration: none; }
"""
)


def build_css(
    *,
    page_width: float,
    page_height: float,
    margin: float,
    font_size: float,
    line_height: float,
    body_font: str,
    theme: str = DEFAULT_THEME,
    mono_font: str = MONO_STACK,
) -> str:
    """Render the CSS for the given typographic parameters and theme."""
    colours = THEMES[theme]
    return _CSS_TEMPLATE.substitute(
        page_width=_fmt(page_width),
        page_height=_fmt(page_height),
        margin=_fmt(margin),
        font_size=_fmt(font_size),
        line_height=_fmt(line_height),
        body_font=body_font,
        mono_font=mono_font,
        **colours,
    )


def _fmt(value: float) -> str:
    """Format a float without a trailing ``.0`` so the CSS stays tidy."""
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text or "0"
