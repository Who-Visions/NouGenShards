"""Evaluation for bounded judgments: pure functions over plain records.

No dependency on any backend or on the plane's receipt type: an adapter turns a
receipt (or a stored corpus row) into an ``EvalRecord``. Numbers only, no verdicts:
``promotion_gate`` says which gates failed, it never says "ship it".

Hard rules baked in:
  * report tp/fn/fp/tn-style counts and per-class numbers, not one headline ratio;
  * every metric that needs data returns ``None`` on empty input instead of 0.0, so a
    missing measurement can never read as a perfect one;
  * cost of a miss is a matrix the domain supplies, not a constant.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class EvalRecord:
    truth: str
    predicted: Optional[str]              # None = the backend abstained
    confidence: Optional[float] = None    # None = UNCALIBRATED (constrained decoding gives no
                                          # probabilities); 0.0 is a real, very low confidence
    probabilities: Mapping[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    escalated: bool = False               # routed to LLM/human instead of accepted
    repeat_predictions: Tuple[str, ...] = ()  # same input re-run: stability check


@dataclass(frozen=True)
class EvalReport:
    n: int
    accuracy: Optional[float]
    precision: Dict[str, Optional[float]]
    recall: Dict[str, Optional[float]]
    f1: Dict[str, Optional[float]]
    confusion: Dict[str, Dict[str, int]]
    weighted_false_negative_cost: Optional[float]
    brier_score: Optional[float]
    expected_calibration_error: Optional[float]
    uncalibrated_rate: Optional[float]
    abstain_rate: Optional[float]
    escalation_rate: Optional[float]
    stability_rate: Optional[float]
    p50_latency_ms: Optional[float]
    p95_latency_ms: Optional[float]
    cost_per_1000: Optional[float]


def _div(a: float, b: float) -> Optional[float]:
    return None if b == 0 else a / b


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    """Nearest-rank percentile, q in [0, 100]."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def confusion_matrix(records: Iterable[EvalRecord], labels: Sequence[str]) -> Dict[str, Dict[str, int]]:
    """matrix[truth][predicted]; abstentions land in the 'ABSTAIN' column."""
    cols = list(labels) + ["ABSTAIN"]
    m = {t: {p: 0 for p in cols} for t in labels}
    for r in records:
        if r.truth not in m:
            raise ValueError(f"truth {r.truth!r} not in label set")
        pred = r.predicted if r.predicted is not None else "ABSTAIN"
        if pred not in m[r.truth]:
            raise ValueError(f"predicted {pred!r} not in label set")
        m[r.truth][pred] += 1
    return m


def brier(records: Sequence[EvalRecord], labels: Sequence[str]) -> Optional[float]:
    """Multiclass Brier over records that carry probabilities."""
    rows = [r for r in records if r.probabilities]
    if not rows:
        return None
    total = 0.0
    for r in rows:
        total += sum((float(r.probabilities.get(lab, 0.0)) - (1.0 if lab == r.truth else 0.0)) ** 2 for lab in labels)
    return total / len(rows)


def expected_calibration_error(records: Sequence[EvalRecord], bins: int = 10) -> Optional[float]:
    """Top-label ECE: how far stated confidence is from observed accuracy, per bin."""
    rows = [r for r in records if r.predicted is not None and r.confidence is not None]
    if not rows:
        return None
    buckets: List[List[EvalRecord]] = [[] for _ in range(bins)]
    for r in rows:
        c = min(max(float(r.confidence), 0.0), 1.0)
        buckets[min(int(c * bins), bins - 1)].append(r)
    ece = 0.0
    for b in buckets:
        if not b:
            continue
        acc = sum(1 for r in b if r.predicted == r.truth) / len(b)
        conf = sum(min(max(float(r.confidence), 0.0), 1.0) for r in b) / len(b)
        ece += (len(b) / len(rows)) * abs(acc - conf)
    return ece


def weighted_miss_cost(records: Iterable[EvalRecord], cost: Mapping[Tuple[str, str], float],
                       abstain_cost: float = 0.0, default: float = 1.0) -> float:
    """Sum of cost[(truth, predicted)] over wrong answers. Right answers cost 0.

    A domain says how bad each mistake is (missing real work >> one extra surfaced leg).
    Unlisted wrong pairs cost ``default``; abstention costs ``abstain_cost``.
    """
    total = 0.0
    for r in records:
        if r.predicted is None:
            total += abstain_cost
        elif r.predicted != r.truth:
            total += float(cost.get((r.truth, r.predicted), default))
    return total


