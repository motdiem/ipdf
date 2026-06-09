"""Native macOS desktop wrapper for ipdf.

This reuses everything that already exists:

* the ``ipdf`` converter (Markdown / .docx -> iPhone-optimised PDF), and
* the ``webapp`` Flask frontend (the same drag-and-drop UI),

and presents them inside a native macOS window via ``pywebview`` (which uses
the system WKWebView). The Flask app runs on a private localhost port in a
background thread; the window points at it. A small JavaScript bridge lets the
page hand finished PDFs back to Python so they can be written out through a
native "Save as…" dialog.

Run it with::

    python -m macapp

``webview`` is imported lazily (only inside the functions that need a running
GUI) so the rest of this module stays importable — and testable — on machines
without a display or the GUI backend installed.
"""

from __future__ import annotations

import base64
import socket
import threading
from pathlib import Path

from werkzeug.serving import make_server

from webapp.app import app as flask_app

WINDOW_TITLE = "ipdf"
DEFAULT_SIZE = (760, 860)
MIN_SIZE = (430, 600)


def find_free_port(host: str = "127.0.0.1") -> int:
    """Ask the OS for an unused TCP port on ``host``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


class FlaskServerThread(threading.Thread):
    """Runs the Flask app on a real WSGI server in a background thread."""

    def __init__(self, host: str = "127.0.0.1", port: int | None = None):
        super().__init__(daemon=True)
        self.host = host
        self.port = port or find_free_port(host)
        self._server = make_server(host, self.port, flask_app, threaded=True)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def run(self) -> None:  # pragma: no cover - exercised via integration use
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()


def write_pdf(path: str | Path, b64_data: str) -> Path:
    """Decode base64 PDF bytes from the webview and write them to ``path``.

    Factored out from the dialog flow so it can be unit-tested without a GUI.
    """
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        path = path.with_suffix(".pdf")
    path.write_bytes(base64.b64decode(b64_data))
    return path


class Api:
    """JavaScript-callable bridge exposed to the page as ``window.pywebview.api``."""

    def save_pdf(self, filename: str, b64_data: str) -> dict:
        """Prompt for a destination and save the converted PDF there.

        Returns ``{"saved": bool, "path": str|None}`` so the page can update
        its status line. ``{"saved": False}`` means the user cancelled.
        """
        import webview  # lazy: only needed when a window actually exists

        window = webview.windows[0]
        safe_name = Path(filename or "document.pdf").name
        result = window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=safe_name,
            file_types=("PDF files (*.pdf)",),
        )
        if not result:
            return {"saved": False, "path": None}
        # Different pywebview versions return a str or a one-element list/tuple.
        target = result if isinstance(result, (str, bytes)) else result[0]
        try:
            saved = write_pdf(target, b64_data)
        except (ValueError, OSError) as exc:
            # Malformed base64 from the bridge, or an unwritable path.
            return {"saved": False, "path": None, "error": str(exc)}
        return {"saved": True, "path": str(saved)}


def main() -> None:
    """Launch the desktop app."""
    import webview  # lazy import so module import never requires a GUI backend

    server = FlaskServerThread()
    server.start()

    api = Api()
    webview.create_window(
        WINDOW_TITLE,
        server.url,
        js_api=api,
        width=DEFAULT_SIZE[0],
        height=DEFAULT_SIZE[1],
        min_size=MIN_SIZE,
    )
    try:
        # gui="cocoa" is the native macOS backend; pywebview auto-detects it
        # but we name it for clarity.
        webview.start(gui="cocoa")
    finally:
        server.shutdown()


if __name__ == "__main__":  # pragma: no cover
    main()
