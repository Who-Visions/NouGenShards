"""Confidence is not authority. A value is auto-accepted only when the evidence
for it clears every bar -- top-1 confidence, margin over the runner-up, and
spread across the menu -- and never when the request is high-criticality."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Mapping, Tuple

from .types import DecisionValue, Escalation


@dataclass(frozen=True)
class DecisionPolicy:
    accept_confidence: float = 0.92
    min_margin: float = 0.20
    max_entropy: float = 0.35
    criticality_force_escalation: Tuple[str, ...] = ("high", "destructive")
    low_confidence_route: Escalation = Escalation.LLM
    high_criticality_route: Escalation = Escalation.HUMAN


def normalized_entropy(probabilities: Mapping[str, float]) -> float:
    ps = [max(float(p), 1e-12) for p in probabilities.values()]
    h = -sum(p * math.log(p) for p in ps)
    return h / math.log(max(len(ps), 2))


def margin(probabilities: Mapping[str, float]) -> float:
    ranked = sorted(probabilities.values(), reverse=True)
    if len(ranked) < 2:
        return 1.0
    return ranked[0] - ranked[1]


def can_auto_accept(value: DecisionValue, policy: DecisionPolicy) -> bool:
    if value.confidence < policy.accept_confidence:
        return False
    if value.probabilities:
        if margin(value.probabilities) < policy.min_margin:
            return False
        if normalized_entropy(value.probabilities) > policy.max_entropy:
            return False
    return True


MODES = ("off", "shadow", "enforce")


def mode() -> str:
    """NOUGEN_DECISION_PLANE: off | shadow | enforce. Anything unrecognised
    fails closed to ``off`` -- a typo must never switch enforcement on."""
    v = os.environ.get("NOUGEN_DECISION_PLANE", "off").strip().lower()
    return v if v in MODES else "off"
