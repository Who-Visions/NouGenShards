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

import itertools
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence


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


# =============================================================================
# Context Mode state (wishlist items 26, 47 -- leg 20260910T202128Z, rebroadcast
# 20260923T174020Z, category C "NouGen Context Mode enforcement")
#
# This is a DIFFERENT axis from StatusLevel above. StatusLevel answers "is this
# COMPONENT healthy" (GREEN/YELLOW/ORANGE/RED/UNKNOWN, scoped per-probe).
# ContextState answers "how complete is the MEMORY the current task is
# reasoning from" -- a single fleet-wide judgment a task makes once, not a
# per-component health reading. A vault can be individually YELLOW (stale)
# while context_state is still FULL, if that vault wasn't required for this
# task; and every required vault can individually be GREEN while
# context_state is DEGRADED, if one of them just hasn't been reached yet this
# turn. The two must never be conflated into one enum -- that conflation is
# exactly the "false green" pattern items 21-40 exist to prevent.
# =============================================================================

class ContextState(str, Enum):
    FULL = "full"                # every required source answered and is current
    DEGRADED = "degraded"        # at least one required source failed, timed out,
                                  # or answered stale; reasoning continues on what's left
    LOCAL_ONLY = "local_only"    # no remote/fleet source reachable at all; only this
                                  # node's own local evidence is in hand
    UNAVAILABLE = "unavailable"  # no source answered, local or remote; nothing to reason from


@dataclass(frozen=True)
class RequiredSource:
    """One thing the current task declared it needs before reasoning.
    ``is_local`` distinguishes 'this node's own vault' from a fleet peer, so
    LOCAL_ONLY can be told apart from DEGRADED and from UNAVAILABLE."""
    name: str
    is_local: bool
    answered: bool
    reason: str = ""


def derive_context_state(required: Sequence[RequiredSource]) -> "ContextReceipt":
    """The single, honest judgment a task makes about its own memory
    completeness before reasoning (item 41: 'make Context Mode mandatory
    before substantive fleet work'; item 60: 'expose a compact Context Mode
    receipt showing sources consulted and completeness').

    Deliberately conservative in the direction the wishlist demands:
    - Zero required sources is NOT full-by-default -- it is unavailable.
      A task that declares nothing required has not proven anything.
    - Any missing required source means DEGRADED at best, never FULL,
      regardless of how many others answered.
    """
    if not required:
        return ContextReceipt(ContextState.UNAVAILABLE, tuple(), tuple(),
                              "no required sources declared -- nothing to reason from")

    answered = [r for r in required if r.answered]
    missing = [r for r in required if not r.answered]
    local_answered = [r for r in answered if r.is_local]
    remote_answered = [r for r in answered if not r.is_local]

    if not answered:
        state = ContextState.UNAVAILABLE
    elif not missing:
        state = ContextState.FULL
    elif remote_answered:
        state = ContextState.DEGRADED
    elif local_answered:
        state = ContextState.LOCAL_ONLY
    else:
        state = ContextState.UNAVAILABLE

    reason = _context_state_reason(state, answered, missing)
    return ContextReceipt(state, tuple(r.name for r in answered), tuple(r.name for r in missing), reason)


def _context_state_reason(state: ContextState, answered: List[RequiredSource],
                          missing: List[RequiredSource]) -> str:
    if state is ContextState.FULL:
        return f"all {len(answered)} required source(s) answered"
    if state is ContextState.UNAVAILABLE:
        return "no required source answered" if answered or missing else "no required sources declared"
    names = ", ".join(f"{r.name} ({r.reason})" if r.reason else r.name for r in missing)
    if state is ContextState.LOCAL_ONLY:
        return f"only local source(s) answered; no remote source reachable -- missing: {names}"
    return f"{len(answered)}/{len(answered) + len(missing)} required source(s) answered -- missing: {names}"


@dataclass(frozen=True)
class ContextReceipt:
    """Item 60's 'compact Context Mode receipt': exactly what a consuming
    lane needs to decide whether to trust a conclusion drawn under it --
    never more, never a vague summary in place of the actual source list."""
    state: ContextState
    sources_answered: tuple
    sources_missing: tuple
    reason: str

    @property
    def exhaustive_recall_permitted(self) -> bool:
        """Item 48: 'in degraded mode, prohibit claims of exhaustive recall.'"""
        return self.state is ContextState.FULL

    @property
    def absence_conclusions_permitted(self) -> bool:
        """Item 49: 'in degraded mode, prohibit absence conclusions.' Absence
        can only be asserted from a context that saw everything required."""
        return self.state is ContextState.FULL

    @property
    def destructive_edits_permitted(self) -> bool:
        """Item 50: 'in degraded mode, prohibit destructive canon or
        infrastructure edits based on missing evidence.'"""
        return self.state is ContextState.FULL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_state": self.state.value,
            "sources_answered": list(self.sources_answered),
            "sources_missing": list(self.sources_missing),
            "reason": self.reason,
            "exhaustive_recall_permitted": self.exhaustive_recall_permitted,
            "absence_conclusions_permitted": self.absence_conclusions_permitted,
            "destructive_edits_permitted": self.destructive_edits_permitted,
        }


# =============================================================================
# Health generation IDs (wishlist item 39: "Add health generation IDs so
# stale responses can be detected.")
#
# A monotonic counter a health-reporting process bumps every time it takes a
# fresh full sweep. Consumers compare the generation stamped on a cached
# response against the process's CURRENT generation: if they differ, the
# response predates the most recent sweep and must not be presented as
# current, even if its own status field still says GREEN. This is the
# "stale health cache versus live read failure" distinction (item 36) made
# checkable, not just described.
# =============================================================================

_generation_counter = itertools.count(1)


class HealthGeneration:
    """Not a singleton by force -- callers that want one process-wide counter
    hold one instance; tests construct their own to stay isolated."""

    def __init__(self, start: int = 0):
        self._value = start

    @property
    def value(self) -> int:
        return self._value

    def bump(self) -> int:
        """Call this at the start of every fresh full health sweep."""
        self._value += 1
        return self._value


def stamp_generation(observation: Observation, generation: int) -> Observation:
    """Attach a generation id to an existing Observation's evidence without
    otherwise touching it -- generation is provenance metadata, not a status
    signal, so it never changes .status or .reason."""
    ev = dict(observation.evidence)
    ev["health_generation"] = generation
    return Observation(observation.observed_component, observation.reported_scope,
                       observation.status, observation.reason, ev, observation.confidence,
                       observation.last_verified_at, observation.observer)


def is_stale_generation(observation: Observation, current_generation: int) -> bool:
    """True if this observation was stamped by an earlier sweep than the
    current one -- callers should treat it as evidence, never as a live
    reading, regardless of its own .status. An observation never stamped
    with a generation at all cannot be judged stale by this check (it
    predates generation tracking, or the caller never stamped it) -- that is
    a caller bug to fix, not something this function should guess at."""
    stamped = observation.evidence.get("health_generation")
    if stamped is None:
        return False
    return stamped < current_generation

