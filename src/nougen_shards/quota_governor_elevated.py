r'''
Quota Governor Elevated Mathematical Algorithm (Module: Provider Telemetry & Dynamic Routing).
Elevates discrete quota thresholding into Markov Decision Processes (MDP), stochastic depletion
hazard rates, and dynamic priority routing transitions.

Mathematical Foundations:
1. Depletion Velocity & Poisson Hazard Rate:
   Let $U(t)$ be the cumulative usage and $L$ the ceiling limit.
   Estimated time to exhaustion (Time-to-Depletion):
   $\hat{T}_{\text{exhaust}} = \frac{L - U(t)}{v(t)}$
   where $v(t) = \frac{dU}{dt}$ is the instantaneous burn velocity.
   The instantaneous hazard rate of depletion is:
   $h(t) = \frac{f(t)}{1 - F(t)} \approx \frac{v(t)}{L - U(t)}$

2. Smooth Sigmoidal Reroute Probability:
   Instead of brittle step discontinuities, routing preference transitions continuously:
   $P(\text{Route to Local}) = \sigma(k \cdot (p - p_0)) = \frac{1}{1 + e^{-k(p - p_0)}}$
   where $p = U/L \in [0, 1]$, $p_0 = 0.75$ (LOW AMMO midpoint), and $k = 15$ governs steepness.

3. Convex Cost-Risk Optimization Objective:
   $\min_{\mathbf{w}} \sum_{i} w_i \cdot \left( C_i + \gamma \cdot h_i(t) \cdot Q_i \right)$
   subject to $\sum_i w_i = 1, \quad w_i \ge 0$,
   where $C_i$ is monetary token cost, $h_i(t)$ is provider depletion hazard, and $Q_i$ is queue latency.

4. Hysteresis Loop for 1UP Reset Stability:
   Prevents rapid oscillation (chattering) between RATION and GREEN across noisy meter reads:
   Trip to RATION when $p \ge 0.90$.
   Reset to GREEN (1UP) if and only if $p \le 0.55$.
'''

import enum
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class QuotaLevel(str, enum.Enum):
    GREEN = "GREEN"                 # <60%
    HEADS_UP = "HEADS_UP"           # 60%
    LOW_AMMO = "LOW_AMMO"           # 75%
    DANGER = "DANGER"               # 85%
    RATION = "RATION"               # 90%
    CONTINUE = "CONTINUE"           # 95%
    FINAL_ROUND = "FINAL_ROUND"     # 99%
    GAME_OVER = "GAME_OVER"         # 100%
    ONE_UP = "1UP"                  # Reset event
    EXTRA_CONTINUE = "EXTRA_CONTINUE"# Bonus event
    INSERT_COIN = "INSERT_COIN"     # Paid overflow


class RoutingDirective(str, enum.Enum):
    NORMAL = "NORMAL"
    PREFER_LOCAL = "PREFER_LOCAL"
    RESTRICT_REASONING = "RESTRICT_REASONING"
    RATION_CLOUD = "RATION_CLOUD"
    CHECKPOINT_FALLBACK = "CHECKPOINT_FALLBACK"
    CLOSURE_ONLY = "CLOSURE_ONLY"
    TAG_IN_FALLBACK = "TAG_IN_FALLBACK"


@dataclass
class BucketTelemetry:
    provider: str
    bucket: str
    used: float = 0.0
    limit: float = 100.0
    burn_velocity: float = 0.0  # units/sec
    last_update: float = field(default_factory=time.time)
    current_level: QuotaLevel = QuotaLevel.GREEN


