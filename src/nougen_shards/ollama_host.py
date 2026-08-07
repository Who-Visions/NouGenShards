"""Canonical ollama client-URL resolution.

Rule 0.2 (Dynamic State Doctrine): ``OLLAMA_HOST`` is the *server's* bind address,
not a client target. On a box configured to listen on every interface it reads
``0.0.0.0`` -- schemeless, portless, and not connectable. Handing it straight to an
HTTP client raises ``URLError: <urlopen error [WinError 10049] The requested address
is not valid in its context>`` on Windows (``Cannot assign requested address`` on
Linux), which reads exactly like "ollama is down" and sends you debugging the daemon.

Confirmed twice on the Stadium: flagged 2026-08-05, reproduced by the dream lane
2026-08-06. Every caller in this package resolves through :func:`resolve_ollama_url`
so the fix lives in one place instead of being re-derived per script.

Resolution order (env -> sanitize -> logged fallback):

1. ``NOUGEN_OLLAMA_URL`` / ``NOUGEN_OLLAMA_HOST`` -- explicit client override, wins.
2. ``OLLAMA_HOST`` -- inherited from the daemon's config; sanitized, never trusted raw.
3. ``DEFAULT_CLIENT_URL`` -- logged fallback, never the source of truth.

Cloud lanes are the opposite case: ``OLLAMA_HOST=https://ollama.com`` is a genuine
client URL and passes through untouched (scheme preserved, no port forced).
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

#: Wildcard/listen addresses that are valid to bind but not to dial.
WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*", ""})

DEFAULT_CLIENT_HOST = "127.0.0.1"
DEFAULT_OLLAMA_PORT = 11434
#: Schemes that carry their own implicit port -- don't append one.
_IMPLICIT_PORT_SCHEMES = frozenset({"https"})

_ENV_KEYS = ("NOUGEN_OLLAMA_URL", "NOUGEN_OLLAMA_HOST", "OLLAMA_HOST")


def default_port() -> int:
    """Client port, env-resolvable with a logged constant fallback."""
    raw = os.environ.get("NOUGEN_OLLAMA_PORT") or os.environ.get("OLLAMA_PORT")
    if raw:
        try:
            return int(str(raw).strip())
        except ValueError:
            logger.warning("ignoring non-numeric ollama port %r", raw)
    return DEFAULT_OLLAMA_PORT


def default_client_url() -> str:
    return f"http://{DEFAULT_CLIENT_HOST}:{default_port()}"


def sanitize_ollama_url(raw: str | None, *, port: int | None = None) -> str:
    """Turn any ``OLLAMA_HOST``-shaped value into a dialable client URL.

    Handles the cases that actually occur: bare ``0.0.0.0``, ``:11434``,
    ``localhost``, ``http://host`` with no port, IPv6 wildcards, and full
    ``https://`` cloud URLs (returned unchanged apart from trailing-slash trim).
    """
    port = port or default_port()
    text = (raw or "").strip().rstrip("/")
    if not text:
        return f"http://{DEFAULT_CLIENT_HOST}:{port}"

    # ":11434" is a bind shorthand meaning "all interfaces, this port".
    if text.startswith(":") and text[1:].isdigit():
        return f"http://{DEFAULT_CLIENT_HOST}:{int(text[1:])}"

    if "://" not in text:
        text = "http://" + text

    # Bare wildcard tokens ("::", "[::]", "0.0.0.0", "*") are not parseable as
    # netlocs -- urlsplit raises on "http://::" -- so resolve them before parsing.
    scheme, _, remainder = text.partition("://")
    if remainder in WILDCARD_HOSTS:
        return f"{scheme}://{DEFAULT_CLIENT_HOST}:{port}"

    try:
        parts = urlsplit(text)
        hostname = parts.hostname  # lowercased, IPv6 brackets stripped
    except ValueError:
        logger.warning("unparseable ollama host %r; falling back to loopback", raw)
        return f"http://{DEFAULT_CLIENT_HOST}:{port}"
    if hostname is None or hostname in WILDCARD_HOSTS:
        hostname = DEFAULT_CLIENT_HOST

    # Re-bracket IPv6 literals so netloc stays parseable.
    if ":" in hostname:
        hostname = f"[{hostname}]"

    try:
        explicit_port = parts.port
    except ValueError:
        explicit_port = None
    if explicit_port is None and parts.scheme not in _IMPLICIT_PORT_SCHEMES:
        explicit_port = port

    netloc = hostname if explicit_port is None else f"{hostname}:{explicit_port}"
    if parts.username:
        credentials = parts.username
        if parts.password:
            credentials += f":{parts.password}"
        netloc = f"{credentials}@{netloc}"

    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", "")).rstrip("/")


def resolve_ollama_url(*, env: dict | None = None, log: bool = True) -> str:
    """Resolve the ollama client base URL: env -> sanitize -> logged fallback."""
    source_env = os.environ if env is None else env
    for key in _ENV_KEYS:
        raw = source_env.get(key)
        if raw and str(raw).strip():
            resolved = sanitize_ollama_url(str(raw))
            if log and resolved != str(raw).strip().rstrip("/"):
                logger.info("normalized %s %r -> %r (bind address is not dialable)",
                            key, raw, resolved)
            return resolved
    fallback = default_client_url()
    if log:
        logger.info("no ollama host in env; falling back to %s", fallback)
    return fallback


def api(path: str, *, base: str | None = None) -> str:
    """Join an API path onto the resolved base, e.g. ``api("/api/tags")``."""
    return f"{base or resolve_ollama_url()}/{path.lstrip('/')}"


__all__ = [
    "WILDCARD_HOSTS",
    "DEFAULT_CLIENT_HOST",
    "DEFAULT_OLLAMA_PORT",
    "api",
    "default_client_url",
    "default_port",
    "resolve_ollama_url",
    "sanitize_ollama_url",
]
