"""Flask web frontend for ipdf.

A tiny single-page app: drag a Markdown or .docx file onto the page and the
converted, iPhone-optimised PDF downloads automatically. Conversion options are
tucked behind a settings panel.

Run it with::

    python -m webapp           # http://127.0.0.1:5000
    # or
    python webapp/app.py
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

# Allow running as a loose script (python webapp/app.py) as well as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import (  # noqa: E402
    Flask,
    abort,
    jsonify,
    render_template,
    request,
    send_file,
)
from werkzeug.utils import secure_filename  # noqa: E402

from ipdf.converter import (  # noqa: E402
    DOCX_SUFFIXES,
    MARKDOWN_SUFFIXES,
    ConversionError,
    RenderOptions,
    render,
)
from ipdf.styles import (  # noqa: E402
    DEFAULT_FONT,
    DEFAULT_PRESET,
    DEFAULT_THEME,
    FONT_STACKS,
    PAGE_PRESETS,
    THEMES,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
ALLOWED_SUFFIXES = MARKDOWN_SUFFIXES | DOCX_SUFFIXES

# Human-friendly labels for the option pickers in the UI.
PRESET_LABELS = {
    "iphone": "iPhone (6.1\")",
    "iphone-mini": "iPhone mini",
    "iphone-max": "iPhone Pro Max",
    "iphone-se": "iPhone SE",
}
FONT_LABELS = {"sans": "Sans-serif", "serif": "Serif", "mono": "Monospace"}
THEME_LABELS = {"light": "Light", "dark": "Dark", "sepia": "Sepia"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def _choices():
    """Option metadata used to build the settings panel and validate input."""
    return {
        "presets": [
            {"value": name, "label": PRESET_LABELS.get(name, name)}
            for name in PAGE_PRESETS
        ],
        "fonts": [
            {"value": name, "label": FONT_LABELS.get(name, name)}
            for name in FONT_STACKS
        ],
        "themes": [
            {"value": name, "label": THEME_LABELS.get(name, name)}
            for name in THEMES
        ],
        "defaults": {
            "preset": DEFAULT_PRESET,
            "font": DEFAULT_FONT,
            "theme": DEFAULT_THEME,
            "font_size": "",      # blank => preset default
            "margin": 0.3,
            "line_height": 1.5,
            "hyphenate": True,
        },
        "accept": sorted(ALLOWED_SUFFIXES),
        "max_bytes": MAX_UPLOAD_BYTES,
    }


@app.get("/")
def index():
    return render_template("index.html", choices=_choices())


@app.get("/api/options")
def api_options():
    return jsonify(_choices())


def _float_or_none(value, default=None):
    if value is None:
        return default
    value = str(value).strip()
    if value == "":
        return default
    try:
        return float(value)
    except ValueError:
        abort(400, f"Expected a number, got {value!r}")


def _build_options(form) -> RenderOptions:
    preset = (form.get("preset") or DEFAULT_PRESET).strip()
    if preset not in PAGE_PRESETS:
        abort(400, f"Unknown preset {preset!r}")

    theme = (form.get("theme") or DEFAULT_THEME).strip()
    if theme not in THEMES:
        abort(400, f"Unknown theme {theme!r}")

    font = (form.get("font") or DEFAULT_FONT).strip()

    margin = _float_or_none(form.get("margin"), 0.3)
    line_height = _float_or_none(form.get("line_height"), 1.5)
    font_size = _float_or_none(form.get("font_size"), None)

    # checkboxes arrive as "true"/"on"/"1" when ticked, absent otherwise.
    hyphenate = str(form.get("hyphenate", "true")).lower() in {"1", "true", "on", "yes"}

    title = (form.get("title") or "").strip() or None

    return RenderOptions(
        page_preset=preset,
        margin=margin,
        font=font,
        font_size=font_size,
        line_height=line_height,
        theme=theme,
        hyphenate=hyphenate,
        title=title,
    )


@app.post("/convert")
def convert():
    if "file" not in request.files:
        abort(400, "No file was uploaded.")
    upload = request.files["file"]
    if not upload.filename:
        abort(400, "No file was selected.")

    safe_name = secure_filename(upload.filename) or "document"
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        abort(
            400,
            f"Unsupported file type {suffix or '(none)'!r}. "
            f"Upload a Markdown or .docx file.",
        )

    options = _build_options(request.form)

    # Save to a temp file so the converter can detect the format by extension
    # and resolve any relative assets against its directory.
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / safe_name
        upload.save(src)
        try:
            result = render(src, options=options)
        except ConversionError as exc:
            abort(400, str(exc))

    download_name = Path(safe_name).with_suffix(".pdf").name
    return send_file(
        io.BytesIO(result.pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


@app.errorhandler(400)
def _bad_request(err):
    return jsonify(error=getattr(err, "description", "Bad request")), 400


@app.errorhandler(413)
def _too_large(err):
    limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
    return jsonify(error=f"File too large (limit {limit_mb} MB)."), 413


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the ipdf web frontend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