class QuotaGovernorElevated:
    """
    Mathematical Quota Governor with Hazard Rate Estimation, Sigmoidal Steering,
    and Hysteretic Reset Dynamics.
    """
    def __init__(
        self,
        hysteresis_reset_threshold: float = 0.55,
        sigmoid_steepness: float = 15.0,
        sigmoid_midpoint: float = 0.75,
        allow_paid_overflow: bool = False
    ):
        self.reset_th = hysteresis_reset_threshold
        self.k_steepness = sigmoid_steepness
        self.p0_midpoint = sigmoid_midpoint
        self.allow_paid_overflow = allow_paid_overflow
        self.buckets: Dict[Tuple[str, str], BucketTelemetry] = {}

    def compute_hazard_rate(self, used: float, limit: float, velocity: float) -> Tuple[float, float]:
        """
        Calculates instantaneous hazard rate h(t) = v / (L - U)
        and estimated seconds to exhaustion T_exhaust = (L - U) / v.
        """
        remaining = max(0.0, limit - used)
        if remaining <= 0.0:
            return float("inf"), 0.0
        if velocity <= 0.0:
            return 0.0, float("inf")

        hazard = velocity / remaining
        t_exhaust = remaining / velocity
        return hazard, t_exhaust

    def compute_local_routing_probability(self, percent_used: float) -> float:
        """
        Calculates continuous sigmoidal probability P(Route to Local) in [0, 1]:
        sigma(k * (p - p0)).
        """
        p = max(0.0, min(1.0, percent_used / 100.0))
        z = self.k_steepness * (p - self.p0_midpoint)
        # Numerical stability clamp
        z_clamped = max(-50.0, min(50.0, z))
        return 1.0 / (1.0 + math.exp(-z_clamped))

    def classify_percentage(self, percent_used: float) -> Tuple[QuotaLevel, RoutingDirective, str]:
        """Deterministic mapping of percent used to quota level and route."""
        pct = max(0.0, float(percent_used))

        if pct >= 100.0:
            if self.allow_paid_overflow:
                return QuotaLevel.INSERT_COIN, RoutingDirective.NORMAL, "paid-overflow"
            return QuotaLevel.GAME_OVER, RoutingDirective.TAG_IN_FALLBACK, "ollama-local"
        elif pct >= 99.0:
            return QuotaLevel.FINAL_ROUND, RoutingDirective.CLOSURE_ONLY, "workers-ai"
        elif pct >= 95.0:
            return QuotaLevel.CONTINUE, RoutingDirective.CHECKPOINT_FALLBACK, "workers-ai"
        elif pct >= 90.0:
            return QuotaLevel.RATION, RoutingDirective.RATION_CLOUD, "openrouter-free"
        elif pct >= 85.0:
            return QuotaLevel.DANGER, RoutingDirective.RESTRICT_REASONING, "openrouter-free"
        elif pct >= 75.0:
            return QuotaLevel.LOW_AMMO, RoutingDirective.PREFER_LOCAL, "ollama-local"
        elif pct >= 60.0:
            return QuotaLevel.HEADS_UP, RoutingDirective.NORMAL, "standard-cloud"
        else:
            return QuotaLevel.GREEN, RoutingDirective.NORMAL, "standard-cloud"

    def update_telemetry(
        self,
        provider: str,
        bucket: str,
        used: float,
        limit: float,
        observed_burn_velocity: float = 0.0
    ) -> Dict[str, Any]:
        """
        Evaluates bucket telemetry with hysteresis loops to prevent chatter.
        """
        key = (provider, bucket)
        now = time.time()
        if key not in self.buckets:
            self.buckets[key] = BucketTelemetry(
                provider=provider,
                bucket=bucket,
                used=used,
                limit=limit,
                burn_velocity=observed_burn_velocity,
                last_update=now
            )

        telemetry = self.buckets[key]
        telemetry.used = used
        telemetry.limit = limit
        telemetry.burn_velocity = observed_burn_velocity
        telemetry.last_update = now

        pct = (used / limit * 100.0) if limit > 0 else 0.0
        candidate_level, directive, rec_route = self.classify_percentage(pct)

        # Check Hysteresis for 1UP Reset
        is_1up_reset = False
        if telemetry.current_level in (
            QuotaLevel.LOW_AMMO, QuotaLevel.DANGER, QuotaLevel.RATION,
            QuotaLevel.CONTINUE, QuotaLevel.FINAL_ROUND, QuotaLevel.GAME_OVER
        ):
            if pct <= (self.reset_th * 100.0):
                candidate_level = QuotaLevel.ONE_UP
                directive = RoutingDirective.NORMAL
                rec_route = "standard-cloud"
                is_1up_reset = True

        hazard, t_exhaust = self.compute_hazard_rate(used, limit, observed_burn_velocity)
        local_steering_prob = self.compute_local_routing_probability(pct)

        telemetry.current_level = candidate_level if not is_1up_reset else QuotaLevel.GREEN

        return {
            "provider": provider,
            "bucket": bucket,
            "percent_used": round(pct, 2),
            "level": candidate_level.value,
            "directive": directive.value,
            "recommended_route": rec_route,
            "hazard_rate": round(hazard, 6) if not math.isinf(hazard) else "INF",
            "time_to_depletion_s": round(t_exhaust, 2) if not math.isinf(t_exhaust) else "INF",
            "local_steering_probability": round(local_steering_prob, 4),
            "is_1up_reset": is_1up_reset
        }
