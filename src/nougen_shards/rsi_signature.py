"""Falsifiable RSI Capability Signature Validator.

Implements the formal test:
eta_t = dCapability / dVerifiedExperience on leave-one-kind-out sealed splits.
RSI holds iff the bootstrap CI of the slope of eta_t > 0 AND the transfer gap
between search and out-of-distribution (OOD) sealed cases is not widening.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class RSISignatureResult:
    is_rsi_confirmed: bool
    eta_slope: float
    ci_lower: float
    ci_upper: float
    transfer_gap_widening: bool
    sample_size: int
    reason: str


def compute_eta(delta_capability: float, delta_experience: float) -> float:
    """Computes efficiency derivative eta = dC / dE."""
    if delta_experience <= 0:
        raise ValueError("delta_experience must be positive")
    return delta_capability / delta_experience


def linear_slope(x_series: Sequence[float], y_series: Sequence[float]) -> float:
    """Computes ordinary least squares slope."""
    n = len(x_series)
    if n != len(y_series) or n < 2:
        return 0.0
    mean_x = sum(x_series) / n
    mean_y = sum(y_series) / n
    denom = sum((x - mean_x) ** 2 for x in x_series)
    if denom == 0.0:
        return 0.0
    numer = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_series, y_series))
    return numer / denom


def bootstrap_slope_ci(
    x_series: Sequence[float],
    y_series: Sequence[float],
    n_resamples: int = 200,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """Computes bootstrap confidence interval for the regression slope."""
    n = len(x_series)
    if n < 3:
        slope = linear_slope(x_series, y_series)
        return slope, slope

    slopes: List[float] = []
    # Deterministic pseudo-random sequence for reproducible test verification
    seed = 42
    for i in range(n_resamples):
        resampled_x = []
        resampled_y = []
        for j in range(n):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            idx = seed % n
            resampled_x.append(x_series[idx])
            resampled_y.append(y_series[idx])
        slopes.append(linear_slope(resampled_x, resampled_y))

    slopes.sort()
    low_idx = int(math.floor((alpha / 2.0) * n_resamples))
    high_idx = int(math.ceil((1.0 - alpha / 2.0) * n_resamples)) - 1
    low_idx = max(0, min(low_idx, n_resamples - 1))
    high_idx = max(0, min(high_idx, n_resamples - 1))
    return slopes[low_idx], slopes[high_idx]


def evaluate_rsi_signature(
    epochs: Sequence[int],
    eta_history: Sequence[float],
    search_scores: Sequence[float],
    ood_scores: Sequence[float],
    min_epochs: int = 4,
) -> RSISignatureResult:
    """Verifies whether NouGen shows true recursive self-improvement."""
    n = len(epochs)
    if n < min_epochs:
        return RSISignatureResult(
            is_rsi_confirmed=False,
            eta_slope=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            transfer_gap_widening=False,
            sample_size=n,
            reason=f"Insufficient epochs: {n} < {min_epochs}",
        )

    # 1. Slope of eta
    x = [float(e) for e in epochs]
    slope = linear_slope(x, eta_history)
    ci_low, ci_high = bootstrap_slope_ci(x, eta_history)

    # 2. Transfer gap: gap = search_score - ood_score
    gaps = [s - o for s, o in zip(search_scores, ood_scores)]
    gap_slope = linear_slope(x, gaps)
    gap_widening = gap_slope > 0.05  # Divergence threshold

    # 3. Decision rule: slope > 0 with 95% CI > 0, and transfer gap not widening
    is_confirmed = (ci_low > 0.0) and not gap_widening

    reason = "RSI signature verified" if is_confirmed else ""
    if ci_low <= 0.0:
        reason += f"Eta slope lower bound not positive (CI=[{ci_low:.3f}, {ci_high:.3f}]); "
    if gap_widening:
        reason += f"Transfer gap widening into Goodhart regime (gap_slope={gap_slope:.3f}); "

    return RSISignatureResult(
        is_rsi_confirmed=is_confirmed,
        eta_slope=slope,
        ci_lower=ci_low,
        ci_upper=ci_high,
        transfer_gap_widening=gap_widening,
        sample_size=n,
        reason=reason.strip("; "),
    )
