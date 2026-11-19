"""Falsifiable RSI Capability Signature Validator.

Implements the formal test:
eta_t = dCapability / dVerifiedExperience on leave-one-kind-out sealed splits.
RSI holds iff the bootstrap CI of the slope of eta_t > 0 AND the transfer gap
between search and out-of-distribution (OOD) sealed cases is not widening.
"""

from __future__ import annotations

import math
import numbers
import operator
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


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
    if math.isnan(delta_capability) or math.isnan(delta_experience) or math.isinf(delta_capability) or math.isinf(delta_experience):
        raise ValueError("delta_capability and delta_experience must be a valid real number")
    if delta_experience <= 0:
        raise ValueError("delta_experience must be positive")
    return delta_capability / delta_experience


def _finite(value) -> bool:
    """True for a finite real. Ints pass without a float conversion (which overflows
    past ~1e308), matching the input check in evaluate_rsi_signature."""
    if isinstance(value, int) and not isinstance(value, bool):
        return True
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def _sum_sq_dev(values: Sequence[float]) -> float:
    """Sum of squared deviations from the mean, raising ValueError on overflow."""
    try:
        mean = sum(values) / len(values)
        total = sum((v - mean) * (v - mean) for v in values)
    except OverflowError:
        raise ValueError("derived RSI statistics must be finite") from None
    if not (_finite(mean) and _finite(total)):
        raise ValueError("derived RSI statistics must be finite")
    return total


def linear_slope(x_series: Sequence[float], y_series: Sequence[float]) -> float:
    """Computes ordinary least squares slope."""
    n = len(x_series)
    if n != len(y_series) or n < 2:
        return 0.0
    if not all(_finite(x) and _finite(y) for x, y in zip(x_series, y_series)):
        raise ValueError("x_series and y_series elements must be finite")
    # Finite inputs can still overflow here: `**` and huge-int division raise
    # OverflowError, while `*`, `/` and sum() silently return inf. Catch both.
    try:
        mean_x = sum(x_series) / n
        mean_y = sum(y_series) / n
        denom = sum((x - mean_x) * (x - mean_x) for x in x_series)
        numer = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_series, y_series))
    except OverflowError:
        raise ValueError("derived RSI statistics must be finite") from None
    if not all(_finite(v) for v in (mean_x, mean_y, denom, numer)):
        raise ValueError("derived RSI statistics must be finite")
    if denom == 0.0:
        return 0.0
    slope = numer / denom
    if not _finite(slope):
        raise ValueError("derived RSI statistics must be finite")
    return slope


