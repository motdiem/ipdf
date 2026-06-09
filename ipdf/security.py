"""Security primitives for safe conversion of *untrusted* documents.

Everything here is stdlib-only and self-contained. The three concerns:

1. ``build_url_fetcher`` — a restrictive WeasyPrint ``url_fetcher`` that decides
   which resources a document is allowed to pull in. This is the keystone
   defence against SSRF / local-file disclosure: a malicious document can embed
   ``<img src="file:///etc/passwd">`` or ``<img src="http://169.254.169.254/…">``
   and, without a gate, WeasyPrint would happily fetch it into the PDF.
2. ``check_archive_safety`` — guards against ``.docx`` (zip) decompression
   bombs, which slip past an upload byte-limit because the limit applies to the
   *compressed* size.
3. ``sanitize_font_family`` — keeps a caller-supplied literal font name from
   breaking out of the ``font-family`` CSS declaration (CSS injection).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import zipfile
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

# ---------------------------------------------------------------------------
# Default resource limits. Generous enough for real documents, small enough to
# stop a single request from exhausting a worker.
# ---------------------------------------------------------------------------
ARCHIVE_MAX_TOTAL_BYTES = 300 * 1024 * 1024   # 300 MB uncompressed
ARCHIVE_MAX_RATIO = 200                        # compressed -> uncompressed
ARCHIVE_MAX_ENTRIES = 5000

FONT_FAMILY_MAX_LEN = 200


class SecurityError(Exception):
    """Raised when a security policy is violated (bad font, zip bomb, …)."""


# ---------------------------------------------------------------------------
# URL fetcher
# ---------------------------------------------------------------------------
def _host_is_public(host: str) -> bool:
    """True only if every resolved address for ``host`` is publicly routable.

    Blocks loopback / private / link-local / reserved / multicast / unspecified
    ranges (e.g. 127.0.0.0/8, 10/8, 192.168/16, 169.254/16 incl. the cloud
    metadata endpoint, ::1, fc00::/7). Resolves the name once via
    ``getaddrinfo``; note the residual DNS-rebinding TOCTOU (WeasyPrint resolves
    again when it connects) — acceptable for a best-effort guard.
    """
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = info[4][0]
        # Strip a possible IPv6 zone id (e.g. "fe80::1%eth0").
        addr = addr.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def build_url_fetcher(
    base_dir: str | os.PathLike,
    *,
    allow_local_files: bool,
    allow_remote: bool,
) -> Callable:
    """Build a WeasyPrint ``url_fetcher`` enforcing a resource policy.

    Policy:
      * ``data:`` URIs are always allowed (mammoth inlines DOCX images this way).
      * ``file:`` / relative paths are allowed only when ``allow_local_files`` and
        only if they resolve *inside* ``base_dir`` (no ``..`` escapes, no
        absolute paths elsewhere on the filesystem).
      * ``http(s)`` is allowed only when ``allow_remote`` and only to publicly
        routable hosts (SSRF guard).
      * every other scheme is refused.
    """
    base = Path(base_dir).resolve()

    def fetcher(url, timeout=10, ssl_context=None):
        scheme = urlsplit(url).scheme.lower()

        if scheme == "data":
            return _delegate(url, timeout, ssl_context)

        if scheme in ("", "file"):
            if not allow_local_files:
                raise SecurityError(f"Local file access is disabled: {url!r}")
            target = _resolve_local(url, base)
            if not _within(target, base):
                raise SecurityError(
                    f"Refusing to read outside the document directory: {target}"
                )
            return _delegate(target.as_uri(), timeout, ssl_context)

        if scheme in ("http", "https"):
            if not allow_remote:
                raise SecurityError(f"Remote resource fetching is disabled: {url!r}")
            host = urlsplit(url).hostname
            if not _host_is_public(host):
                raise SecurityError(
                    f"Refusing to fetch from a non-public host: {host!r}"
                )
            return _delegate(url, timeout, ssl_context)

        raise SecurityError(f"Blocked URL scheme {scheme!r}: {url!r}")

    return fetcher


def _delegate(url, timeout, ssl_context):
    """Fetch an already-vetted URL via WeasyPrint's default fetcher.

    We deliberately use ``default_url_fetcher`` rather than the newer
    ``URLFetcher``: the default fetcher does **not** follow HTTP redirects, which
    matters for SSRF — a public URL that 30x-redirects to a private/metadata IP
    would otherwise bypass the ``_host_is_public`` check (which only sees the
    original host). ``default_url_fetcher`` is deprecated and removed in
    WeasyPrint 69, hence the ``<69`` pin; when moving to 69+, switch to
    ``URLFetcher`` *and* re-validate the host after redirects (or disable them).
    """
    import warnings

    from weasyprint import default_url_fetcher

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*default_url_fetcher.*")
        return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)


def _resolve_local(url: str, base: Path) -> Path:
    """Map a ``file:`` URL or relative reference to an absolute, resolved path."""
    parts = urlsplit(url)
    if parts.scheme == "file":
        # file:///abs/path  ->  /abs/path  (handles percent-encoding, Windows)
        raw = url2pathname(parts.path)
        path = Path(raw)
    else:
        path = Path(unquote(parts.path))
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _within(path: Path, base: Path) -> bool:
    try:
        return path == base or path.is_relative_to(base)
    except AttributeError:  # pragma: no cover - Python < 3.9 safety net
        return os.path.commonpath([str(path), str(base)]) == str(base)


# ---------------------------------------------------------------------------
# Archive (DOCX) bomb guard
# ---------------------------------------------------------------------------
def check_archive_safety(
    path: str | os.PathLike,
    *,
    max_total_bytes: int = ARCHIVE_MAX_TOTAL_BYTES,
    max_ratio: int = ARCHIVE_MAX_RATIO,
    max_entries: int = ARCHIVE_MAX_ENTRIES,
) -> None:
    """Reject a zip-based file (``.docx``) that looks like a decompression bomb.

    A small upload can declare an enormous uncompressed size; mammoth would then
    expand it and exhaust memory. We inspect the central directory (cheap, no
    extraction) and refuse on total size, entry count, or compression ratio.
    """
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > max_entries:
                raise SecurityError(
                    f"Archive has too many entries ({len(infos)} > {max_entries})."
                )
            total_uncompressed = sum(i.file_size for i in infos)
            total_compressed = sum(i.compress_size for i in infos)
            if total_uncompressed > max_total_bytes:
                raise SecurityError(
                    f"Archive expands to {total_uncompressed} bytes "
                    f"(> {max_total_bytes}); refusing as a possible zip bomb."
                )
            if total_compressed > 0:
                ratio = total_uncompressed / total_compressed
                if ratio > max_ratio:
                    raise SecurityError(
                        f"Archive compression ratio {ratio:.0f}x exceeds "
                        f"{max_ratio}x; refusing as a possible zip bomb."
                    )
    except zipfile.BadZipFile as exc:
        raise SecurityError(f"Not a valid .docx (zip) file: {exc}") from exc


# ---------------------------------------------------------------------------
# Font family sanitisation
# ---------------------------------------------------------------------------
# A CSS <family-name>/<generic-family> list is letters, digits, spaces, commas,
# quotes, dots, hyphens, underscores. Anything else ( ; { } ( ) @ / \ < > : )
# could break out of the `font-family: …;` declaration or smuggle url()/@import.
_FONT_RE = re.compile(r"^[A-Za-z0-9 ,._'\"-]+$")


def sanitize_font_family(value: str) -> str:
    """Return ``value`` if it is a safe CSS font-family list, else raise.

    Used only for *literal* font names (the CLI/library let a user pass an
    arbitrary family). Preset keys never reach here.
    """
    value = (value or "").strip()
    lowered = value.lower()
    if (
        not value
        or len(value) > FONT_FAMILY_MAX_LEN
        or not _FONT_RE.match(value)
        or "url(" in lowered
        or "@import" in lowered
        or "/*" in value
    ):
        raise SecurityError(f"Unsafe font family value: {value!r}")
    return value
