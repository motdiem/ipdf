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

There's also a tiny web app: **drop a Markdown or `.docx` file** onto the page —
or switch to **Paste Markdown** and type/paste content directly (⌘/Ctrl+Enter to
convert) — and the PDF downloads automatically. All the conversion options live
behind a ⚙️ settings panel (iPhone model, theme, font, font size, margin, line
height, hyphenation, title).

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
> use. For hosting, use the Docker image below (it runs gunicorn).

### Run the web app with Docker

The image bundles WeasyPrint's native libraries and fonts and serves the app
with gunicorn (a production WSGI server):

```bash
docker compose up --build      # → http://localhost:8000
# or
docker build -t ipdf-web .
docker run --rm -p 8000:8000 ipdf-web
```

Tunables via environment variables: `PORT`, `GUNICORN_WORKERS`,
`GUNICORN_THREADS`, `GUNICORN_TIMEOUT`, `IPDF_MAX_CONCURRENCY`.

The web service is hardened for untrusted input: documents may only embed
`data:` resources (no local-file or network fetching — SSRF-safe), options are
strictly validated, DOCX zip-bombs are rejected, a concurrency cap sheds load
with `503`, and responses carry a strict CSP + security headers. For
defence-in-depth (edge rate limiting, HTML sanitiser) and the full threat model,
see [docs/ARCHITECTURE.md §11.3–11.19](docs/ARCHITECTURE.md#113-ssrf--local-file-read-via-resource-fetching-security--mitigated).

## macOS app

For a desktop experience there's a native macOS app that reuses the same UI.
It runs the converter in-process and shows the drag-and-drop page inside a
native window (WKWebView via [pywebview](https://pywebview.flowrl.com)); dropping
a file opens a native **Save as…** dialog for the resulting PDF.

```bash
pip install ".[mac]"        # or: pip install -r macapp/requirements.txt
python -m macapp            # opens the app window
```

### Building a double-clickable `ipdf.app`

On a Mac you can bundle it with [py2app](https://py2app.readthedocs.io):

```bash
pip install -r macapp/requirements.txt py2app
python macapp/setup_py2app.py py2app
open dist/ipdf.app
```

> **Native-library caveat.** WeasyPrint depends on Pango/cairo/GDK-PixBuf.
> `python -m macapp` works as soon as those are present (`brew install
> weasyprint` installs them). A fully self-contained `.app` that runs on a Mac
> *without* Homebrew requires bundling those dylibs into the app — that step is
> environment-specific and not automated here.

Why pywebview and not Tauri/Electron? The conversion is Python + WeasyPrint, so
a Rust/JS shell would still have to ship and drive a Python backend. pywebview
reuses the existing converter and frontend directly in a native window — far
less moving machinery for the same result.

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

For the full design — component map, the iPhone-readability math, request
lifecycles, deployment, and a maintainer's list of **gotchas** (native deps,
the SSRF/local-file security note, worker sizing, fonts, …) — see
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Development

```bash
python -m unittest        # run the test suite
```

## License

MIT — see [LICENSE](LICENSE).