def evaluate(records: Sequence[EvalRecord], labels: Sequence[str],
             cost: Optional[Mapping[Tuple[str, str], float]] = None) -> EvalReport:
    recs = list(records)
    n = len(recs)
    m = confusion_matrix(recs, labels)
    precision: Dict[str, Optional[float]] = {}
    recall: Dict[str, Optional[float]] = {}
    f1: Dict[str, Optional[float]] = {}
    for lab in labels:
        tp = m[lab][lab]
        fn = sum(v for p, v in m[lab].items() if p != lab)
        fp = sum(m[t][lab] for t in labels if t != lab)
        p, rc = _div(tp, tp + fp), _div(tp, tp + fn)
        precision[lab], recall[lab] = p, rc
        f1[lab] = None if p is None or rc is None or (p + rc) == 0 else 2 * p * rc / (p + rc)
    correct = sum(m[lab][lab] for lab in labels)
    stab = [r for r in recs if r.repeat_predictions]
    stable = sum(1 for r in stab if len(set(r.repeat_predictions)) == 1)
    lat = [r.latency_ms for r in recs]
    return EvalReport(
        n=n,
        accuracy=_div(correct, n),
        precision=precision, recall=recall, f1=f1, confusion=m,
        weighted_false_negative_cost=(weighted_miss_cost(recs, cost) if cost is not None and n else None),
        brier_score=brier(recs, labels),
        expected_calibration_error=expected_calibration_error(recs),
        uncalibrated_rate=_div(sum(1 for r in recs if r.predicted is not None and r.confidence is None), n),
        abstain_rate=_div(sum(1 for r in recs if r.predicted is None), n),
        escalation_rate=_div(sum(1 for r in recs if r.escalated), n),
        stability_rate=_div(stable, len(stab)),
        p50_latency_ms=percentile(lat, 50),
        p95_latency_ms=percentile(lat, 95),
        cost_per_1000=_div(sum(r.cost_usd for r in recs) * 1000.0, n),
    )


def threshold_sweep(records: Sequence[EvalRecord], cost: Mapping[Tuple[str, str], float],
                    thresholds: Sequence[float], escalation_cost: float = 0.25,
                    default: float = 1.0) -> List[Dict[str, float]]:
    """For each confidence threshold: accept at or above it, escalate below it.

    Records with no calibrated confidence cannot be thresholded and are skipped (reported
    per row as ``skipped_uncalibrated``): "unknown" is not "low".

    Escalating costs ``escalation_cost`` (a human or bigger model looks) and is assumed
    to get the answer right; accepting a wrong answer costs its matrix entry. Pick the
    threshold from this table, not by feel.
    """
    out = []
    usable = [r for r in records if r.confidence is not None]
    skipped = len(records) - len(usable)
    for t in thresholds:
        accepted = escalated = 0
        total = 0.0
        for r in usable:
            if r.predicted is not None and r.confidence >= t:
                accepted += 1
                if r.predicted != r.truth:
                    total += float(cost.get((r.truth, r.predicted), default))
            else:
                escalated += 1
                total += escalation_cost
        out.append({"threshold": float(t), "accepted": accepted, "escalated": escalated,
                    "total_cost": total, "skipped_uncalibrated": skipped})
    return out


def promotion_gate(candidate: EvalReport, baseline: EvalReport, *, min_examples: int = 300,
                   max_ece: float = 0.10, p95_slo_ms: Optional[float] = None,
                   max_cost_per_1000: Optional[float] = None,
                   fallback_tested: bool = False, replay_stable: bool = False) -> List[str]:
    """Return the gates that FAIL (empty list = every gate passed). Never auto-promotes."""
    fails: List[str] = []
    if candidate.n < min_examples:
        fails.append(f"too few labeled examples: {candidate.n} < {min_examples}")
    c, b = candidate.weighted_false_negative_cost, baseline.weighted_false_negative_cost
    if c is None or b is None:
        fails.append("weighted cost not measured for candidate or baseline")
    elif c > b:
        fails.append(f"weighted cost regressed vs rules: {c:.3f} > {b:.3f}")
    ece = candidate.expected_calibration_error
    if ece is None:
        fails.append("calibration not measurable: backend gives no calibrated confidence")
    elif ece > max_ece:
        fails.append(f"calibration outside tolerance: ece={ece:.3f}")
    if p95_slo_ms is not None and (candidate.p95_latency_ms is None or candidate.p95_latency_ms > p95_slo_ms):
        fails.append(f"p95 latency over SLO: {candidate.p95_latency_ms}")
    if max_cost_per_1000 is not None and (candidate.cost_per_1000 is None or candidate.cost_per_1000 > max_cost_per_1000):
        fails.append(f"cost over budget: {candidate.cost_per_1000}")
    if not fallback_tested:
        fails.append("fallback with the classifier unavailable is not tested")
    if not replay_stable:
        fails.append("replay stability across pinned model versions is not tested")
    return fails


def record_from_receipt(receipt, truth: str, question_key: str, *, escalated: Optional[bool] = None,
                        repeat_predictions: Tuple[str, ...] = ()) -> EvalRecord:
    """Build an EvalRecord from a decision receipt (duck-typed: no import of the plane).

    A value with confidence 0.0 and no probabilities is UNCALIBRATED, not low-confidence.
    A missing value or an ABSTAIN escalation is an abstention.
    """
    val = None
    for v in getattr(receipt, "values", ()) or ():
        if getattr(v, "key", None) == question_key:
            val = v
            break
    esc = getattr(getattr(receipt, "escalation", None), "value", getattr(receipt, "escalation", None))
    abstained = val is None or esc == "abstain"
    probs = dict(getattr(val, "probabilities", {}) or {}) if val is not None else {}
    conf = getattr(val, "confidence", None) if val is not None else None
    if conf is not None and float(conf) == 0.0 and not probs:
        conf = None
    return EvalRecord(
        truth=truth,
        predicted=None if abstained else str(getattr(val, "value")),
        confidence=None if conf is None else float(conf),
        probabilities=probs,
        latency_ms=float(getattr(receipt, "latency_ms", 0.0) or 0.0),
        cost_usd=float(getattr(receipt, "estimated_cost_usd", 0.0) or 0.0),
        escalated=bool(esc in ("llm", "human", "retry")) if escalated is None else escalated,
        repeat_predictions=repeat_predictions,
    )
