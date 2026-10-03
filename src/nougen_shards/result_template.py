"""
Universal Deterministic Result Engine & Evaluation Interval Template Evaluator.

Implements the bounded interval evaluation contract:
  - Templates define weighted criteria (metrics), optional hard gates, and pass threshold tau.
  - Unknown/missing metrics contribute 0 to R_min and 1 to R_max.
  - Interval [R_min, R_max] satisfies 0 <= R_min <= R_max <= 1.
  - PASS iff all hard gates pass and R_min >= tau.
  - FAIL iff any hard gate fails or R_max < tau.
  - UNKNOWN_WITHIN_BUDGET iff hard gates pass and R_min < tau <= R_max.
  - Produces canonical SHA-256 provenance hashes over canonical evidence and template data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class EvaluationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN_WITHIN_BUDGET = "UNKNOWN_WITHIN_BUDGET"


@dataclass(frozen=True)
class MetricCriterion:
    """A weighted metric criterion evaluated against evidence."""
    name: str
    weight: float
    description: str = ""
    min_value: float = 0.0
    max_value: float = 1.0


@dataclass(frozen=True)
class ResultTemplate:
    """Versioned deterministic evaluation template."""
    template_id: str
    version: str
    tau: float  # Pass threshold in [0.0, 1.0]
    metrics: Tuple[MetricCriterion, ...]
    hard_gates: Tuple[str, ...] = ()  # Metric or check names that must evaluate to True/1.0
    description: str = ""

    def __post_init__(self):
        if not (0.0 <= self.tau <= 1.0):
            raise ValueError(f"Pass threshold tau must be in [0.0, 1.0], got {self.tau}")
        total_weight = sum(m.weight for m in self.metrics)
        if total_weight <= 0:
            raise ValueError(f"Total metric weight must be positive, got {total_weight}")

    def canonical_hash(self) -> str:
        """Deterministic SHA-256 hash of the template specification."""
        payload = {
            "template_id": self.template_id,
            "version": self.version,
            "tau": round(self.tau, 6),
            "hard_gates": sorted(self.hard_gates),
            "metrics": [
                {
                    "name": m.name,
                    "weight": round(m.weight, 6),
                    "min_value": round(m.min_value, 6),
                    "max_value": round(m.max_value, 6),
                }
                for m in sorted(self.metrics, key=lambda m: m.name)
            ]
        }
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@dataclass
class EvaluationIntervalResult:
    """Bounded evaluation outcome."""
    template_id: str
    template_version: str
    template_hash: str
    evidence_hash: str
    r_min: float
    r_max: float
    coverage: float
    tau: float
    hard_gates_passed: bool
    status: EvaluationStatus
    hard_gate_failures: List[str] = field(default_factory=list)
    metric_scores: Dict[str, Optional[float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_version": self.template_version,
            "template_hash": self.template_hash,
            "evidence_hash": self.evidence_hash,
            "r_min": round(self.r_min, 6),
            "r_max": round(self.r_max, 6),
            "coverage": round(self.coverage, 6),
            "tau": round(self.tau, 6),
            "hard_gates_passed": self.hard_gates_passed,
            "status": self.status.value,
            "hard_gate_failures": self.hard_gate_failures,
            "metric_scores": self.metric_scores,
        }


def compute_evidence_hash(evidence: Dict[str, Any]) -> str:
    """Compute canonical SHA-256 hash over an evidence dictionary."""
    canonical_json = json.dumps(evidence, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def evaluate_result(
    evidence: Dict[str, Any],
    template: ResultTemplate
) -> EvaluationIntervalResult:
    """
    Deterministic evaluation of evidence against a ResultTemplate.
    Computes interval bounds [R_min, R_max]:
      - Unknown evidence metrics contribute 0 to R_min and 1 to R_max.
      - Known evidence metrics are normalized into [0.0, 1.0] and contribute proportionally.
    """
    total_weight = sum(m.weight for m in template.metrics)
    accum_min = 0.0
    accum_max = 0.0
    known_weight = 0.0

    hard_gate_failures = []
    metric_scores: Dict[str, Optional[float]] = {}

    # 1. Check hard gates
    for gate in template.hard_gates:
        val = evidence.get(gate)
        # Gate passes if value is True, 1, or positive score
        if val is None or val is False or val == 0:
            hard_gate_failures.append(gate)

    hard_gates_passed = (len(hard_gate_failures) == 0)

    # 2. Evaluate weighted metrics
    for m in template.metrics:
        raw_val = evidence.get(m.name)
        if raw_val is None:
            # Unknown metric: 0 contribution to min, full contribution (1.0) to max
            accum_min += 0.0
            accum_max += m.weight * 1.0
            metric_scores[m.name] = None
        else:
            # Known metric: normalize into [0.0, 1.0]
            try:
                numeric_val = float(raw_val)
            except (ValueError, TypeError):
                numeric_val = 0.0

            span = m.max_value - m.min_value
            if span > 0:
                normalized = max(0.0, min(1.0, (numeric_val - m.min_value) / span))
            else:
                normalized = 1.0 if numeric_val >= m.max_value else 0.0

            accum_min += m.weight * normalized
            accum_max += m.weight * normalized
            known_weight += m.weight
            metric_scores[m.name] = normalized

    r_min = accum_min / total_weight if total_weight > 0 else 0.0
    r_max = accum_max / total_weight if total_weight > 0 else 1.0
    coverage = known_weight / total_weight if total_weight > 0 else 0.0

    # Ensure numerical bounds
    r_min = max(0.0, min(1.0, r_min))
    r_max = max(0.0, min(1.0, r_max))
    if r_min > r_max:
        r_min = r_max

    # 3. Determine status
    if not hard_gates_passed:
        status = EvaluationStatus.FAIL
    elif r_min >= template.tau:
        status = EvaluationStatus.PASS
    elif r_max < template.tau:
        status = EvaluationStatus.FAIL
    else:
        status = EvaluationStatus.UNKNOWN_WITHIN_BUDGET

    return EvaluationIntervalResult(
        template_id=template.template_id,
        template_version=template.version,
        template_hash=template.canonical_hash(),
        evidence_hash=compute_evidence_hash(evidence),
        r_min=r_min,
        r_max=r_max,
        coverage=coverage,
        tau=template.tau,
        hard_gates_passed=hard_gates_passed,
        status=status,
        hard_gate_failures=hard_gate_failures,
        metric_scores=metric_scores,
    )
