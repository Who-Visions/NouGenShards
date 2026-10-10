from __future__ import annotations

from nougen_shards.rsi_signature import (
    compute_eta,
    evaluate_rsi_signature,
)


def test_compute_eta():
    assert compute_eta(10.0, 2.0) == 5.0


def test_rsi_signature_accepts_accelerating_non_divergent_epochs():
    epochs = [1, 2, 3, 4, 5]
    # Steadily increasing capability per verified experience (accelerating)
    eta = [1.0, 1.8, 2.6, 3.5, 4.4]
    # Search vs OOD remain well aligned (no widening Goodhart gap)
    search = [0.60, 0.70, 0.78, 0.85, 0.90]
    ood = [0.58, 0.67, 0.75, 0.83, 0.88]

    res = evaluate_rsi_signature(epochs, eta, search, ood)
    assert res.is_rsi_confirmed is True
    assert res.eta_slope > 0.8
    assert res.ci_lower > 0.0
    assert res.transfer_gap_widening is False


def test_rsi_signature_rejects_goodhart_divergence():
    epochs = [1, 2, 3, 4, 5]
    eta = [1.0, 2.0, 3.0, 4.0, 5.0]
    # Search climbs while OOD stagnates (transfer gap explodes)
    search = [0.60, 0.75, 0.85, 0.95, 0.99]
    ood = [0.55, 0.54, 0.53, 0.52, 0.51]

    res = evaluate_rsi_signature(epochs, eta, search, ood)
    assert res.is_rsi_confirmed is False
    assert res.transfer_gap_widening is True
    assert "Goodhart" in res.reason


def test_rsi_signature_rejects_insufficient_epochs():
    epochs = [1, 2]
    eta = [1.0, 2.0]
    search = [0.6, 0.7]
    ood = [0.5, 0.6]

    res = evaluate_rsi_signature(epochs, eta, search, ood, min_epochs=4)
    assert res.is_rsi_confirmed is False
    assert "Insufficient epochs" in res.reason


# --- classify_epochs / credit_table -------------------------------------------------------
import pytest  # noqa: E402


@pytest.mark.parametrize("series_index", [0, 1, 2])
@pytest.mark.parametrize("length", [0, 1, 5, 7])
def test_rsi_signature_rejects_unaligned_evidence(series_index, length):
    epochs = list(range(6))
    evidence = [epochs.copy(), epochs.copy(), epochs.copy()]
    evidence[series_index] = list(range(length))
    with pytest.raises(ValueError, match="align with every epoch"):
        evaluate_rsi_signature(epochs, *evidence)


@pytest.mark.parametrize("series_index", [0, 1, 2, 3])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("position", [0, 3, 5])
def test_rsi_signature_rejects_nonfinite_evidence(series_index, value, position):
    series = [list(range(6)) for _ in range(4)]
    series[series_index][position] = value
    with pytest.raises(ValueError, match="must be finite"):
        evaluate_rsi_signature(*series)


@pytest.mark.parametrize("series_index", [0, 1, 2, 3])
@pytest.mark.parametrize("value", [1e308, -1e308])
def test_rsi_signature_rejects_overflowed_statistics(series_index, value):
    series = [list(range(6)) for _ in range(4)]
    series[series_index] = [value] * 6
    with pytest.raises(ValueError, match="derived RSI statistics must be finite"):
        evaluate_rsi_signature(*series)


from nougen_shards.rsi_signature import EpochRecord, classify_epochs, credit_table, epoch_series  # noqa: E402


def _recs(heldout, search=None, compute=None, step=10):
    search = search or [h + 0.05 for h in heldout]
    compute = compute or [1.0] * len(heldout)
    return [EpochRecord(f"e{i}", 10 + step * i, h, s, c)
            for i, (h, s, c) in enumerate(zip(heldout, search, compute))]


def test_classify_insufficient():
    assert classify_epochs(_recs([0.1, 0.2, 0.3])).verdict == "INSUFFICIENT_DATA"


def test_classify_linear_is_accumulation_not_acceleration():
    v = classify_epochs(_recs([0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]))
    assert v.verdict == "ACCUMULATION"


def test_classify_convex_is_acceleration():
    v = classify_epochs(_recs([0.10, 0.11, 0.13, 0.16, 0.20, 0.25, 0.31, 0.38]))
    assert v.verdict == "ACCELERATION"


def test_classify_goodhart():
    held = [0.20, 0.21, 0.20, 0.21, 0.20, 0.21, 0.20]
    srch = [0.25, 0.32, 0.40, 0.48, 0.56, 0.64, 0.72]
    assert classify_epochs(_recs(held, srch)).verdict == "GOODHART"


