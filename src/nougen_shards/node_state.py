"""Node power/reachability state as first-class telemetry (relay 20260913T162818Z).

A machine that is OFF must never look like a machine that is SICK. One
observer losing a route is not proof a node is offline, a dead tunnel is
not proof the computer is dead, and a refused connection proves the host
is UP (something answered with a reset).

Owner declarations live in ~/.nougen/node_power.json:

    {"blade": {"state": "offline", "declared_at": 1789330000.0, "note": "powered off"}}
"""

from __future__ import annotations

import errno
import json
import os
import socket
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class NodeState(str, Enum):
    ONLINE_HEALTHY = "ONLINE_HEALTHY"
    ONLINE_DEGRADED = "ONLINE_DEGRADED"
    ONLINE_SERVICE_DOWN = "ONLINE_SERVICE_DOWN"
    OFFLINE_EXPECTED = "OFFLINE_EXPECTED"
    OFFLINE_UNEXPECTED = "OFFLINE_UNEXPECTED"
    NETWORK_PARTITION = "NETWORK_PARTITION"
    SLEEPING = "SLEEPING"
    BOOTING = "BOOTING"
    UNKNOWN = "UNKNOWN"


ONLINE_STATES = {NodeState.ONLINE_HEALTHY, NodeState.ONLINE_DEGRADED,
                 NodeState.ONLINE_SERVICE_DOWN, NodeState.BOOTING}

_UNREACHABLE_ERRNOS = {errno.EHOSTUNREACH, errno.ENETUNREACH,
                       getattr(errno, "EHOSTDOWN", errno.EHOSTUNREACH)}


def failure_class(exc: BaseException) -> str:
    """Name what a failed connect actually says, instead of calling it all 'refused'."""
    if isinstance(exc, socket.gaierror):
        return "DNS_FAILURE"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "CONNECT_TIMEOUT"
    if isinstance(exc, ConnectionRefusedError) or getattr(exc, "errno", None) in (
            errno.ECONNREFUSED, 10061):
        return "CONNECTION_REFUSED"
    if getattr(exc, "errno", None) in _UNREACHABLE_ERRNOS or getattr(exc, "errno", None) in (10065, 10051):
        return "HOST_UNREACHABLE"
    return "SOCKET_ERROR"


def observer_name() -> str:
    return os.environ.get("NOUGEN_NODE_NAME") or os.environ.get("NOUGEN_MACHINE") or socket.gethostname()


def _power_file(home_dir: Optional[Path]) -> Path:
    return (home_dir or Path.home() / ".nougen") / "node_power.json"


def load_declarations(home_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    path = _power_file(home_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def declare(node: str, state: str, note: str = "", home_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Record the owner's word on a node's power state. state: offline|sleeping|online."""
    state = state.lower()
    if state not in ("offline", "sleeping", "online"):
        raise ValueError("state must be offline, sleeping or online")
    decls = load_declarations(home_dir)
    if state == "online":
        decls.pop(node, None)
        entry: Dict[str, Any] = {}
    else:
        entry = {"state": state, "declared_at": time.time(), "note": note}
        decls[node] = entry
    path = _power_file(home_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(decls, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return entry


def classify(node: str, probes: Iterable[Dict[str, Any]],
             declaration: Optional[Dict[str, Any]] = None,
             witnesses: Optional[List[Dict[str, Any]]] = None,
             observer: Optional[str] = None) -> Dict[str, Any]:
    """Classify one node from this observer's probes plus any other evidence.

    probes: probe_tcp_detailed-style dicts (reachable, reason_code, port).
    witnesses: other observers' verdicts, [{"observer": "whoart", "reachable": False}].
    """
    probes = list(probes)
    witnesses = list(witnesses or [])
    observer = observer or observer_name()
    up = [p for p in probes if p.get("reachable")]
    refused = [p for p in probes if not p.get("reachable")
               and p.get("reason_code") == "CONNECTION_REFUSED"]
    classes = sorted({p.get("reason_code", "UNKNOWN") for p in probes if not p.get("reachable")})
    evidence = {"observer": observer, "probes": probes, "witnesses": witnesses,
                "declaration": declaration or None, "failure_classes": classes}

    def out(state: NodeState, reason: str, confidence: float) -> Dict[str, Any]:
        # `online` is intentionally tri-state. A single observer's timeout,
        # DNS failure, or unknown route is not evidence that the host is down.
        # Keep the richer `state` as the authority and reserve False for
        # explicitly offline/sleeping states supported by owner or witness data.
        online: Optional[bool]
        if state in ONLINE_STATES or state is NodeState.NETWORK_PARTITION:
            online = True
        elif state in (NodeState.OFFLINE_EXPECTED, NodeState.OFFLINE_UNEXPECTED,
                       NodeState.SLEEPING):
            online = False
        else:
            online = None
        return {"node": node, "state": state.value, "reason": reason,
                "confidence": confidence, "evidence": evidence,
                "online": online, "telemetry_available": True,
                "timestamp": time.time()}

    declared = (declaration or {}).get("state")
    if up:
        if declared in ("offline", "sleeping"):
            return out(NodeState.BOOTING,
                       f"declared {declared} but port {up[0].get('port')} answers; declaration is stale", 0.8)
        down = [p for p in probes if not p.get("reachable")]
        if not down:
            return out(NodeState.ONLINE_HEALTHY, f"all {len(up)} probed ports answer from {observer}", 1.0)
        return out(NodeState.ONLINE_DEGRADED,
                   "up; not answering on " + ", ".join(
                       f"{p.get('port')} ({p.get('reason_code')})" for p in down), 0.9)
    if refused:
        return out(NodeState.ONLINE_SERVICE_DOWN,
                   f"host is up (port {refused[0].get('port')} refused); no probed service listening", 0.9)
    if declared == "offline":
        return out(NodeState.OFFLINE_EXPECTED,
                   "declared offline by owner" + (f": {declaration.get('note')}" if declaration.get("note") else ""), 1.0)
    if declared == "sleeping":
        return out(NodeState.SLEEPING, "declared sleeping by owner", 1.0)

    saw_it = [w for w in witnesses if w.get("reachable")]
    lost_it = [w for w in witnesses if w.get("reachable") is False]
    if saw_it:
        return out(NodeState.NETWORK_PARTITION,
                   f"unreachable from {observer} but reachable from "
                   + ", ".join(str(w.get("observer")) for w in saw_it), 0.9)
    if lost_it:
        return out(NodeState.OFFLINE_UNEXPECTED,
                   f"unreachable from {observer} and "
                   + ", ".join(str(w.get("observer")) for w in lost_it)
                   + f" ({', '.join(classes) or 'no probes'}); not declared offline", 0.8)
    if "DNS_FAILURE" in classes and len(classes) == 1:
        return out(NodeState.UNKNOWN, f"name did not resolve from {observer}; host state not established", 0.2)
    return out(NodeState.UNKNOWN,
               f"unreachable from {observer} only ({', '.join(classes) or 'no probes'}); "
               "one observer cannot prove offline", 0.3)
