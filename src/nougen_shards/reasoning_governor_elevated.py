"""
Elevated Mathematical Reasoning Governor & Utility Tensor Subsystem.
Extends reasoning_governor.py with formal utility tensors, confidence intervals, and vectorized marginal evaluation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional

from .reasoning_governor import TrajectoryCheckpoint, ReasoningValueBucket, GovernorAction, TaskClass, ConsequenceClass


@dataclass
class CognitiveUtilityTensor:
    """Formal 4-component cognitive utility tensor U_cog = [Gain, Cost, Risk, Latency]."""
    quality_gain: float = 0.0
    token_cost: float = 0.0
    drift_risk: float = 0.0
    latency_penalty: float = 0.0

    @property
    def net_utility(self) -> float:
        return round(self.quality_gain - self.token_cost - self.drift_risk - self.latency_penalty, 4)


def compute_epistemic_confidence_interval(
    positive_observations: int,
    total_observations: int,
    confidence_level: float = 0.95
) -> Tuple[float, float, float]:
    """
    Computes Wilson Score Interval for epistemic confidence:
    Returns (center, lower_bound, upper_bound).
    """
    if total_observations <= 0:
        return 0.0, 0.0, 0.0

    z = 1.96 if confidence_level >= 0.95 else 1.645
    p_hat = positive_observations / total_observations

    denominator = 1.0 + (z**2 / total_observations)
    center_adjusted = (p_hat + (z**2 / (2.0 * total_observations))) / denominator
    margin = (z * math.sqrt((p_hat * (1.0 - p_hat) / total_observations) + (z**2 / (4.0 * total_observations**2)))) / denominator

    lower = max(0.0, center_adjusted - margin)
    upper = min(1.0, center_adjusted + margin)

    return round(center_adjusted, 4), round(lower, 4), round(upper, 4)


def evaluate_tensorized_marginal_value(
    checkpoint: TrajectoryCheckpoint,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 1.0,
    delta: float = 0.5
) -> Tuple[CognitiveUtilityTensor, ReasoningValueBucket, str]:
    """
    Computes U_cog tensor and returns (utility_tensor, value_bucket, reason_code).
    """
    if not checkpoint.is_knowable or checkpoint.evidence_state == "UNKNOWABLE":
        tensor = CognitiveUtilityTensor(quality_gain=0.0, token_cost=1.0, drift_risk=1.0, latency_penalty=0.5)
        return tensor, ReasoningValueBucket.NEGATIVE_WASTE, "unknowable_task_abstain"

    # 1. Quality Gain Component
    gain = 0.0
    if checkpoint.contradictions_count > 0:
        gain += 0.40 * min(3, checkpoint.contradictions_count)

    subgoal_gap = 1.0 - (checkpoint.subgoals_completed / max(1, checkpoint.subgoals_total))
    gain += 0.35 * max(0.0, subgoal_gap)

    if checkpoint.unresolved_constraints > 0:
        gain += 0.25 * min(4, checkpoint.unresolved_constraints)

    consequence_mult = 1.0 + (0.25 * int(checkpoint.consequence_class))
    gain *= consequence_mult

    if checkpoint.verification_state == "FAILED":
        gain += 0.45

    # 2. Token Cost Component
    cost = 0.0
    if checkpoint.reasoning_tokens_spent > 8000:
        cost = min(0.60, (checkpoint.reasoning_tokens_spent - 8000) / 10000.0)

    # 3. Drift Risk Component
    risk = 0.0
    if len(checkpoint.action_history) >= 4:
        recent = checkpoint.action_history[-4:]
        if len(set(recent)) <= 2:
            risk = 0.30

    if checkpoint.consecutive_zero_delta_steps >= 2:
        risk += 0.45

    # 4. Latency Penalty Component
    lat_pen = min(0.50, checkpoint.elapsed_seconds / 60.0) * delta

    tensor = CognitiveUtilityTensor(
        quality_gain=round(gain * alpha, 4),
        token_cost=round(cost * beta, 4),
        drift_risk=round(risk * gamma, 4),
        latency_penalty=round(lat_pen, 4)
    )

    net = tensor.net_utility
    if net >= 0.40:
        bucket = ReasoningValueBucket.HIGH_POSITIVE
        reason = "high_utility_cognition_licensed"
    elif net > 0.05:
        bucket = ReasoningValueBucket.LOW_POSITIVE
        reason = "modest_utility_cognition_licensed"
    elif net >= -0.15:
        bucket = ReasoningValueBucket.MARGINAL_ZERO
        reason = "utility_plateau_detected"
    else:
        bucket = ReasoningValueBucket.NEGATIVE_WASTE
        reason = "negative_utility_waste_halt"

    return tensor, bucket, reason
