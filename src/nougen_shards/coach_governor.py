"""Coach Governor — ENFORCED budget/lease/kill-switch runtime, not advisory.

Hardens the previously advisory-only Coach/token-budget discipline
(`quota_governor.py`, `reasoning_governor.py`) into real runtime enforcement,
per GM order "build that coach mode shit into core nougen" and the
NouGen Token Hypervisor v1.0 / Coach Governor spec direction relayed in leg
20260913T170403Z (that leg was not reachable this session — see
wargames/coach-governor-hardening.md and wargames/ledger.md for what is
adapted vs. pinned pending GM review).

Design in one sentence: nothing spends before it leases, and a lease is
denied BEFORE the caller's work runs, not after the fact.

Composes with (does not replace) the existing advisory governors:
`quota_governor.QuotaGovernor` and `reasoning_governor.ReasoningGovernor`
still produce recommendations; this module is the independent hard stop.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Env-configurable thresholds (Rule 0.2: dynamic over hardcode, constant only
# as a logged fallback).
# --------------------------------------------------------------------------

def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s=%r is not a float; using fallback %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int; using fallback %s", name, raw, default)
        return default


WATCH_PCT = _env_float("NOUGEN_COACH_WATCH_PCT", 60.0)
THROTTLE_PCT = _env_float("NOUGEN_COACH_THROTTLE_PCT", 80.0)
CONTAINMENT_PCT = _env_float("NOUGEN_COACH_CONTAINMENT_PCT", 90.0)
CHECKPOINT_PCT = _env_float("NOUGEN_COACH_CHECKPOINT_PCT", 97.0)

MAX_FANOUT = _env_int("NOUGEN_COACH_MAX_FANOUT", 8)
MAX_BURN_COUNT = _env_int("NOUGEN_COACH_MAX_BURN_COUNT", 5)
BURN_WINDOW_S = _env_float("NOUGEN_COACH_BURN_WINDOW_S", 10.0)
BURN_SIMILARITY_TOL = _env_float("NOUGEN_COACH_BURN_SIMILARITY_TOL", 0.05)

TELEMETRY_PATH = os.environ.get(
    "NOUGEN_COACH_TELEMETRY_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                 "logs", "coach_governor.jsonl"),
)
NODE_NAME = os.environ.get("NOUGEN_NODE_NAME") or os.environ.get("COMPUTERNAME") or "unknown"


class CircuitLevel(str, Enum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    THROTTLE = "THROTTLE"
    CONTAINMENT = "CONTAINMENT"
    CHECKPOINT = "CHECKPOINT"
    KILL = "KILL"


class CoachGovernorError(Exception):
    """Base for all enforcement denials — always raised BEFORE spend."""


class BudgetExceeded(CoachGovernorError):
    pass


class LeaseDenied(CoachGovernorError):
    pass


class LoopSuspected(LeaseDenied):
    pass


class FanoutExceeded(LeaseDenied):
    pass


class KillSwitchActive(LeaseDenied):
    pass


class CheckpointRequired(LeaseDenied):
    pass


@dataclass
class _Scope:
    path: str
    ceiling: float
    spent: float = 0.0
    reserved: float = 0.0
    fanout_outstanding: int = 0
    checkpoint_ack: bool = True  # True = open; False = CHECKPOINT gate is shut
    killed: bool = False
    kill_reason: str = ""
    charges: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=64))

    @property
    def committed(self) -> float:
        return self.spent + self.reserved

    @property
    def percent_used(self) -> float:
        if self.ceiling <= 0:
            return 0.0
        return (self.committed / self.ceiling) * 100.0

    def level(self) -> CircuitLevel:
        if self.killed:
            return CircuitLevel.KILL
        if not self.checkpoint_ack:
            return CircuitLevel.CHECKPOINT
        pct = self.percent_used
        if pct >= 100.0:
            return CircuitLevel.KILL
        if pct >= CHECKPOINT_PCT:
            return CircuitLevel.CHECKPOINT
        if pct >= CONTAINMENT_PCT:
            return CircuitLevel.CONTAINMENT
        if pct >= THROTTLE_PCT:
            return CircuitLevel.THROTTLE
        if pct >= WATCH_PCT:
            return CircuitLevel.WATCH
        return CircuitLevel.NORMAL


def _parent_path(scope_path: str) -> Optional[str]:
    """'machine/provider/agent/task' -> 'machine/provider/agent'; None at root."""
    if "/" not in scope_path:
        return None
    return scope_path.rsplit("/", 1)[0]


def _ancestor_chain(scope_path: str) -> List[str]:
    """Root-first list of this scope and every ancestor, e.g.
    ['machine', 'machine/providerA', 'machine/providerA/agent1']."""
    parts = scope_path.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


class Lease:
    """Context-manager handle for a reserved spend. settle() reconciles the
    estimate to the actual amount; __exit__ auto-settles at the estimate if
    the caller never calls settle() explicitly (fail-safe, not fail-open)."""

    def __init__(self, governor: "CoachGovernor", scope_path: str,
                 estimate: float, kind: str, lease_id: str):
        self._governor = governor
        self.scope_path = scope_path
        self.estimate = estimate
        self.kind = kind
        self.lease_id = lease_id
        self._settled = False

    def settle(self, actual_amount: Optional[float] = None) -> None:
        if self._settled:
            return
        self._governor._settle(self, actual_amount)
        self._settled = True

    def __enter__(self) -> "Lease":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.settle(self.estimate if self._settled is False and exc_type else None)


class CoachGovernor:
    """The hard stop. One instance is meant to be process-wide (or shared via
    a persisted state file across a session's tool calls)."""

    def __init__(self, telemetry_path: Optional[str] = None):
        self._lock = threading.RLock()
        self._scopes: Dict[str, _Scope] = {}
        self._telemetry_path = telemetry_path or TELEMETRY_PATH

    # -- scope management -------------------------------------------------
    def register_scope(self, scope_path: str, ceiling: float) -> None:
        """Idempotent: re-registering an existing scope raises its ceiling
        without resetting spend (a ceiling bump, never a stealth reset)."""
        with self._lock:
            existing = self._scopes.get(scope_path)
            if existing is None:
                self._scopes[scope_path] = _Scope(path=scope_path, ceiling=ceiling)
            else:
                existing.ceiling = ceiling

    def _get_or_create(self, scope_path: str) -> _Scope:
        scope = self._scopes.get(scope_path)
        if scope is None:
            # Unregistered ancestors get an effectively unbounded ceiling —
            # only explicitly registered scopes enforce a real cap. This
            # keeps registration additive: a task can lease under a machine
            # scope nobody set a ceiling for without being denied by default.
            scope = _Scope(path=scope_path, ceiling=float("inf"))
            self._scopes[scope_path] = scope
        return scope

    # -- kill switch --------------------------------------------------------
    def set_kill(self, scope_path: str, reason: str = "") -> None:
        with self._lock:
            scope = self._get_or_create(scope_path)
            scope.killed = True
            scope.kill_reason = reason
        self._emit("kill_set", scope_path, 0.0, CircuitLevel.KILL, reason)
        logger.warning("coach_governor: KILL set on %s (%s)", scope_path, reason)

    def clear_kill(self, scope_path: str, reason: str = "") -> None:
        """Explicit human/GM action only — never auto-cleared by a provider
        quota reset (ledger.md: provider-reset-cannot-bypass-authorization)."""
        with self._lock:
            scope = self._get_or_create(scope_path)
            scope.killed = False
            scope.kill_reason = ""
        self._emit("kill_cleared", scope_path, 0.0, CircuitLevel.NORMAL, reason)
        logger.warning("coach_governor: KILL cleared on %s (%s)", scope_path, reason)

    def ack_checkpoint(self, scope_path: str, reason: str = "") -> None:
        with self._lock:
            scope = self._get_or_create(scope_path)
            scope.checkpoint_ack = True
        self._emit("checkpoint_ack", scope_path, 0.0, CircuitLevel.NORMAL, reason)

    # -- the hard stop ------------------------------------------------------
    def acquire_lease(self, scope_path: str, estimated_amount: float, *,
                       kind: str = "spend", provider: str = "", model: str = "",
                       agent: str = "", task: str = "", tool: str = "",
                       consequence_class: int = 0) -> Lease:
        """Reserve `estimated_amount` against `scope_path` and every ancestor.
        Denies (raises) BEFORE any counter changes and before the caller does
        any work — this is the fix for the advisory-only failure mode."""
        chain = _ancestor_chain(scope_path)
        with self._lock:
            scopes = [self._get_or_create(p) for p in chain]

            # 1. kill switch — checked first, unconditionally, no short-circuit.
            for s in scopes:
                if s.killed:
                    self._emit("lease_denied_kill", scope_path, estimated_amount,
                               CircuitLevel.KILL, s.kill_reason,
                               provider=provider, model=model, agent=agent,
                               task=task, tool=tool)
                    raise KillSwitchActive(
                        f"scope {s.path!r} killed: {s.kill_reason or 'no reason given'}")

            # 2. checkpoint gate.
            for s in scopes:
                if not s.checkpoint_ack:
                    self._emit("lease_denied_checkpoint", scope_path, estimated_amount,
                               CircuitLevel.CHECKPOINT, "",
                               provider=provider, model=model, agent=agent,
                               task=task, tool=tool)
                    raise CheckpointRequired(
                        f"scope {s.path!r} is CHECKPOINT-gated; call ack_checkpoint()")

            # 3. circuit-breaker level per nearest finite-ceiling ancestor,
            #    worst level across the chain wins.
            worst = CircuitLevel.NORMAL
            levels_order = [CircuitLevel.NORMAL, CircuitLevel.WATCH,
                             CircuitLevel.THROTTLE, CircuitLevel.CONTAINMENT,
                             CircuitLevel.CHECKPOINT, CircuitLevel.KILL]
            for s in scopes:
                lvl = s.level()
                if levels_order.index(lvl) > levels_order.index(worst):
                    worst = lvl

            if worst == CircuitLevel.CONTAINMENT and consequence_class > 1:
                self._emit("lease_denied_containment", scope_path, estimated_amount,
                           worst, "non-reversible work denied under CONTAINMENT",
                           provider=provider, model=model, agent=agent,
                           task=task, tool=tool)
                raise LeaseDenied(
                    "CONTAINMENT: only consequence_class<=1 (reversible/local) work allowed")

            if worst == CircuitLevel.THROTTLE:
                cap = _env_float("NOUGEN_COACH_THROTTLE_CAP", 1.0)
                for s in scopes:
                    if s.ceiling != float("inf") and estimated_amount > s.ceiling * cap:
                        self._emit("lease_denied_throttle", scope_path, estimated_amount,
                                   worst, f"exceeds throttle cap {cap} of {s.path} ceiling",
                                   provider=provider, model=model, agent=agent,
                                   task=task, tool=tool)
                        raise LeaseDenied(
                            f"THROTTLE: request {estimated_amount} exceeds cap on {s.path}")

            # 4. loop / burn-velocity detection.
            now = time.time()
            leaf = scopes[-1]
            recent = [(t, a) for (t, a) in leaf.charges if now - t <= BURN_WINDOW_S]
            if len(recent) >= MAX_BURN_COUNT:
                amounts = [a for _, a in recent] + [estimated_amount]
                avg = sum(amounts) / len(amounts)
                if avg > 0 and all(abs(a - avg) / avg <= BURN_SIMILARITY_TOL for a in amounts):
                    self._emit("lease_denied_loop", scope_path, estimated_amount,
                               worst, f"{len(recent)} near-identical charges in {BURN_WINDOW_S}s",
                               provider=provider, model=model, agent=agent,
                               task=task, tool=tool)
                    raise LoopSuspected(
                        f"burn-velocity loop suspected on {leaf.path}: "
                        f"{len(recent)} near-identical charges in {BURN_WINDOW_S}s")

            # 5. fanout limit for child-agent leases.
            if kind == "child_agent":
                parent = leaf
                if parent.fanout_outstanding >= MAX_FANOUT:
                    self._emit("lease_denied_fanout", scope_path, estimated_amount,
                               worst, f"{parent.fanout_outstanding} >= {MAX_FANOUT}",
                               provider=provider, model=model, agent=agent,
                               task=task, tool=tool)
                    raise FanoutExceeded(
                        f"fanout limit {MAX_FANOUT} reached on {parent.path}")

            # 6. ceiling check — the actual budget math. Compute-then-commit:
            #    verify every ancestor BEFORE mutating any of them.
            for s in scopes:
                if s.ceiling != float("inf") and s.committed + estimated_amount > s.ceiling:
                    self._emit("lease_denied_ceiling", scope_path, estimated_amount,
                               worst, f"{s.path} committed={s.committed} ceiling={s.ceiling}",
                               provider=provider, model=model, agent=agent,
                               task=task, tool=tool)
                    raise BudgetExceeded(
                        f"scope {s.path!r} would exceed ceiling: "
                        f"{s.committed} + {estimated_amount} > {s.ceiling}")

            # All checks passed — commit the reservation atomically.
            for s in scopes:
                s.reserved += estimated_amount
            if kind == "child_agent":
                leaf.fanout_outstanding += 1

            lease_id = uuid.uuid4().hex[:12]
            self._emit("lease_granted", scope_path, estimated_amount, worst, "",
                       provider=provider, model=model, agent=agent,
                       task=task, tool=tool)
            return Lease(self, scope_path, estimated_amount, kind, lease_id)

    def _settle(self, lease: Lease, actual_amount: Optional[float]) -> None:
        amount = lease.estimate if actual_amount is None else actual_amount
        chain = _ancestor_chain(lease.scope_path)
        now = time.time()
        with self._lock:
            for p in chain:
                s = self._get_or_create(p)
                s.reserved = max(0.0, s.reserved - lease.estimate)
                s.spent += amount
            leaf = self._get_or_create(lease.scope_path)
            leaf.charges.append((now, amount))
            if lease.kind == "child_agent":
                leaf.fanout_outstanding = max(0, leaf.fanout_outstanding - 1)
            # a scope that just crossed CHECKPOINT gets gated shut going forward.
            for p in chain:
                s = self._get_or_create(p)
                if s.level() == CircuitLevel.CHECKPOINT and s.checkpoint_ack:
                    s.checkpoint_ack = False
        self._emit("lease_settled", lease.scope_path, amount, self.level(lease.scope_path), "")

    # -- introspection --------------------------------------------------------
    def level(self, scope_path: str) -> CircuitLevel:
        with self._lock:
            worst = CircuitLevel.NORMAL
            order = [CircuitLevel.NORMAL, CircuitLevel.WATCH, CircuitLevel.THROTTLE,
                     CircuitLevel.CONTAINMENT, CircuitLevel.CHECKPOINT, CircuitLevel.KILL]
            for p in _ancestor_chain(scope_path):
                s = self._scopes.get(p)
                if s is None:
                    continue
                lvl = s.level()
                if order.index(lvl) > order.index(worst):
                    worst = lvl
            return worst

    def status(self, scope_path: str) -> Dict[str, object]:
        with self._lock:
            s = self._scopes.get(scope_path)
            if s is None:
                return {"scope": scope_path, "registered": False}
            return {
                "scope": s.path, "registered": True, "ceiling": s.ceiling,
                "spent": s.spent, "reserved": s.reserved, "committed": s.committed,
                "percent_used": round(s.percent_used, 2), "level": s.level().value,
                "killed": s.killed, "kill_reason": s.kill_reason,
                "checkpoint_open": s.checkpoint_ack,
                "fanout_outstanding": s.fanout_outstanding,
                "recent_charges": list(s.charges),
            }

    def burn_rate(self, scope_path: str, window_s: float = BURN_WINDOW_S) -> float:
        with self._lock:
            s = self._scopes.get(scope_path)
            if s is None:
                return 0.0
            now = time.time()
            return sum(a for t, a in s.charges if now - t <= window_s)

    # -- telemetry --------------------------------------------------------
    def _emit(self, event: str, scope_path: str, amount: float, level: CircuitLevel,
               reason: str, *, provider: str = "", model: str = "", agent: str = "",
               task: str = "", tool: str = "") -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "machine": NODE_NAME, "provider": provider, "model": model,
            "agent": agent, "task": task, "tool": tool,
            "scope_path": scope_path, "event": event, "amount": amount,
            "level": level.value, "reason": reason,
        }
        try:
            path = self._telemetry_path
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError as exc:  # telemetry is best-effort, never blocks a decision
            logger.warning("coach_governor: telemetry write failed: %s: %s",
                           type(exc).__name__, exc)


_default_governor: Optional[CoachGovernor] = None
_default_lock = threading.Lock()


def get_default_governor() -> CoachGovernor:
    """Process-wide singleton — the enforcement point every caller should
    share so leases are denied against the SAME ledger, not a fresh one."""
    global _default_governor
    with _default_lock:
        if _default_governor is None:
            _default_governor = CoachGovernor()
        return _default_governor