def test_classify_flat_is_no_gain():
    assert classify_epochs(_recs([0.3] * 8)).verdict == "NO_GAIN"


def test_compute_normalization_removes_bought_acceleration():
    held = [0.10, 0.11, 0.13, 0.16, 0.20, 0.25, 0.31, 0.38]
    compute = [1, 2, 4, 8, 16, 32, 64, 128]
    assert classify_epochs(_recs(held, compute=compute), compute_normalized=False).verdict == "ACCELERATION"
    assert classify_epochs(_recs(held, compute=compute)).verdict != "ACCELERATION"


def test_experience_must_increase():
    with pytest.raises(ValueError):
        epoch_series([EpochRecord("a", 10, 0.1, 0.1), EpochRecord("b", 10, 0.2, 0.2)])


def test_credit_table():
    t = credit_table(0.10, {"c1": 0.04, "c2": 0.03, "c3": -0.01})
    assert t["attributed"] and t["fraction"] == pytest.approx(0.7)
    assert not credit_table(0.10, {"c1": 0.02})["attributed"]
    assert not credit_table(0.0, {"c1": 0.1})["attributed"]


def test_default_min_epochs_is_six(monkeypatch):
    monkeypatch.delenv("NOUGEN_RSI_MIN_EPOCHS", raising=False)
    five_etas = _recs([0.10, 0.11, 0.13, 0.16, 0.20, 0.25])  # 5 eta points
    assert classify_epochs(five_etas).verdict == "INSUFFICIENT_DATA"
    monkeypatch.setenv("NOUGEN_RSI_MIN_EPOCHS", "4")
    assert classify_epochs(five_etas).verdict != "INSUFFICIENT_DATA"


# --- Comprehensive Falsification Suite ----------------------------------------------------
from nougen_shards.rsi_signature import bootstrap_slope_ci, linear_slope  # noqa: E402


def test_compute_eta_falsification_boundaries():
    with pytest.raises(ValueError, match="must be positive"):
        compute_eta(10.0, 0.0)
    with pytest.raises(ValueError, match="must be positive"):
        compute_eta(10.0, -2.0)
    # Negative and zero capability changes
    assert compute_eta(-4.0, 2.0) == -2.0
    assert compute_eta(0.0, 5.0) == 0.0


def test_linear_slope_and_bootstrap_falsification_invariants():
    # Degenerate inputs
    assert linear_slope([], []) == 0.0
    assert linear_slope([1.0], [2.0]) == 0.0
    assert linear_slope([1.0, 2.0], [3.0]) == 0.0
    # Zero variance in X
    assert linear_slope([2.0, 2.0, 2.0], [1.0, 2.0, 3.0]) == 0.0
    # Zero variance in Y
    assert linear_slope([1.0, 2.0, 3.0], [5.0, 5.0, 5.0]) == 0.0

    # Bootstrap CI on n < 3 returns identical slope for both bounds
    ci_low, ci_high = bootstrap_slope_ci([1.0, 2.0], [2.0, 4.0])
    assert ci_low == 2.0 and ci_high == 2.0

    # Invariant: CI lower <= CI upper and deterministic reproducibility
    ci1 = bootstrap_slope_ci([1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.1, 2.9, 4.2, 5.0])
    ci2 = bootstrap_slope_ci([1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.1, 2.9, 4.2, 5.0])
    assert ci1[0] <= ci1[1]
    assert ci1 == ci2


def test_rsi_signature_falsifies_decelerating_gains():
    epochs = [1, 2, 3, 4, 5]
    # Diminishing / decelerating efficiency per unit experience
    eta = [5.0, 4.0, 3.0, 2.0, 1.0]
    search = [0.60, 0.70, 0.75, 0.78, 0.80]
    ood = [0.58, 0.68, 0.73, 0.76, 0.78]

    res = evaluate_rsi_signature(epochs, eta, search, ood)
    assert res.is_rsi_confirmed is False
    assert res.eta_slope < 0.0
    assert res.ci_lower < 0.0
    assert "Eta slope lower bound not positive" in res.reason


def test_rsi_signature_falsifies_noisy_spurious_trend():
    epochs = [1, 2, 3, 4, 5, 6]
    # High variance oscillating eta whose 95% CI crosses zero
    eta = [1.0, 4.0, 1.1, 4.1, 1.0, 4.2]
    search = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75]
    ood = [0.49, 0.54, 0.59, 0.64, 0.69, 0.74]

    res = evaluate_rsi_signature(epochs, eta, search, ood)
    assert res.is_rsi_confirmed is False
    assert res.ci_lower <= 0.0
    assert "Eta slope lower bound not positive" in res.reason


