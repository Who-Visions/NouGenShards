"""Fleet topology resolved at runtime, never hardcoded.

A stranger's machine has no fleet. Node names come from ``NOUGEN_PEER_NODES``
(comma-separated, default empty) and the local node from the hostname, so a
clean install reports zero expected peers instead of phantom ones.
"""
from __future__ import annotations

import os
import socket


def fleet_nodes() -> tuple[str, ...]:
    raw = os.environ.get("NOUGEN_PEER_NODES", "")
    return tuple(n.strip().lower() for n in raw.split(",") if n.strip())


# Hostnames that name no machine. A phone, a container or a fresh VM often
# reports one of these, so every such device would stamp the same name.
_GENERIC_HOSTS = frozenset({"", "localhost", "localhost.localdomain", "android", "ubuntu",
                            "debian", "raspberrypi", "iphone", "ipad", "unknown", "host"})


def _slug(value: str) -> str:
    """Lowercase, [a-z0-9-] only, so a name is safe in a path, a pipe and a header."""
    import re
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:48]


def _machine_id_path():
    from pathlib import Path
    root = os.environ.get("NOUGEN_ROOT", "").strip()
    return (Path(root).expanduser() if root else Path.home() / ".nougen") / "machine_id"


def device_id() -> str:
    """A stable id for a device whose hostname says nothing: ``device-<8 hex>``.

    Written once next to the other NouGen state and read back after, so the id
    survives restarts. If the file cannot be written (read-only home, sandbox)
    the id is derived from the network hardware address instead, so two
    reads still agree; only a box with neither stays unnamed.
    """
    path = _machine_id_path()
    try:
        stored = _slug(path.read_text(encoding="utf-8"))
        if stored:
            return stored
    except OSError:
        pass
    import hashlib
    import uuid
    mac = uuid.getnode()
    # uuid.getnode() invents a random value (multicast bit set) when it cannot read a MAC.
    derived = "device-" + hashlib.sha256(str(mac).encode()).hexdigest()[:8]
    fresh = derived if not (mac >> 40) & 1 else "device-" + uuid.uuid4().hex[:8]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fresh + "\n", encoding="utf-8")
        return fresh
    except OSError:
        return derived


def local_node() -> str:
    """This machine's node name, discovered at runtime on whatever device this is.

    ``NOUGEN_NODE_NAME`` (repo convention) wins; else the hostname, slugged
    so it is safe to stamp into a path or header; else, when the hostname
    names no machine (``localhost``, ``android``, empty), a persisted
    ``device-<hex>`` id. Never empty, never a fleet name baked into code.
    """
    named = _slug(os.environ.get("NOUGEN_NODE_NAME", ""))
    if named:
        return named
    try:
        host = socket.gethostname().split(".")[0]
    except OSError:
        host = ""
    slug = _slug(host)
    if slug and slug not in _GENERIC_HOSTS:
        return slug
    return device_id()