def bootstrap_slope_ci(
    x_series: Sequence[float],
    y_series: Sequence[float],
    n_resamples: int = 200,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """Computes bootstrap confidence interval for the regression slope with degeneracy protection."""
    if len(x_series) != len(y_series):
        raise ValueError("x_series and y_series must have the same length")
    try:
        if isinstance(n_resamples, bool) or (
            not isinstance(n_resamples, numbers.Integral)
            and not hasattr(n_resamples, "__index__")
        ):
            raise TypeError
        n_resamples_val = operator.index(n_resamples)
        if n_resamples_val <= 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("n_resamples must be a positive integer")
    n_resamples = n_resamples_val
    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be finite and strictly between 0 and 1")

    n = len(x_series)
    if n < 3:
        slope = linear_slope(x_series, y_series)
        return slope, slope

    if not all(_finite(v) for v in (*x_series, *y_series)):
        raise ValueError("x_series and y_series elements must be finite")
    # Check if original x_series has zero variance
    if _sum_sq_dev(x_series) == 0.0:
        return 0.0, 0.0

    slopes: List[float] = []
    # A local RNG preserves reproducibility without modulo low-bit cycles.
    rng = random.Random(42)
    max_attempts = n_resamples * 5
    attempts = 0

    while len(slopes) < n_resamples and attempts < max_attempts:
        attempts += 1
        resampled_x = []
        resampled_y = []
        for _ in range(n):
            idx = rng.randrange(n)
            resampled_x.append(x_series[idx])
            resampled_y.append(y_series[idx])

        # Reject degenerate resample where all x are identical to prevent zero-variance attenuation bias
        if _sum_sq_dev(resampled_x) == 0.0:
            continue

        slopes.append(linear_slope(resampled_x, resampled_y))

    # Fallback if too many resamples were rejected
    if not slopes:
        base_slope = linear_slope(x_series, y_series)
        return base_slope, base_slope

    slopes.sort()
    m = len(slopes)
    low_idx = int(math.floor((alpha / 2.0) * m))
    high_idx = int(math.ceil((1.0 - alpha / 2.0) * m)) - 1
    low_idx = max(0, min(low_idx, m - 1))
    high_idx = max(0, min(high_idx, m - 1))
    ci_low, ci_high = slopes[low_idx], slopes[high_idx]
    if not (_finite(ci_low) and _finite(ci_high)):
        raise ValueError("derived RSI statistics must be finite")
    return ci_low, ci_high


def evaluate_rsi_signature(
    epochs: Sequence[int],
    eta_history: Sequence[float],
    search_scores: Sequence[float],
    ood_scores: Sequence[float],
    min_epochs: int = 4,
) -> RSISignatureResult:
    """Verifies whether NouGen shows true recursive self-improvement."""
    n = len(epochs)
    if any(len(series) != n for series in (eta_history, search_scores, ood_scores)):
        raise ValueError("eta, search, and OOD evidence must align with every epoch")
    for series in (epochs, eta_history, search_scores, ood_scores):
        for value in series:
            if isinstance(value, int) and not isinstance(value, bool):
                continue
            try:
                if not math.isfinite(value):
                    raise ValueError("epochs, eta, search, and OOD evidence must be finite")
            except (OverflowError, TypeError):
                raise ValueError("epochs, eta, search, and OOD evidence must be finite")
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
    if not all(_finite(g) for g in gaps):
        raise ValueError("derived RSI statistics must be finite")
    gap_slope = linear_slope(x, gaps)
    if not all(math.isfinite(value) for value in (slope, ci_low, ci_high, gap_slope)):
        raise ValueError("derived RSI statistics must be finite")
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


# --- Verdicts on raw epoch records (leg 20261004T184219Z) -----------------------------------
# evaluate_rsi_signature above takes a precomputed eta series and a fixed 0.05 gap threshold.
# classify_epochs derives eta from the raw evaluator records, optionally normalizes by compute,
# uses a bootstrap CI for the gap slope too, and separates accumulation from acceleration.

GAP_CI_ENV = "NOUGEN_RSI_GAP_SLOPE_MIN"  # optional extra floor on the gap slope's CI lower bound


@dataclass(frozen=True)
class EpochRecord:
    epoch: str
    experience: int      # verified fitness-corpus cases (#706)
    heldout: float       # sealed leave-one-kind-out pass rate
    search: float        # lane-visible pass rate
    compute: float = 1.0  # ledger-receipted compute (#705), any positive unit


@dataclass
class EpochVerdict:
    verdict: str  # INSUFFICIENT_DATA | GOODHART | ACCELERATION | ACCUMULATION | NO_GAIN
    eta: List[float]
    eta_ci: Tuple[float, float]
    gap_ci: Tuple[float, float]
    mean_gain: float


def epoch_series(records: Sequence[EpochRecord], compute_normalized: bool = True) -> Tuple[List[float], List[float], List[float]]:
    """(gains, eta, gaps). eta_t = gain / new experience [/ compute]; experience must strictly increase."""
    for r in records:
        if not all(_finite(v) for v in (r.experience, r.heldout, r.search, r.compute)):
            raise ValueError(f"all epoch metrics must be finite ({r.epoch})")
    gains, eta = [], []
    for prev, cur in zip(records, records[1:]):
        d_exp = cur.experience - prev.experience
        if d_exp <= 0:
            raise ValueError(f"experience must strictly increase ({prev.epoch} -> {cur.epoch})")
        if cur.compute <= 0:
            raise ValueError(f"compute must be positive ({cur.epoch})")
        g = cur.heldout - prev.heldout
        try:
            e = g / d_exp / (cur.compute if compute_normalized else 1.0)
        except OverflowError:
            raise ValueError(f"derived RSI statistics must be finite ({cur.epoch})") from None
        # Finite inputs can still overflow: a tiny positive compute (5e-324) sends eta to inf.
        if not (_finite(g) and _finite(e)):
            raise ValueError(f"derived RSI statistics must be finite ({cur.epoch})")
        gains.append(g)
        eta.append(e)
    gaps = [r.search - r.heldout for r in records]
    if not all(_finite(g) for g in gaps):
        raise ValueError("derived RSI statistics must be finite")
    return gains, eta, gaps


# A perfectly monotone trend over n epochs has best-case exact one-sided p = 1/n! (Kendall):
# n=4 -> 0.042 (cannot clear alpha 0.01), n=6 -> 0.0014. Phoebus, leg 20261004T192204Z.
MIN_EPOCHS_ENV = "NOUGEN_RSI_MIN_EPOCHS"
DEFAULT_MIN_EPOCHS = 6


def classify_epochs(records: Sequence[EpochRecord], *, min_epochs: Optional[int] = None,
                    compute_normalized: bool = True) -> EpochVerdict:
    import os

    if min_epochs is None:
        min_epochs = int(os.environ.get(MIN_EPOCHS_ENV, DEFAULT_MIN_EPOCHS))

    gains, eta, gaps = epoch_series(list(records), compute_normalized)
    mean_gain = sum(gains) / len(gains) if gains else 0.0
    if len(eta) < min_epochs:
        return EpochVerdict("INSUFFICIENT_DATA", eta, (0.0, 0.0), (0.0, 0.0), mean_gain)
    eta_ci = bootstrap_slope_ci(list(range(len(eta))), eta)
    gap_ci = bootstrap_slope_ci(list(range(len(gaps))), gaps)
    if not all(_finite(v) for v in (*eta_ci, *gap_ci, mean_gain)):
        raise ValueError("derived RSI statistics must be finite")
    gap_floor = float(os.environ.get(GAP_CI_ENV, "0"))
    if not _finite(gap_floor):
        raise ValueError("gap floor must be finite")
    if gap_ci[0] > gap_floor:
        verdict = "GOODHART"
    elif eta_ci[0] > 0:
        verdict = "ACCELERATION"
    elif mean_gain > 0:
        verdict = "ACCUMULATION"
    else:
        verdict = "NO_GAIN"
    return EpochVerdict(verdict, eta, eta_ci, gap_ci, mean_gain)


def credit_table(total_gain: float, ablation_deltas: Dict[str, float], min_fraction: float = 0.5) -> Dict[str, object]:
    """Causal credit: delta_i = C(all) - C(all minus change i) on sealed cases.

    The gain counts as attributed only if positively credited changes explain >= min_fraction of it.
    """
    if not _finite(total_gain):
        raise ValueError("total_gain must be a finite real number")
    if not _finite(min_fraction) or min_fraction < 0:
        raise ValueError("min_fraction must be a non-negative finite real number")
    for k, v in ablation_deltas.items():
        if not _finite(v):
            raise ValueError(f"ablation delta for {k} must be a finite real number")
    credited = {k: v for k, v in ablation_deltas.items() if v > 0}
    explained = sum(credited.values())
    if not _finite(explained):
        raise ValueError("derived RSI statistics must be finite")
    frac = explained / total_gain if total_gain > 0 else 0.0
    if not _finite(frac):
        raise ValueError("derived RSI statistics must be finite")
    return {"credited": credited, "explained": explained, "fraction": frac,
            "attributed": total_gain > 0 and frac >= min_fraction}