def test_rsi_signature_falsifies_joint_divergence_and_deceleration():
    epochs = [1, 2, 3, 4, 5]
    eta = [5.0, 4.0, 3.0, 2.0, 1.0]
    search = [0.6, 0.75, 0.85, 0.95, 0.99]
    ood = [0.55, 0.54, 0.53, 0.52, 0.51]

    res = evaluate_rsi_signature(epochs, eta, search, ood)
    assert res.is_rsi_confirmed is False
    assert res.transfer_gap_widening is True
    assert "Eta slope lower bound not positive" in res.reason
    assert "Goodhart" in res.reason


def test_epoch_series_falsification_invariants():
    # Experience decreasing
    with pytest.raises(ValueError, match="strictly increase"):
        epoch_series([EpochRecord("e1", 20, 0.5, 0.5), EpochRecord("e2", 15, 0.6, 0.6)])

    # Compute non-positive
    with pytest.raises(ValueError, match="compute must be positive"):
        epoch_series([EpochRecord("e1", 10, 0.5, 0.5, 1.0), EpochRecord("e2", 20, 0.6, 0.6, 0.0)])
    with pytest.raises(ValueError, match="compute must be positive"):
        epoch_series([EpochRecord("e1", 10, 0.5, 0.5, 1.0), EpochRecord("e2", 20, 0.6, 0.6, -2.0)])

    # Capability regressions yield negative eta
    gains, eta, gaps = epoch_series([
        EpochRecord("e1", 10, 0.50, 0.55, 1.0),
        EpochRecord("e2", 20, 0.40, 0.55, 1.0),
    ])
    assert gains[0] == pytest.approx(-0.10)
    assert eta[0] == pytest.approx(-0.01)


def test_classify_epochs_goodhart_overrides_acceleration():
    # Accelerating heldout gains AND explosive Goodhart divergence
    held = [0.10, 0.11, 0.13, 0.16, 0.20, 0.25, 0.31, 0.38]
    srch = [0.20, 0.30, 0.45, 0.60, 0.75, 0.85, 0.95, 0.99]
    verdict = classify_epochs(_recs(held, srch))
    # Goodhart divergence must take strict precedence over Acceleration
    assert verdict.verdict == "GOODHART"


def test_classify_epochs_gap_floor_configuration(monkeypatch):
    held = [0.20, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26]
    srch = [0.25, 0.27, 0.29, 0.31, 0.33, 0.35, 0.37]
    # Default floor 0 detects slight divergence
    v_default = classify_epochs(_recs(held, srch))
    assert v_default.verdict == "GOODHART"

    # Higher gap floor allows tolerance
    monkeypatch.setenv("NOUGEN_RSI_GAP_SLOPE_MIN", "0.05")
    v_tolerant = classify_epochs(_recs(held, srch))
    assert v_tolerant.verdict != "GOODHART"


def test_classify_epochs_regression_is_no_gain():
    # Monotonically declining heldout performance
    held = [0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20]
    assert classify_epochs(_recs(held)).verdict == "NO_GAIN"


def test_credit_table_falsification_edge_cases():
    # Empty ablation dictionary
    t_empty = credit_table(0.10, {})
    assert not t_empty["attributed"]
    assert t_empty["explained"] == 0.0
    assert t_empty["fraction"] == 0.0

    # Negative ablation deltas are completely ignored
    t_neg = credit_table(0.10, {"bad1": -0.05, "bad2": -0.10})
    assert not t_neg["attributed"]
    assert t_neg["explained"] == 0.0

    # Negative total gain with positive ablations
    t_neg_gain = credit_table(-0.05, {"c1": 0.05})
    assert not t_neg_gain["attributed"]

    # Boundary threshold exact checks (min_fraction=0.5 default)
    t_below = credit_table(0.10, {"c1": 0.0499})
    assert not t_below["attributed"]
    assert t_below["fraction"] < 0.5

    t_at = credit_table(0.10, {"c1": 0.05})
    assert t_at["attributed"]
    assert t_at["fraction"] == pytest.approx(0.5)


