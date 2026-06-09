###############################################################################
# ipdf web frontend — container image
#
# Serves the drag-and-drop web app (Markdown / .docx -> iPhone-optimised PDF)
# behind gunicorn. The bulk of this file is about satisfying WeasyPrint's
# *native* dependencies (Pango / cairo / GDK-PixBuf) and shipping good fonts —
# without them the image builds but every conversion fails at runtime.
###############################################################################

FROM python:3.11-slim AS runtime

# --- Native libraries WeasyPrint links against at runtime, plus fonts. -------
# These are the #1 gotcha: a pip install of weasyprint does NOT pull them in.
# Font packages matter for output quality — DejaVu/Liberation cover Latin text
# (Liberation is metric-compatible with Arial), Noto widens script coverage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        libfontconfig1 \
        shared-mime-info \
        fonts-dejavu \
        fonts-liberation \
        fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    GUNICORN_TIMEOUT=120

WORKDIR /app

# --- Python dependencies (own layer for build-cache friendliness). -----------
# Copy only the requirement spec first so changing app code doesn't bust the
# (slow) dependency-install layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn flask

# --- Application code. Only what the web service needs. -----------------------
COPY ipdf ./ipdf
COPY webapp ./webapp

# --- Run as an unprivileged user. --------------------------------------------
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Liveness probe: the index route renders 200 once the app is importable and
# its templates are present. The slim image has no curl, so use Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/', timeout=4)" || exit 1

# gunicorn is the production WSGI server (the Flask dev server is single-threaded
# and explicitly 'not for production'). Threads help overlap upload I/O; workers
# give real parallelism for the CPU-bound render. Tune via the env vars above.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} \
        --workers ${GUNICORN_WORKERS} \
        --threads ${GUNICORN_THREADS} \
        --timeout ${GUNICORN_TIMEOUT} \
        --access-logfile - --error-logfile - \
        webapp.app:app"]
