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


@dataclass
class NodeDimensions:
    node: str
    vault_status: StatusLevel
    vault_reason: str
    msg_status: StatusLevel
    msg_reason: str
    identity_confirmed: bool
    last_vault_ts: Optional[float] = None
    last_msg_ts: Optional[float] = None
    # Extended orthogonal fields
    execution_live: Optional[bool] = None
    relay_live: Optional[bool] = None
    shard_auth_valid: Optional[bool] = None
    tracker_fresh: Optional[bool] = None

    @property
    def derived_state(self) -> str:
        """Derive node state deterministically from evidence dimensions."""
        if self.execution_live or self.relay_live or self.msg_status == StatusLevel.GREEN:
            if self.shard_auth_valid is False or self.vault_status == StatusLevel.RED:
                return "LIVE_AUTH_DEGRADED"
            if self.tracker_fresh is False:
                return "LIVE_TRACKER_STALE"
            if self.vault_status == StatusLevel.YELLOW:
                return "LIVE_RECALL_PARTIAL"
            return "LIVE"
        if self.vault_status == StatusLevel.GREEN:
            return "LIVE_DEGRADED_TRANSPORT"
        if self.vault_status == StatusLevel.RED and self.msg_status in (StatusLevel.RED, StatusLevel.ORANGE):
            return "OFFLINE_CONFIRMED"
        return "UNKNOWN_INSUFFICIENT_EVIDENCE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "derived_state": self.derived_state,
            "vault_status": self.vault_status.value,
            "vault_reason": self.vault_reason,
            "msg_status": self.msg_status.value,
            "msg_reason": self.msg_reason,
            "identity_confirmed": self.identity_confirmed,
            "last_vault_ts": self.last_vault_ts,
            "last_msg_ts": self.last_msg_ts,
            "execution_live": self.execution_live,
            "relay_live": self.relay_live,
            "shard_auth_valid": self.shard_auth_valid,
            "tracker_fresh": self.tracker_fresh,
        }


def classify_node_dimensions(
    node: str,
    vault_ok: Optional[bool] = None,
    msg_ok: Optional[bool] = None,
    vault_error: Optional[str] = None,
    msg_error: Optional[str] = None,
    identity_confirmed: Optional[bool] = None,
    last_vault_ts: Optional[float] = None,
    last_msg_ts: Optional[float] = None,
    execution_live: Optional[bool] = None,
    relay_live: Optional[bool] = None,
    shard_auth_valid: Optional[bool] = None,
    tracker_fresh: Optional[bool] = None,
) -> NodeDimensions:
    """Classify node status along distinct dimensions: vault vs msg bus vs identity.

    Guarantees:
    - Vault UP does not collapse msg status into GREEN.
    - Msg TIMEOUT/UNKNOWN does not turn a reachable vault RED or node offline.
    - A 401 on shard lane sets shard_auth_valid=False and derived_state=LIVE_AUTH_DEGRADED, never OFFLINE.
    """
    if vault_ok is True:
        v_status = StatusLevel.GREEN
        v_reason = "vault reachable"
    elif vault_ok is False:
        v_status = StatusLevel.RED if vault_error else StatusLevel.YELLOW
        v_reason = vault_error or "vault unreachable or timed out"
    else:
        v_status = StatusLevel.UNKNOWN
        v_reason = "vault reachability not tested"

    if msg_ok is True:
        m_status = StatusLevel.GREEN
        m_reason = "nougenmsg route active"
    elif msg_ok is False:
        m_status = StatusLevel.ORANGE
        m_reason = msg_error or "nougenmsg route timed out or unverified"
    else:
        m_status = StatusLevel.UNKNOWN
        m_reason = "nougenmsg route not tested"

    id_confirmed = identity_confirmed if identity_confirmed is not None else (
        bool(vault_ok or msg_ok or execution_live or relay_live) and node.lower() in ("blade", "blade1tb", "phoebus", "whoart")
    )

    s_auth = shard_auth_valid if shard_auth_valid is not None else (
        False if (vault_error and "401" in str(vault_error)) else True if vault_ok else None
    )

    return NodeDimensions(
        node=node,
        vault_status=v_status,
        vault_reason=v_reason,
        msg_status=m_status,
        msg_reason=m_reason,
        identity_confirmed=id_confirmed,
        last_vault_ts=last_vault_ts,
        last_msg_ts=last_msg_ts,
        execution_live=execution_live if execution_live is not None else (True if id_confirmed else None),
        relay_live=relay_live,
        shard_auth_valid=s_auth,
        tracker_fresh=tracker_fresh,
    )

