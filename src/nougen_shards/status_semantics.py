"""Explicit non-green status semantics (relay directive 20260913T174622Z).

A status names the exact component that was tested, at the scope it was
tested. Nothing propagates upward by association:

    GREEN   = directly verified working now
    YELLOW  = directly observed degraded, partial, stale, or incomplete
    ORANGE  = interface / registration / routing anomaly; the service behind
              it is not proven failed
    RED     = directly verified failure of the named component ONLY
    UNKNOWN = no sufficient current evidence. Never coerced to RED.

A parent (shards, machine, vault, service, fleet) is RED only when an
observation AT THAT SCOPE says so. A red probe makes its parent UNKNOWN,
never RED.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


class StatusLevel(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


ICONS = {
    StatusLevel.GREEN: "🟢",
    StatusLevel.YELLOW: "🟡",
    StatusLevel.ORANGE: "🟠",
    StatusLevel.RED: "🔴",
    StatusLevel.UNKNOWN: "⚪",
}

# A GREEN older than this is no longer "verified working now".
DEFAULT_MAX_AGE_S = 300.0


@dataclass
class Observation:
    observed_component: str
    reported_scope: str  # probe | tool_registration | service | node | vault | fleet
    status: StatusLevel
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    last_verified_at: float = field(default_factory=time.time)
    observer: Optional[str] = None

    def aged(self, now: Optional[float] = None,
             max_age_s: float = DEFAULT_MAX_AGE_S) -> "Observation":
        """A stale GREEN becomes YELLOW; nothing else changes colour with age."""
        now = time.time() if now is None else now
        age = now - self.last_verified_at
        if self.status is StatusLevel.GREEN and age > max_age_s:
            return Observation(
                self.observed_component, self.reported_scope, StatusLevel.YELLOW,
                f"stale: last verified {int(age)}s ago ({self.reason})",
                self.evidence, self.confidence, self.last_verified_at, self.observer)
        return self

    def line(self) -> str:
        return f"{ICONS[self.status]} {self.observed_component}: {self.reason}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


def aggregate(component: str, scope: str, observations: Iterable[Observation],
              now: Optional[float] = None,
              max_age_s: float = DEFAULT_MAX_AGE_S) -> Observation:
    """Status of a parent from its own direct evidence first, children second.

    Children can only ever make a parent GREEN (all verified), YELLOW
    (partial) or UNKNOWN. They can never make it RED.
    """
    obs = [o.aged(now, max_age_s) for o in observations]
    direct = [o for o in obs
              if o.reported_scope == scope and o.observed_component == component]
    if direct:
        latest = max(direct, key=lambda o: o.last_verified_at)
        return latest

    children = [o for o in obs if o not in direct]
    if not children:
        return Observation(component, scope, StatusLevel.UNKNOWN,
                           "no evidence at this scope", confidence=0.0)

    greens = [o for o in children if o.status is StatusLevel.GREEN]
    others = [o for o in children if o.status is not StatusLevel.GREEN]
    if not others:
        return Observation(component, scope, StatusLevel.GREEN,
                           f"all {len(greens)} observed children verified",
                           evidence={"children": [o.observed_component for o in greens]},
                           confidence=min(o.confidence for o in greens))
    named = "; ".join(f"{o.observed_component} {o.status.value.lower()}" for o in others)
    if greens:
        return Observation(component, scope, StatusLevel.YELLOW,
                           f"partial: {len(greens)}/{len(children)} verified ({named})",
                           evidence={"children": [o.to_dict() for o in children]},
                           confidence=0.5)
    return Observation(component, scope, StatusLevel.UNKNOWN,
                       f"not established by child evidence ({named})",
                       evidence={"children": [o.to_dict() for o in children]},
                       confidence=0.0)


def render(observations: Iterable[Observation]) -> List[str]:
    """One line per observation; every non-green says what and why."""
    return [o.line() for o in observations]


# --- classifiers for the concrete incidents in the directive -------------

def classify_shards_status(payload: Dict[str, Any],
                           observer: Optional[str] = None) -> List[Observation]:
    """`shards_status` is a health PROBE. Its failure is the probe's, not the shards'.

    up/health_up/mcp_up false with no confirmed origin means the endpoint
    check failed; whether shards work is not established by that.
    """
    origin = payload.get("origin") or payload.get("node") or "unknown"
    blade_confirmed = payload.get("blade_confirmed")
    if blade_confirmed is None:
        blade_confirmed = origin.lower() in ("blade1tb", "blade", "local")

    ok = bool(payload.get("up")) and bool(payload.get("health_up", True))
    ev = {
        "up": payload.get("up", ok),
        "health_up": payload.get("health_up", ok),
        "mcp_up": payload.get("mcp_up", ok),
        "configured": payload.get("configured", True),
        "origin": origin,
        "blade_confirmed": blade_confirmed,
    }
    for k in ("node", "status", "warnings"):
        if k in payload:
            ev[k] = payload[k]

    probe = Observation(
        "Shard health probe", "probe",
        StatusLevel.GREEN if ok else StatusLevel.RED,
        "endpoint check passed" if ok else "endpoint check failed",
        evidence=ev, observer=observer)
    shards = Observation(
        "Shards", "service",
        StatusLevel.UNKNOWN if not ok else (StatusLevel.GREEN if blade_confirmed else StatusLevel.YELLOW),
        "not established by this probe" if not ok
        else ("probe up; node origin verified" if blade_confirmed else "probe up; unconfirmed node origin"),
        confidence=1.0 if (ok and blade_confirmed) else 0.5 if ok else 0.0,
        observer=observer)
    return [probe, shards]


def classify_tool_error(tool: str, error: str, service: str,
                        observer: Optional[str] = None) -> List[Observation]:
    """An advertised tool answering 'unknown tool' is a registration anomaly."""
    if "unknown tool" in (error or "").lower():
        return [
            Observation(f"{tool} tool registration", "tool_registration",
                        StatusLevel.ORANGE, f"advertised but returned '{error}'",
                        evidence={"tool": tool, "error": error}, observer=observer),
            Observation(service, "service", StatusLevel.UNKNOWN,
                        f"not established: only {tool} registration observed",
                        confidence=0.0, observer=observer),
        ]
    return [Observation(tool, "probe", StatusLevel.RED, error or "call failed",
                        evidence={"tool": tool, "error": error}, observer=observer)]


def classify_node(node: str, heartbeat_age_s: Optional[float],
                  max_age_s: float = DEFAULT_MAX_AGE_S,
                  declared_offline: bool = False,
                  observer: Optional[str] = None) -> Observation:
    """A missing or expired heartbeat is absence of evidence, not a sick node."""
    if declared_offline:
        return Observation(node, "node", StatusLevel.UNKNOWN,
                           "offline (declared by owner); not a failure",
                           evidence={"declared_offline": True}, observer=observer)
    if heartbeat_age_s is None:
        return Observation(node, "node", StatusLevel.UNKNOWN,
                           "no heartbeat seen by this observer",
                           confidence=0.0, observer=observer)
    if heartbeat_age_s > max_age_s:
        return Observation(node, "node", StatusLevel.UNKNOWN,
                           f"heartbeat stale ({int(heartbeat_age_s)}s); offline or partitioned, not proven sick",
                           evidence={"heartbeat_age_s": heartbeat_age_s},
                           confidence=0.3, observer=observer)
    return Observation(node, "node", StatusLevel.GREEN,
                       f"heartbeat {int(heartbeat_age_s)}s ago",
                       evidence={"heartbeat_age_s": heartbeat_age_s}, observer=observer)
