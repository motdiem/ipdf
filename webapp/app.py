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
import os
import sys
import tempfile
import threading
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

# Bound how many CPU/memory-heavy renders run concurrently *in this process* so a
# burst of requests (or threads) can't pile up and exhaust the worker. This is a
# per-process backpressure valve, not a substitute for an edge rate-limiter.
MAX_CONCURRENCY = max(1, int(os.environ.get("IPDF_MAX_CONCURRENCY", "2")))
_render_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)

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


# Bounds for numeric form fields. Mirrors the core ranges but rejected here as a
# 400 (client error) rather than a converter exception, so the message is clean.
_MARGIN_BOUNDS = (0.0, 3.0)
_FONT_SIZE_BOUNDS = (4.0, 48.0)
_LINE_HEIGHT_BOUNDS = (0.8, 4.0)


def _bounded_float(value, lo, hi, *, default=None):
    """Parse a finite float within [lo, hi]; abort 400 on anything else."""
    if value is None:
        return default
    value = str(value).strip()
    if value == "":
        return default
    try:
        num = float(value)
    except ValueError:
        abort(400, f"Expected a number, got {value!r}")
    if num != num or num in (float("inf"), float("-inf")):  # NaN / inf
        abort(400, f"Expected a finite number, got {value!r}")
    if not (lo <= num <= hi):
        abort(400, f"Value {num} out of range [{lo}, {hi}]")
    return num


def _build_options(form) -> RenderOptions:
    preset = (form.get("preset") or DEFAULT_PRESET).strip()
    if preset not in PAGE_PRESETS:
        abort(400, f"Unknown preset {preset!r}")

    theme = (form.get("theme") or DEFAULT_THEME).strip()
    if theme not in THEMES:
        abort(400, f"Unknown theme {theme!r}")

    # The web service only offers the vetted font presets — no literal families,
    # which keeps any value from reaching the CSS font-family declaration.
    font = (form.get("font") or DEFAULT_FONT).strip()
    if font not in FONT_STACKS:
        abort(400, f"Unknown font {font!r}")

    margin = _bounded_float(form.get("margin"), *_MARGIN_BOUNDS, default=0.3)
    line_height = _bounded_float(
        form.get("line_height"), *_LINE_HEIGHT_BOUNDS, default=1.5
    )
    font_size = _bounded_float(form.get("font_size"), *_FONT_SIZE_BOUNDS, default=None)

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
        # Untrusted input: never let a document read local files or reach the
        # network. Only embedded data: URIs are allowed through.
        allow_local_files=False,
        allow_remote=False,
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

    # Backpressure: reject rather than queue when all render slots are busy.
    if not _render_slots.acquire(blocking=False):
        abort(503, "Server busy, please retry shortly.")
    try:
        # Save to a temp file so the converter can detect the format by extension
        # and resolve any relative assets against its directory.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / safe_name
            upload.save(src)
            try:
                result = render(src, options=options)
            except ConversionError as exc:
                abort(400, str(exc))
    finally:
        _render_slots.release()

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


@app.errorhandler(503)
def _busy(err):
    return jsonify(error=getattr(err, "description", "Server busy")), 503


# A strict CSP the page actually satisfies: no inline scripts (the option
# metadata is delivered in a non-executed <script type="application/json">
# block), only same-origin assets, images limited to self + data: URIs.
_CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the ipdf web frontend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    # The Werkzeug debugger is a remote-code-execution surface; never let it run
    # on a non-loopback interface.
    loopback = {"127.0.0.1", "::1", "localhost"}
    if args.debug and args.host not in loopback:
        parser.error("--debug may only be used with a loopback --host (127.0.0.1).")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
