"""Network-exposure detection for the NouGenShards node.

The Cortex HUD is an *unauthenticated* read surface: its search tab returns raw
shard ``content`` and its transcript tab hands out a whole-vault dump via
``gr.File``. It may only be mounted when the process is genuinely unreachable
from anything but loopback.

Why this module exists
----------------------
The previous guard decided that question from the ``NGS_HOST`` env var::

    _default_host = "0.0.0.0" if os.environ.get("SPACE_ID") else "127.0.0.1"
    _bind_host = os.environ.get("NGS_HOST", _default_host)
    _network_exposed = _bind_host not in ("127.0.0.1", "localhost", "::1")

``NGS_HOST`` does not control the bind in the shipped container. The Dockerfile
runs ``uvicorn app:app --host 0.0.0.0 --port 7860``; uvicorn never reads
``NGS_HOST``. Setting ``NGS_HOST=127.0.0.1`` in the platform settings therefore
made the app *believe* it was loopback-only while it stayed bound to 0.0.0.0 on
a public domain, mounting the vault UI for anyone. One plausible config change
silently disabled the guard: it failed OPEN.

Doctrine (Rule 0.2)
-------------------
Exposure is derived from what actually determines reachability, resolved
env -> config -> probe, with named constants used only as *logged* fallbacks:

* the real bind host, probed from the live server command line (``--host``),
  then uvicorn/gunicorn env forms, then ``NGS_HOST`` (advisory: it only governs
  the bind when ``app.py`` runs uvicorn itself), then a logged fallback;
* any recognized hosting-platform indicator variable;
* and when the answer is ambiguous the verdict is EXPOSED. Fail closed.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional, Sequence, Tuple

LOGGER = logging.getLogger(__name__)

# --- Env var names (configuration surface) ---------------------------------
ENV_LOOPBACK_HOSTS = "NGS_LOOPBACK_HOSTS"
ENV_WILDCARD_HOSTS = "NGS_WILDCARD_HOSTS"
ENV_PLATFORM_VARS = "NGS_PLATFORM_INDICATOR_VARS"
ENV_BIND_HOST_FALLBACK = "NGS_BIND_HOST_FALLBACK"
ENV_DATA_MOUNT = "NGS_DATA_MOUNT"
ENV_BLOCKED_PATHS = "NGS_HUD_BLOCKED_PATHS"
ENV_ADVISORY_HOST = "NGS_HOST"

# --- Fallback constants ----------------------------------------------------
# Rule 0.2: each of these is overridable by the env var above it, and the
# resolver logs whenever the fallback (rather than configuration or a probe) is
# what actually decided the value. None of them is a source of truth.
FALLBACK_LOOPBACK_HOSTS = "127.0.0.1,localhost,::1,0:0:0:0:0:0:0:1"
# Hosts that mean "every interface". The empty string is included on purpose:
# `--host ""` binds all interfaces just like 0.0.0.0.
FALLBACK_WILDCARD_HOSTS = "0.0.0.0,::,*,"
# uvicorn's own default when no --host is supplied. Used only when every probe
# and every configuration source came up empty.
FALLBACK_BIND_HOST = "127.0.0.1"
FALLBACK_DATA_MOUNT = "/data"
# Variables that only exist inside a managed hosting platform. Presence of any
# of them means the process is reachable from a network we do not control.
FALLBACK_PLATFORM_VARS = ",".join((
    # Hugging Face Spaces
    "SPACE_ID", "SPACE_HOST", "SPACE_REPO_NAME", "SYSTEM",
    # Heroku / Render / Fly / Railway / Vercel / Cloud Run / Azure / AWS
    "DYNO", "RENDER", "RENDER_SERVICE_ID", "FLY_APP_NAME", "FLY_MACHINE_ID",
    "RAILWAY_ENVIRONMENT", "VERCEL", "K_SERVICE", "WEBSITE_SITE_NAME",
    "AWS_EXECUTION_ENV", "ECS_CONTAINER_METADATA_URI",
    # Kubernetes / hosted dev containers
    "KUBERNETES_SERVICE_HOST", "CODESPACE_NAME", "REPL_ID", "GITPOD_WORKSPACE_ID",
))

# Command-line flags that set the bind host on the servers this app ships with.
BIND_HOST_FLAGS = ("--host",)
BIND_ADDR_FLAGS = ("--bind",)  # gunicorn style: host:port
# Env forms honoured by the servers themselves, in precedence order.
SERVER_HOST_ENV_VARS = ("UVICORN_HOST",)
SERVER_BIND_ENV_VARS = ("GUNICORN_CMD_ARGS", "GUNICORN_BIND")


def _env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if env is None else env


def _csv(
    env: Mapping[str, str],
    var: str,
    fallback: str,
    *,
    keep_empty: bool = False,
) -> Tuple[Tuple[str, ...], str]:
    """Resolve a comma-separated list from env, falling back to a constant.

    Returns ``(values, source)`` where source is the env var name or
    ``"fallback:<var>"``; callers log the fallback case.
    """
    raw = env.get(var)
    source = var
    if raw is None or not raw.strip():
        raw, source = fallback, "fallback:%s" % var
        LOGGER.debug("%s unset; using fallback constant", var)
    parts = [p.strip() for p in raw.split(",")]
    values = tuple(p for p in parts if p or keep_empty)
    return values, source


def loopback_hosts(env: Optional[Mapping[str, str]] = None) -> Tuple[str, ...]:
    values, _ = _csv(_env(env), ENV_LOOPBACK_HOSTS, FALLBACK_LOOPBACK_HOSTS)
    return tuple(v.lower() for v in values)


def wildcard_hosts(env: Optional[Mapping[str, str]] = None) -> Tuple[str, ...]:
    values, _ = _csv(
        _env(env), ENV_WILDCARD_HOSTS, FALLBACK_WILDCARD_HOSTS, keep_empty=True
    )
    return tuple(v.lower() for v in values)


def platform_indicator_vars(env: Optional[Mapping[str, str]] = None) -> Tuple[str, ...]:
    values, _ = _csv(_env(env), ENV_PLATFORM_VARS, FALLBACK_PLATFORM_VARS)
    return values


def _normalize_host(host: str) -> str:
    return host.strip().strip("[]").lower()


def is_loopback_host(host: Optional[str], env: Optional[Mapping[str, str]] = None) -> bool:
    """True only when *host* is provably loopback.

    Anything unknown, unparseable, or wildcard returns False so the caller
    fails closed. A hostname we cannot resolve to a loopback literal is treated
    as non-loopback on purpose: "not provably local" must never read as local.
    """
    if host is None:
        return False
    normalized = _normalize_host(host)
    if normalized in wildcard_hosts(env):
        return False
    if normalized in loopback_hosts(env):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _host_from_bind_expr(expr: str) -> Optional[str]:
    """Extract the host from a gunicorn-style ``host:port`` bind expression."""
    expr = expr.strip()
    if not expr:
        return None
    if expr.startswith("["):  # [::1]:8000
        closing = expr.find("]")
        if closing != -1:
            return expr[: closing + 1]
    if expr.count(":") == 1:
        return expr.rsplit(":", 1)[0]
    return expr


def resolve_bind_host(
    env: Optional[Mapping[str, str]] = None,
    argv: Optional[Sequence[str]] = None,
) -> Tuple[Optional[str], str]:
    """Probe the host the server is actually bound to.

    Returns ``(host, source)``. Precedence, strongest evidence first:

    1. ``--host`` / ``--bind`` on the live process command line. Under the
       shipped ``CMD ["uvicorn", "app:app", "--host", "0.0.0.0", ...]`` this is
       the only thing that sets the bind, and it ignores ``NGS_HOST``.
    2. Server-native env forms (``UVICORN_HOST``, ``GUNICORN_CMD_ARGS``).
    3. ``NGS_HOST`` -- advisory only. It governs the bind solely when ``app.py``
       calls ``uvicorn.run()`` itself; it is the weakest signal precisely
       because it is the one an operator can set without changing the bind.
    4. A logged fallback constant (uvicorn's own no-flag default).
    """
    environ = _env(env)
    args = list(sys.argv if argv is None else argv)

    for index, arg in enumerate(args):
        for flag in BIND_HOST_FLAGS:
            if arg == flag and index + 1 < len(args):
                return args[index + 1].strip(), "argv:%s" % flag
            if arg.startswith(flag + "="):
                return arg.split("=", 1)[1].strip(), "argv:%s=" % flag
        for flag in BIND_ADDR_FLAGS:
            value = None
            if arg == flag and index + 1 < len(args):
                value = args[index + 1]
            elif arg.startswith(flag + "="):
                value = arg.split("=", 1)[1]
            if value is not None:
                host = _host_from_bind_expr(value)
                if host:
                    return host.strip(), "argv:%s" % flag

    for var in SERVER_HOST_ENV_VARS:
        value = environ.get(var)
        if value and value.strip():
            return value.strip(), "env:%s" % var

    for var in SERVER_BIND_ENV_VARS:
        value = environ.get(var)
        if not value:
            continue
        tokens = value.split()
        for index, token in enumerate(tokens):
            for flag in BIND_ADDR_FLAGS + BIND_HOST_FLAGS:
                candidate = None
                if token == flag and index + 1 < len(tokens):
                    candidate = tokens[index + 1]
                elif token.startswith(flag + "="):
                    candidate = token.split("=", 1)[1]
                if candidate:
                    host = _host_from_bind_expr(candidate)
                    if host:
                        return host.strip(), "env:%s" % var

    advisory = environ.get(ENV_ADVISORY_HOST)
    if advisory and advisory.strip():
        return advisory.strip(), "env:%s(advisory)" % ENV_ADVISORY_HOST

    fallback = environ.get(ENV_BIND_HOST_FALLBACK) or FALLBACK_BIND_HOST
    source = (
        "env:%s" % ENV_BIND_HOST_FALLBACK
        if environ.get(ENV_BIND_HOST_FALLBACK)
        else "fallback:%s" % ENV_BIND_HOST_FALLBACK
    )
    LOGGER.debug("bind host undetermined by probe or config; using %s", source)
    return fallback, source


@dataclass(frozen=True)
class ExposureDecision:
    """Why the node does or does not consider itself network-reachable."""

    exposed: bool
    bind_host: Optional[str]
    bind_source: str
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    platform_indicators: Tuple[str, ...] = field(default_factory=tuple)

    def describe(self) -> str:
        verdict = "EXPOSED" if self.exposed else "LOCAL-ONLY"
        why = "; ".join(self.reasons) if self.reasons else "no exposure signal"
        return (
            "network exposure = %s (bind_host=%r via %s) because %s"
            % (verdict, self.bind_host, self.bind_source, why)
        )


def detect_exposure(
    env: Optional[Mapping[str, str]] = None,
    argv: Optional[Sequence[str]] = None,
) -> ExposureDecision:
    """Decide whether this process is reachable beyond loopback.

    Exposed if ANY of: a hosting-platform indicator is present, or the probed
    bind host is not provably loopback. Ambiguity resolves to exposed.
    """
    environ = _env(env)
    reasons = []

    indicators = tuple(
        var for var in platform_indicator_vars(environ)
        if str(environ.get(var, "")).strip()
    )
    if indicators:
        reasons.append("hosting platform indicator(s) set: %s" % ", ".join(indicators))

    bind_host, bind_source = resolve_bind_host(environ, argv)
    if not is_loopback_host(bind_host, environ):
        reasons.append(
            "bind host %r (resolved from %s) is not provably loopback"
            % (bind_host, bind_source)
        )

    return ExposureDecision(
        exposed=bool(reasons),
        bind_host=bind_host,
        bind_source=bind_source,
        reasons=tuple(reasons),
        platform_indicators=indicators,
    )


def should_mount_hud(decision: ExposureDecision, hud_auth: Optional[object]) -> bool:
    """The unauthenticated HUD mounts only on a local-only node, or with auth."""
    return bool(hud_auth) or not decision.exposed


def resolve_blocked_paths(env: Optional[Mapping[str, str]] = None) -> Tuple[str, ...]:
    """Paths Gradio's file router must never serve.

    Defence in depth: even if the HUD does mount, the persistent data mount and
    the vault directory stay off the static file router, so a path-traversal or
    a misconfigured ``gr.File`` cannot hand out the vault.
    """
    environ = _env(env)
    paths = []

    configured = environ.get(ENV_BLOCKED_PATHS)
    if configured:
        paths.extend(p.strip() for p in configured.split(os.pathsep))

    for var in ("NOUGEN_HOME", "NOUGEN_VAULT_DIR"):
        value = environ.get(var)
        if value:
            paths.append(value.strip())

    data_mount = environ.get(ENV_DATA_MOUNT)
    if not data_mount:
        data_mount = FALLBACK_DATA_MOUNT
        LOGGER.debug("%s unset; using fallback data mount", ENV_DATA_MOUNT)
    paths.append(data_mount.strip())

    seen = set()
    ordered = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return tuple(ordered)


def log_exposure_decision(
    decision: ExposureDecision,
    hud_mounted: bool,
    blocked: Iterable[str] = (),
    stream=None,
) -> str:
    """Emit the startup line stating plainly why the node ruled as it did."""
    message = "[NGS] %s | cortex HUD %s | blocked_paths=%s" % (
        decision.describe(),
        "MOUNTED" if hud_mounted else "NOT mounted (fail-closed)",
        ",".join(blocked) or "<none>",
    )
    LOGGER.warning(message) if decision.exposed else LOGGER.info(message)
    print(message, file=stream if stream is not None else sys.stderr)
    return message
