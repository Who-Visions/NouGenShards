"""Dynamic endpoint resolution.

Nothing in this module (or its callers) knows any operator's hostnames. A value
resolves from, in order:

1. an environment variable,
2. the local endpoints file (``NOUGEN_ENDPOINTS_FILE`` or ``~/.nougen/endpoints.json``),
3. ``None``.

``None`` means "not configured": callers stay local-first and skip the remote
step instead of falling back to someone else's infrastructure.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

_ENV = {
    "fleet_gateway_url": "NOUGEN_FLEET_GATEWAY_URL",
    "hf_space_url": "HF_SPACE_URL",
    "workers_subdomain": "NOUGEN_WORKERS_SUBDOMAIN",
}


def endpoints_file() -> Path:
    raw = os.environ.get("NOUGEN_ENDPOINTS_FILE")
    return Path(raw).expanduser() if raw else Path.home() / ".nougen" / "endpoints.json"


def _from_file(key: str) -> Optional[str]:
    try:
        data = json.loads(endpoints_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get(key) if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve(key: str) -> Optional[str]:
    """Return the configured value for ``key``, or None when unset."""
    env_name = _ENV.get(key)
    if env_name:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return _from_file(key)


def fleet_gateway_url() -> Optional[str]:
    url = resolve("fleet_gateway_url")
    return url.rstrip("/") if url else None


def hf_space_url() -> Optional[str]:
    url = resolve("hf_space_url")
    return url.rstrip("/") if url else None


def workers_subdomain() -> Optional[str]:
    return resolve("workers_subdomain")


def worker_live_url(worker_name: str) -> Optional[str]:
    """Public URL for a deployed Worker, or None if the subdomain is unknown."""
    sub = workers_subdomain()
    return f"https://{worker_name}.{sub}.workers.dev" if sub else None