def test_synthetic_linear_gain_series_ci_contains_zero_no_false_acceleration():
    """Acceptance criterion: synthetic linear-gain series yields CI(b) containing 0 (no false acceleration)."""
    # Linear gain series: held-out improves by a constant 0.05 per 10 experience units
    # This means eta is constant at 0.005. Slope b must be 0.0 and CI(b) must contain 0.
    records = [
        EpochRecord("e0", 10, 0.20, 0.25, 1.0),
        EpochRecord("e1", 20, 0.25, 0.30, 1.0),
        EpochRecord("e2", 30, 0.30, 0.35, 1.0),
        EpochRecord("e3", 40, 0.35, 0.40, 1.0),
        EpochRecord("e4", 50, 0.40, 0.45, 1.0),
        EpochRecord("e5", 60, 0.45, 0.50, 1.0),
        EpochRecord("e6", 70, 0.50, 0.55, 1.0),
    ]
    verdict = classify_epochs(records)
    # Verdict must be ACCUMULATION, not ACCELERATION
    assert verdict.verdict == "ACCUMULATION"
    # CI(b) must contain 0 (ci_lower <= 0 <= ci_upper)
    ci_low, ci_high = verdict.eta_ci
    assert ci_low <= 0.0 <= ci_high

    # Also check evaluate_rsi_signature on constant eta
    epochs = [1, 2, 3, 4, 5, 6]
    eta = [0.005] * 6
    search = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    ood = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45]
    sig = evaluate_rsi_signature(epochs, eta, search, ood)
    assert sig.is_rsi_confirmed is False
    assert sig.ci_lower <= 0.0 <= sig.ci_upper


def test_synthetic_convex_gain_series_yields_positive_slope():
    """Acceptance criterion: convex series yields b > 0 and confirmed acceleration."""
    # Convex accelerating gain series: delta capability per experience increases over epochs
    records = [
        EpochRecord("e0", 10, 0.10, 0.15, 1.0),
        EpochRecord("e1", 20, 0.11, 0.16, 1.0),  # gain = 0.01 -> eta = 0.001
        EpochRecord("e2", 30, 0.13, 0.18, 1.0),  # gain = 0.02 -> eta = 0.002
        EpochRecord("e3", 40, 0.16, 0.21, 1.0),  # gain = 0.03 -> eta = 0.003
        EpochRecord("e4", 50, 0.20, 0.25, 1.0),  # gain = 0.04 -> eta = 0.004
        EpochRecord("e5", 60, 0.25, 0.30, 1.0),  # gain = 0.05 -> eta = 0.005
        EpochRecord("e6", 70, 0.31, 0.36, 1.0),  # gain = 0.06 -> eta = 0.006
        EpochRecord("e7", 80, 0.38, 0.43, 1.0),  # gain = 0.07 -> eta = 0.007
    ]
    verdict = classify_epochs(records)
    assert verdict.verdict == "ACCELERATION"
    assert verdict.eta_ci[0] > 0.0


def test_rising_search_accuracy_with_flat_held_out_rejected_as_goodhart():
    """Acceptance criterion: rising search-accuracy with flat held-out is rejected as Goodhart."""
    records = [
        EpochRecord("e0", 10, 0.30, 0.35, 1.0),
        EpochRecord("e1", 20, 0.30, 0.45, 1.0),
        EpochRecord("e2", 30, 0.30, 0.55, 1.0),
        EpochRecord("e3", 40, 0.30, 0.65, 1.0),
        EpochRecord("e4", 50, 0.30, 0.75, 1.0),
        EpochRecord("e5", 60, 0.30, 0.85, 1.0),
        EpochRecord("e6", 70, 0.30, 0.95, 1.0),
    ]
    verdict = classify_epochs(records)
    assert verdict.verdict == "GOODHART"

    epochs = [1, 2, 3, 4, 5, 6, 7]
    eta = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
    search = [0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
    ood = [0.30] * 7
    sig = evaluate_rsi_signature(epochs, eta, search, ood)
    assert sig.is_rsi_confirmed is False
    assert sig.transfer_gap_widening is True
    assert "Goodhart" in sig.reason


def test_credit_ablation_sums_reproduce_injected_effects_within_ten_percent():
    """Acceptance criterion: credit ablation sums reproduce injected effects within 10%."""
    # Ground truth injected component gains
    injected_effects = {
        "ast_mutation_opt": 0.040,
        "memory_retrieval_v2": 0.035,
        "context_compression": 0.025,
    }
    total_gain = sum(injected_effects.values())  # 0.100

    # Measured leave-one-out ablations with small experimental noise (+- 5%)
    measured_ablations = {
        "ast_mutation_opt": 0.041,
        "memory_retrieval_v2": 0.034,
        "context_compression": 0.024,
    }

    result = credit_table(total_gain, measured_ablations)
    assert result["attributed"] is True
    # The explained sum (0.099) must reproduce injected total gain (0.100) within 10% tolerance
    relative_error = abs(result["explained"] - total_gain) / total_gain
    assert relative_error <= 0.10
    assert result["fraction"] == pytest.approx(0.99, rel=1e-2)


