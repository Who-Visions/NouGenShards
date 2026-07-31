"""Decide whether this process is reachable from off-box.

The HUD mounts an unauthenticated vault UI (search over shard contents, env
recon) when it believes it is local-only, so this decision is a security
control and has to be conservative.

The rule it replaces asked ``NGS_HOST`` — a variable that never affected the
bind, because the shipped entrypoint is ``uvicorn app:app --host 0.0.0.0`` and
uvicorn does not read it. That failed open two ways: an operator setting
``NGS_HOST=127.0.0.1`` on a public host, and — worse, with no operator error at
all — the shipped Dockerfile run anywhere that isn't a managed platform, where
the old default assumed loopback while uvicorn bound 0.0.0.0.

This module lives apart from ``app.py`` so the decision is importable without
pulling in gradio and the whole application. The guard shipped untested for
exactly that reason.
"""

from __future__ import annotations

import os
import sys

#: Hosts that are provably not reachable from another machine.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"})

#: Set by the hosting platform, never by this repo. Presence means "reachable".
PLATFORM_VARS = (
    "SPACE_ID",                # Hugging Face Spaces
    "DYNO",                    # Heroku
    "RENDER",                  # Render
    "FLY_APP_NAME",            # Fly.io
    "K_SERVICE",               # Cloud Run / Knative
    "KUBERNETES_SERVICE_HOST",  # Kubernetes
    "WEBSITE_INSTANCE_ID",     # Azure App Service
)


def probed_bind_host(argv: list[str] | None = None, env: dict | None = None) -> str | None:
    """The host the server is ACTUALLY bound to, or None if nothing says.

    Precedence follows how much authority each source has over the real bind:
    the server's own argv, then the server's env vars, and only then the
    advisory ``NGS_HOST``.
    """
    argv = sys.argv if argv is None else argv
    env = os.environ if env is None else env
    for i, arg in enumerate(argv):
        if arg in ("--host", "--bind") and i + 1 < len(argv):
            return argv[i + 1]
        for prefix in ("--host=", "--bind="):
            if arg.startswith(prefix):
                return arg.split("=", 1)[1]
    return env.get("UVICORN_HOST") or env.get("NGS_HOST")


def on_managed_platform(env: dict | None = None) -> bool:
    """True when a hosting platform marks this process as internet-reachable."""
    env = os.environ if env is None else env
    return any(env.get(var) for var in PLATFORM_VARS)


def normalize_host(host: str | None) -> str:
    """Lower-case, strip IPv6 brackets; empty/None means 'nothing claimed'."""
    return (host or "").strip().strip("[]").lower()


def is_network_exposed(argv: list[str] | None = None, env: dict | None = None) -> bool:
    """Whether the HUD must require credentials.

    Fails closed: a managed platform always counts as exposed, and any host
    that is not *provably* loopback counts as exposed. Only an explicit
    loopback bind with no platform marker is treated as local-only.
    """
    if on_managed_platform(env):
        return True
    host = normalize_host(probed_bind_host(argv, env))
    if not host:
        return False  # nothing binds off-box by default
    return host not in LOOPBACK_HOSTS
