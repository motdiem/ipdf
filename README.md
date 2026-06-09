# ipdf

Turn a **Markdown** or **Word (`.docx`)** document into a PDF that's genuinely
pleasant to read on an iPhone.

It keeps your document's structure and styling — headings, **bold**, *italic*,
lists, tables, blockquotes, code, links, images — and renders it onto a small,
phone-shaped page with a font, size, and margins chosen for on-screen reading.

```
ipdf notes.md
ipdf report.docx -o report.pdf --theme dark
```

## Why it reads well on a phone

When you read a PDF on a phone you almost always **fit it to the screen width**.
At that point the absolute paper size is irrelevant — what matters is the *ratio*
between the body font and the page width. ipdf leans into that:

- **Phone-shaped page.** The default page is `3.5" × 7.58"` — the ~19.5∶9 aspect
  ratio of a modern iPhone — so a page maps roughly to a screenful and "fit to
  width" makes the text appear large.
- **Comfortable measure.** A small page plus an ~11 pt body font yields a short
  line length (~35–45 characters), the sweet spot for narrow-column reading.
- **Screen-first typography.** A clean sans-serif stack, `1.5` line height, and
  ragged-right text with automatic hyphenation.
- **Nothing clipped.** Long code lines wrap, big words break, and images scale
  down to fit the page.
- **Dark / sepia themes** for night and low-glare reading.

## Install

Requires Python 3.9+. [WeasyPrint](https://weasyprint.org) (the PDF engine)
needs its native libraries — Pango, cairo, GDK-PixBuf — which are present on
most Linux/macOS setups (`brew install weasyprint` pulls them on macOS).

```bash
pip install .
# or, without installing the package:
pip install -r requirements.txt
python -m ipdf --help
```

## Usage

```
ipdf INPUT [-o OUTPUT] [options]
```

| Option            | Description                                                        |
| ----------------- | ------------------------------------------------------------------ |
| `-o, --output`    | Output PDF path (default: input name with a `.pdf` suffix)         |
| `--preset`        | iPhone page preset: `iphone`, `iphone-mini`, `iphone-max`, `iphone-se` |
| `--page-size`     | Custom size, overrides preset: e.g. `3.5x7.6in`, `90x195mm`        |
| `--margin`        | Page margin in inches (default `0.3`)                              |
| `--font`          | `sans` (default), `serif`, `mono`, or a literal family name        |
| `--font-size`     | Body font size in points (default: preset-specific, ~11 pt)        |
| `--line-height`   | Line height multiple (default `1.5`)                               |
| `--theme`         | `light` (default), `dark`, `sepia`                                 |
| `--no-hyphens`    | Disable automatic hyphenation                                      |
| `--title`         | PDF title (default: first H1, else the file name)                  |
| `-q, --quiet`     | Suppress non-error output                                          |

### Examples

```bash
# Quickest path — writes notes.pdf next to the source
ipdf notes.md

# A Word doc, dark theme, larger Pro Max page
ipdf report.docx --preset iphone-max --theme dark

# Serif body at 12 pt for long-form reading
ipdf book.md --font serif --font-size 12

# A fully custom page in millimetres
ipdf memo.md --page-size 90x195mm --margin 0.25
```

Try it on the bundled sample:

```bash
ipdf examples/sample.md -o sample.pdf
```

## Use as a library

```python
from ipdf import convert
from ipdf.converter import RenderOptions

convert(
    "notes.md",
    "notes.pdf",
    RenderOptions(page_preset="iphone-max", theme="dark", font="serif"),
)
```

`ipdf.converter.render()` returns the PDF bytes plus the intermediate HTML and
detected title if you'd rather not write to disk.

## Web frontend

There's also a tiny drag-and-drop web app: drop a Markdown or `.docx` file onto
the page and the converted PDF downloads automatically. All the conversion
options live behind a ⚙️ settings panel (iPhone model, theme, font, font size,
margin, line height, hyphenation, title).

```bash
pip install ".[web]"        # or: pip install -r webapp/requirements.txt
python -m webapp            # serves http://127.0.0.1:5000
```

Options:

```bash
python -m webapp --host 0.0.0.0 --port 8080   # expose on the network
```

Files are converted in memory and never written to disk beyond a short-lived
temp file during conversion. Uploads are capped at 25 MB.

> The bundled server is Flask's development server — fine for personal/local
> use. To host it for others, put it behind a production WSGI server, e.g.
> `gunicorn webapp.app:app`.

## How it works

```
Markdown ──(python-markdown)──┐
                              ├──> HTML ──(WeasyPrint + tuned CSS)──> PDF
Word .docx ──(mammoth)────────┘
```

- **Markdown** is parsed with `python-markdown` (`extra`, `sane_lists`,
  `smarty`, `admonition`, `toc`) so tables, fenced code, footnotes, definition
  lists, and typographic quotes all come through.
- **`.docx`** is converted with `mammoth`, which maps Word's semantic styles
  (headings, bold/italic, lists, tables) to clean HTML and inlines images.
- The HTML is wrapped in a stylesheet (`ipdf/styles.py`) whose `@page` size,
  font, margins, and colours are computed from your options, then rendered by
  **WeasyPrint**.

## Development

```bash
python -m unittest        # run the test suite
```

## License

MIT — see [LICENSE](LICENSE).
