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


def local_node() -> str:
    """This machine's node name: NOUGEN_NODE_NAME (repo convention), else hostname."""
    named = os.environ.get("NOUGEN_NODE_NAME", "").strip().lower()
    return named or socket.gethostname().split(".")[0].lower()
