"""EvidenceSufficiency: the gate between "interesting" and "adopted".

Owner leg 20260923T034306Z (PR-C). Promotes the primitive proven in
ShadowDweller's ``nougenfight_replay.evidence_sufficient`` into a real gate
with a candidate record, receipts and a rollback path.

The rule this exists to enforce: **NouGen must not adapt routing or retrieval
policy because one event was interesting.** Dream may propose, Build may
prototype, Evolve may promote ONLY when this gate says ELIGIBLE and the
authority rules permit.

Design stance
-------------
* The gate REFUSES by default. Every path that cannot prove eligibility
  returns a blocking status with a reason, never a shrug.
* A status is a pure function of the evidence bundle: the same bundle always
  yields the same status, so a promotion decision can be re-derived and
  audited later rather than taken on trust.
* Touching a hard invariant does not merely warn -- it demands a higher
  authority than the change itself can grant. A policy cannot authorise its
  own exception.
* Nothing here mutates production. This module decides and records; applying a
  decision is the caller's separate, explicit act.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


class Status(str, Enum):
    OBSERVE = "OBSERVE"          # gathering; far below threshold
    SHADOW = "SHADOW"            # enough to run alongside, not to adopt
    ELIGIBLE = "ELIGIBLE"        # evidence supports promotion; authority still applies
    BLOCKED = "BLOCKED"          # a regression or invariant forbids it
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"


class Authority(str, Enum):
    """Who may promote. Ordered: each level subsumes the ones before it."""
    AUTOMATIC = "automatic"      # the loop may adopt without a human
    LANE = "lane"                # an owning lane signs off
    OWNER = "owner"              # the human author (Dave) signs off

    @property
    def rank(self) -> int:
        return {"automatic": 0, "lane": 1, "owner": 2}[self.value]


# Defaults are deliberately conservative. A caller may raise them, never
# silently lower them below MIN_FLOOR.
MIN_SAMPLES = 20
MIN_FLOOR = 5
SHADOW_SAMPLES = 5


@dataclass(frozen=True)
class EvidenceReceipt:
    """One observation that argues for or against the hypothesis."""
    source: str                  # where it came from (replay trial, live task, ...)
    observation: str
    delta: float                 # signed effect; positive favours the candidate
    trials: int = 1

    @property
    def receipt_id(self) -> str:
        blob = f"{self.source}:{self.observation}:{self.delta}:{self.trials}"
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Metrics:
    """Baseline vs candidate on the same measurement."""
    name: str
    baseline: float
    candidate: float
    higher_is_better: bool = True

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline

    @property
    def regressed(self) -> bool:
        return self.delta < 0 if self.higher_is_better else self.delta > 0


@dataclass(frozen=True)
class PolicyCandidate:
    """The full record a promotion decision is derived from."""
    policy_id: str
    version: str
    hypothesis: str
    receipts: Tuple[EvidenceReceipt, ...] = ()
    metrics: Tuple[Metrics, ...] = ()
    invariants_touched: Tuple[str, ...] = ()
    rollback_to: Optional[str] = None
    required_authority: Authority = Authority.LANE
    min_samples: int = MIN_SAMPLES

    @property
    def sample_count(self) -> int:
        return sum(r.trials for r in self.receipts)

    @property
    def effect(self) -> float:
        """Sample-weighted mean effect across receipts."""
        n = self.sample_count
        if not n:
            return 0.0
        return sum(r.delta * r.trials for r in self.receipts) / n

    @property
    def regressions(self) -> Tuple[str, ...]:
        return tuple(m.name for m in self.metrics if m.regressed)

    @property
    def bundle_id(self) -> str:
        """Identity of the EVIDENCE, not the record: two candidates with the
        same evidence must reach the same verdict."""
        blob = json.dumps({
            "policy": self.policy_id, "version": self.version,
            "receipts": sorted(r.receipt_id for r in self.receipts),
            "metrics": sorted((m.name, m.baseline, m.candidate, m.higher_is_better)
                              for m in self.metrics),
            "invariants": sorted(self.invariants_touched),
        }, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Verdict:
    status: Status
    reason: str
    bundle_id: str
    sample_count: int
    effect: float
    regressions: Tuple[str, ...]
    required_authority: Authority
    promotable_by: Optional[Authority] = None

    @property
    def eligible(self) -> bool:
        return self.status is Status.ELIGIBLE

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["required_authority"] = self.required_authority.value
        d["promotable_by"] = self.promotable_by.value if self.promotable_by else None
        d["regressions"] = list(self.regressions)
        return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def evaluate(candidate: PolicyCandidate) -> Verdict:
    """Pure: the same evidence bundle always yields the same status.

    Order matters. A regression or an invariant blocks regardless of how much
    evidence was gathered -- volume of data never buys a exemption from a
    hard rule.
    """
    base = dict(bundle_id=candidate.bundle_id, sample_count=candidate.sample_count,
                effect=round(candidate.effect, 6), regressions=candidate.regressions)

    if candidate.regressions:
        return Verdict(Status.BLOCKED,
                       f"regression in {', '.join(candidate.regressions)}: a candidate that "
                       f"loses ground somewhere is not promotable on aggregate improvement",
                       required_authority=candidate.required_authority, **base)

    required = candidate.required_authority
    if candidate.invariants_touched:
        # A change that touches a hard invariant cannot be adopted by the loop,
        # and cannot authorise its own exception.
        required = Authority.OWNER if required.rank < Authority.OWNER.rank else required

    floor = max(candidate.min_samples, MIN_FLOOR)
    n = candidate.sample_count

    if n < SHADOW_SAMPLES:
        return Verdict(Status.OBSERVE,
                       f"{n} observation(s): one interesting event is not a trend "
                       f"(need {SHADOW_SAMPLES} to shadow, {floor} to be eligible)",
                       required_authority=required, **base)
    if n < floor:
        return Verdict(Status.SHADOW,
                       f"{n} of {floor} observations: run alongside and keep measuring, "
                       f"do not adopt",
                       required_authority=required, **base)
    if candidate.effect <= 0.0:
        return Verdict(Status.SHADOW,
                       f"effect {candidate.effect:.4f} is not positive: evidence is "
                       f"sufficient in volume but does not argue for the change",
                       required_authority=required, **base)

    return Verdict(Status.ELIGIBLE,
                   f"{n} observations, effect {candidate.effect:.4f}, no regressions"
                   + (f"; touches invariant(s) {', '.join(candidate.invariants_touched)}, "
                      f"so {required.value} authority is required"
                      if candidate.invariants_touched else ""),
                   required_authority=required, promotable_by=required, **base)


class PromotionRefused(Exception):
    """Raised instead of promoting. Carries the verdict that refused."""

    def __init__(self, message: str, verdict: Verdict):
        super().__init__(message)
        self.verdict = verdict


@dataclass
class EvolveGate:
    """The SRDBE integration point. Dream proposes, Build prototypes, Evolve
    asks HERE before promoting. Keeps an append-only ledger so a promotion or
    rollback can be audited after the fact."""
    ledger: List[Dict[str, Any]] = field(default_factory=list)

    def check(self, candidate: PolicyCandidate) -> Verdict:
        v = evaluate(candidate)
        self.ledger.append({"at": _now(), "action": "check", "policy": candidate.policy_id,
                            "version": candidate.version, **v.to_dict()})
        return v

    def promote(self, candidate: PolicyCandidate, granted_by: Authority) -> Dict[str, Any]:
        """Promote only when the gate says ELIGIBLE *and* the granted authority
        meets what the candidate requires. Both conditions, never one."""
        v = evaluate(candidate)
        if not v.eligible:
            raise PromotionRefused(f"{candidate.policy_id}: {v.status.value} - {v.reason}", v)
        if granted_by.rank < v.required_authority.rank:
            raise PromotionRefused(
                f"{candidate.policy_id}: requires {v.required_authority.value} authority, "
                f"granted {granted_by.value}"
                + (" (touches a hard invariant)" if candidate.invariants_touched else ""), v)
        receipt = {"at": _now(), "action": "promote", "policy": candidate.policy_id,
                   "version": candidate.version, "granted_by": granted_by.value,
                   "rollback_to": candidate.rollback_to, "status": Status.PROMOTED.value,
                   **{k: val for k, val in v.to_dict().items() if k != "status"}}
        self.ledger.append(receipt)
        return receipt

    def rollback(self, policy_id: str, reason: str) -> Dict[str, Any]:
        """Restore the prior version named by the promotion receipt. Refuses if
        the policy was never promoted, or if the promotion recorded nowhere to
        go back to -- an un-revertable change should never have shipped."""
        promo = next((e for e in reversed(self.ledger)
                      if e["policy"] == policy_id and e.get("action") == "promote"), None)
        if promo is None:
            raise PromotionRefused(f"{policy_id}: never promoted, nothing to roll back",
                                   evaluate(PolicyCandidate(policy_id, "0", "n/a")))
        if not promo.get("rollback_to"):
            raise PromotionRefused(f"{policy_id}: promotion recorded no rollback target",
                                   evaluate(PolicyCandidate(policy_id, "0", "n/a")))
        receipt = {"at": _now(), "action": "rollback", "policy": policy_id,
                   "from_version": promo["version"], "restored_version": promo["rollback_to"],
                   "reason": reason, "status": Status.ROLLED_BACK.value,
                   "promotion_bundle": promo.get("bundle_id")}
        self.ledger.append(receipt)
        return receipt

    def current_version(self, policy_id: str) -> Optional[str]:
        """What is actually live for this policy, per the ledger."""
        for e in reversed(self.ledger):
            if e["policy"] != policy_id:
                continue
            if e.get("action") == "promote":
                return e["version"]
            if e.get("action") == "rollback":
                return e["restored_version"]
        return None

    def history(self, policy_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [e for e in self.ledger if policy_id is None or e["policy"] == policy_id]


def from_replay(policy_id: str, version: str, hypothesis: str,
                trials: Sequence[Mapping[str, Any]], metric: str = "effect",
                **kw: Any) -> PolicyCandidate:
    """Adapter for replay corpora (ShadowDweller nougenfight_replay and any
    future fleet harness): one trial, one receipt. Kept generic so no product
    lore enters this module."""
    receipts = tuple(EvidenceReceipt(source=str(t.get("name", f"trial{i}")),
                                     observation=str(t.get("observation", metric)),
                                     delta=float(t.get(metric, 0.0)),
                                     trials=int(t.get("trials", 1)))
                     for i, t in enumerate(trials))
    return PolicyCandidate(policy_id, version, hypothesis, receipts=receipts, **kw)


__all__ = ["Status", "Authority", "EvidenceReceipt", "Metrics", "PolicyCandidate", "Verdict",
           "EvolveGate", "PromotionRefused", "evaluate", "from_replay",
           "MIN_SAMPLES", "MIN_FLOOR", "SHADOW_SAMPLES"]
