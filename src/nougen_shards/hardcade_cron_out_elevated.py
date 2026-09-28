"""
Hardcade Cron Out Elevated Module

Implements mathematical backoff jitter models, misfire probability estimations,
and reliability metrics for persistent cron execution schedules.

Mathematical Formulations:
1. Exponential Backoff with Full Jitter:
   delay(i) = random_uniform(0, min(T_max, T_base * 2^i))

2. Misfire Drift Probability Density:
   P_misfire(dt) = 1 - exp(-lambda_drift * dt)

3. Cadence Reliability Score:
   R_cadence = (N_success / N_total) * exp(- (sigma_jitter^2) / (2 * mu_interval^2))

4. Idempotency Deterministic Run Key:
   H_run = SHA256(schedule_id || tick_epoch || payload_digest)
"""

from dataclasses import dataclass, field
import hashlib
import math
import random
from typing import Dict, List, Optional, Tuple


@dataclass
class JitterBackoffCalculator:
    base_interval: float = 1.0
    max_interval: float = 60.0
    multiplier: float = 2.0
    jitter_type: str = "full"  # "full", "equal", "decorrelated"

    def compute_delay(self, attempt: int, seed: Optional[int] = None) -> float:
        """
        Computes backoff delay for retry attempt (0-indexed).
        Full jitter: random between 0 and min(max_interval, base * multiplier^attempt)
        Equal jitter: (cap / 2) + random between 0 and cap / 2
        """
        if seed is not None:
            rng = random.Random(seed + attempt)
        else:
            rng = random.Random()

        cap = min(self.max_interval, self.base_interval * (self.multiplier ** attempt))

        if self.jitter_type == "full":
            return rng.uniform(0.0, cap)
        elif self.jitter_type == "equal":
            half = cap / 2.0
            return half + rng.uniform(0.0, half)
        else:
            return rng.uniform(self.base_interval, cap)


@dataclass
class ReliabilityTracker:
    successes: int = 0
    failures: int = 0
    intervals: List[float] = field(default_factory=list)

    @property
    def total_runs(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        if self.total_runs == 0:
            return 1.0
        return self.successes / self.total_runs

    def compute_reliability_score(self, target_interval: float) -> float:
        """
        Calculates R_cadence = (N_success / N_total) * exp(- sigma_jitter^2 / (2 * mu_interval^2))
        """
        if self.total_runs == 0 or target_interval <= 0:
            return 1.0

        if not self.intervals or len(self.intervals) < 2:
            jitter_penalty = 1.0
        else:
            mean_int = sum(self.intervals) / len(self.intervals)
            variance = sum((x - mean_int) ** 2 for x in self.intervals) / (len(self.intervals) - 1)
            std_dev = math.sqrt(variance)
            jitter_penalty = math.exp(-(std_dev ** 2) / (2.0 * (target_interval ** 2)))

        return self.success_rate * jitter_penalty


class MisfireEstimator:
    """
    Estimates probability of execution misfire based on time drift.
    P_misfire(dt) = 1 - exp(-lambda_drift * dt)
    """

    def __init__(self, lambda_drift: float = 0.01):
        self.lambda_drift = max(1e-6, lambda_drift)

    def probability(self, dt: float) -> float:
        if dt <= 0:
            return 0.0
        prob = 1.0 - math.exp(-self.lambda_drift * dt)
        return max(0.0, min(1.0, prob))


def compute_idempotency_key(schedule_id: str, tick_epoch: int, payload: str) -> str:
    """
    Computes deterministic run key H_run = SHA256(schedule_id || tick_epoch || payload)
    """
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    raw = f"{schedule_id}:{tick_epoch}:{payload_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
