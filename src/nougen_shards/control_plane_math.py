"""Deterministic control-plane math: Pareto routing, execution Adherence, replay, harness ledger.

Leg 20261001T202909Z, parts 2-4. Pure decision functions remain provider-neutral;
validated JSON adapters are in ``control_plane_api``. The route evaluator does not
dispatch provider calls, and the harness ledger is in-memory rather than durable.
Promotion is NOT reimplemented: ``HarnessLedger.promote`` delegates to the existing
``decision.calibration.promotion_gate`` (which never auto-promotes).

Definitions
-----------
Pareto: candidate a dominates b iff a >= b on every objective and a > b on at least one
(objectives are oriented by an explicit "max"/"min" map). The front is the non-dominated set,
returned in input order. ``route`` picks from the front by an explicit weighted sum over
min-max-normalised objectives; ties break on candidate id so the choice is total.

Adherence (declared workflow edges D vs observed event-stream edges O):
    coverage     = |D ∩ O| / |D|       (declared steps that actually happened)
    undeclared   = |O \\ D| / |O|       (observed steps nobody declared)
Reported separately, never blended; empty denominators give None ("unmeasured" != 0).

Replay: ``replay(log, policy_version, decide)`` folds ``decide`` over the log in order and
returns the decisions plus a SHA-256 digest of (policy_version, log, decisions). Same log +
same policy version must give the same digest; every decision carries its provenance.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

Candidate = Mapping[str, Any]   # {"id": str, <objective>: float, ...}


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# -- Pareto ---------------------------------------------------------------

def _sign(direction: str) -> float:
    if direction not in ("max", "min"):
        raise ValueError("direction must be 'max' or 'min'")
    return 1.0 if direction == "max" else -1.0


def dominates(a: Candidate, b: Candidate, objectives: Mapping[str, str]) -> bool:
    ge = all(_sign(d) * a[o] >= _sign(d) * b[o] for o, d in objectives.items())
    gt = any(_sign(d) * a[o] > _sign(d) * b[o] for o, d in objectives.items())
    return ge and gt


def pareto_front(cands: Sequence[Candidate], objectives: Mapping[str, str]) -> List[Candidate]:
    return [c for c in cands if not any(dominates(o, c, objectives) for o in cands if o is not c)]


def route(cands: Sequence[Candidate], objectives: Mapping[str, str], weights: Mapping[str, float],
          policy_version: str) -> Dict[str, Any]:
    """Choose one candidate from the Pareto front; return the decision with provenance."""
    if not cands:
        raise ValueError("no candidates")
    front = pareto_front(cands, objectives)
    lo = {o: min(c[o] for c in front) for o in objectives}
    hi = {o: max(c[o] for c in front) for o in objectives}

    def util(c: Candidate) -> float:
        total = 0.0
        for o, d in objectives.items():
            span = hi[o] - lo[o]
            x = 0.5 if span == 0 else (c[o] - lo[o]) / span
            total += weights.get(o, 0.0) * (x if d == "max" else 1.0 - x)
        return total

    chosen = max(sorted(front, key=lambda c: str(c["id"])), key=util)
    return {"chosen": chosen["id"], "front": [c["id"] for c in front],
            "provenance": {"policy_version": policy_version, "objectives": dict(objectives),
                           "weights": dict(weights), "inputs_digest": _digest(list(cands))}}


# -- Adherence ------------------------------------------------------------

def adherence(declared: Iterable[Tuple[str, str]], observed: Iterable[Tuple[str, str]]) -> Dict[str, Any]:
    d, o = set(declared), set(observed)
    return {"coverage": (len(d & o) / len(d)) if d else None,
            "undeclared": (len(o - d) / len(o)) if o else None,
            "missing_edges": sorted(d - o), "undeclared_edges": sorted(o - d)}


# -- Replay ---------------------------------------------------------------

def replay(log: Sequence[Mapping[str, Any]], policy_version: str,
           decide: Callable[[Mapping[str, Any], str], Mapping[str, Any]]) -> Dict[str, Any]:
    decisions = []
    for i, event in enumerate(log):
        dec = dict(decide(event, policy_version))
        dec["provenance"] = {**dec.get("provenance", {}), "event_index": i, "policy_version": policy_version}
        decisions.append(dec)
    return {"decisions": decisions,
            "digest": _digest({"policy": policy_version, "log": list(log), "decisions": decisions})}


# -- Harness ledger -------------------------------------------------------

@dataclass
class HarnessLedger:
    """Lineage + negative evidence + rollback. Promotion only via the existing gate."""
    promoted: List[str] = field(default_factory=list)
    parents: Dict[str, Optional[str]] = field(default_factory=dict)
    negative_evidence: List[Dict[str, Any]] = field(default_factory=list)

    def propose(self, hid: str, parent: Optional[str] = None) -> None:
        if hid in self.parents:
            raise ValueError(f"harness {hid!r} already proposed")
        self.parents[hid] = parent

    def promote(self, hid: str, candidate: Any, baseline: Any, **gate_kwargs: Any) -> Dict[str, Any]:
        from .decision.calibration import promotion_gate
        if hid not in self.parents:
            raise KeyError(hid)
        fails = promotion_gate(candidate, baseline, **gate_kwargs)
        if fails:
            self.negative_evidence.append({"harness": hid, "parent": self.parents[hid], "failed_gates": fails})
            return {"promoted": False, "failed_gates": fails}
        self.promoted.append(hid)
        return {"promoted": True, "failed_gates": []}

    def rollback(self) -> Optional[str]:
        """Drop the newest promotion; return the harness now live (None if none)."""
        if self.promoted:
            self.promoted.pop()
        return self.promoted[-1] if self.promoted else None

    @property
    def live(self) -> Optional[str]:
        return self.promoted[-1] if self.promoted else None
