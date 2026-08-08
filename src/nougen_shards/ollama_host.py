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
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

#: Wildcard/listen addresses that are valid to bind but not to dial.
WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*", ""})

DEFAULT_CLIENT_HOST = "127.0.0.1"
DEFAULT_OLLAMA_PORT = 11434
#: Ports this box has actually served on. Fallback ranking only -- the live port
#: wins, discovered by probe. 11436 was the live port on 2026-08-07 while the
#: 11434 constant answered nothing; that is exactly why this is a list, not a value.
DEFAULT_CANDIDATE_PORTS = (11434, 11436)
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


def candidate_ports() -> tuple[int, ...]:
    """Ports to probe when the env gives no usable one. ``NOUGEN_OLLAMA_PORTS=11434,11436``."""
    raw = os.environ.get("NOUGEN_OLLAMA_PORTS")
    if raw:
        ports = []
        for chunk in str(raw).replace(";", ",").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                ports.append(int(chunk))
            except ValueError:
                logger.warning("ignoring non-numeric candidate ollama port %r", chunk)
        if ports:
            return tuple(dict.fromkeys(ports))
    # Env-declared port leads the probe order; constants are the logged tail.
    return tuple(dict.fromkeys((default_port(),) + DEFAULT_CANDIDATE_PORTS))


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


def probe_url(url: str, *, timeout: float | None = None) -> bool:
    """True if an ollama daemon answers ``/api/tags`` at ``url``.

    A sanitized URL is still only a *claim* that something is listening (Rule 0.2).
    ``WinError 10061``/``ConnectionRefused`` means the daemon is cold -- a different
    failure from the ``10049`` bind-address trap this module was written for.
    """
    timeout = timeout if timeout is not None else float(
        os.environ.get("NOUGEN_OLLAMA_PROBE_TIMEOUT", "4"))
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=timeout) as r:
            return 200 <= getattr(r, "status", 200) < 300
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("ollama probe failed at %s: %s", url, exc)
        return False


def discover_ollama_url(*, timeout: float | None = None) -> str | None:
    """Return the first ollama base URL that actually answers, else ``None``.

    Order: the env-resolved URL, then each candidate port on the loopback host.
    Discovery beats the constant -- a portless env value must not pin a caller to
    a dead default port.
    """
    seen: list[str] = []
    resolved = resolve_ollama_url(log=False)
    for url in [resolved] + [f"http://{DEFAULT_CLIENT_HOST}:{p}" for p in candidate_ports()]:
        if url in seen:
            continue
        seen.append(url)
        if probe_url(url, timeout=timeout):
            if url != resolved:
                logger.info("ollama answered at %s (env resolved to %s)", url, resolved)
            return url
    logger.info("no ollama daemon answered on any of %s", seen)
    return None


def autostart_enabled() -> bool:
    """Whether a cold daemon may be ignited. ``NOUGEN_OLLAMA_AUTOSTART=0`` disables."""
    raw = os.environ.get("NOUGEN_OLLAMA_AUTOSTART")
    if raw is None:
        return True
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def ensure_ollama_url(*, autostart: bool | None = None,
                      wait_s: float | None = None) -> str | None:
    """Discover a live ollama, igniting a cold daemon once if allowed.

    There is no ollama autostart on this box, so an unattended lane firing at 3 AM
    meets a cold daemon and loses its whole fleet step unless it starts one itself
    (dream lane, 2026-08-07). Returns the live base URL, or ``None`` if the lane is
    genuinely unavailable -- callers degrade, they do not pretend.
    """
    url = discover_ollama_url()
    if url:
        return url
    if not (autostart_enabled() if autostart is None else autostart):
        logger.info("ollama cold and autostart disabled; lane unavailable")
        return None

    binary = os.environ.get("NOUGEN_OLLAMA_BIN", "ollama")
    try:
        subprocess.Popen([binary, "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    except (OSError, ValueError) as exc:
        logger.warning("could not start %s serve: %s", binary, exc)
        return None

    deadline = time.monotonic() + (wait_s if wait_s is not None else float(
        os.environ.get("NOUGEN_OLLAMA_START_WAIT", "45")))
    while time.monotonic() < deadline:
        time.sleep(1.5)
        url = discover_ollama_url()
        if url:
            logger.info("ignited cold ollama daemon; live at %s", url)
            return url
    logger.warning("started %s serve but nothing answered before timeout", binary)
    return None


__all__ = [
    "WILDCARD_HOSTS",
    "DEFAULT_CANDIDATE_PORTS",
    "DEFAULT_CLIENT_HOST",
    "DEFAULT_OLLAMA_PORT",
    "api",
    "autostart_enabled",
    "candidate_ports",
    "default_client_url",
    "default_port",
    "discover_ollama_url",
    "ensure_ollama_url",
    "probe_url",
    "resolve_ollama_url",
    "sanitize_ollama_url",
]
