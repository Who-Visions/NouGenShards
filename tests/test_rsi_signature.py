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


# --- 4 Explicit Acceptance Falsification Tests (Leg 20261006T140129Z) ------------------------

def test_falsification_linear_gain_ci_contains_zero():
    """Synthetic linear-gain series yields CI(b) containing 0 (no false acceleration)."""
    # Linear gain progression: constant dC per epoch => constant eta => zero slope
    recs = _recs([0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45], step=10)
    verdict = classify_epochs(recs)
    assert verdict.verdict == "ACCUMULATION"
    ci_low, ci_high = verdict.eta_ci
    assert ci_low <= 0.0 <= ci_high


def test_falsification_convex_series_yields_positive_b():
    """Convex series yields b > 0 and 95% CI strictly positive."""
    # Convex gain progression: increasing dC per epoch => accelerating eta
    recs = _recs([0.10, 0.11, 0.13, 0.16, 0.20, 0.25, 0.31, 0.38], step=10)
    verdict = classify_epochs(recs)
    assert verdict.verdict == "ACCELERATION"
    ci_low, _ = verdict.eta_ci
    assert ci_low > 0.0


def test_falsification_rising_search_flat_heldout_rejected_as_goodhart():
    """Rising search-accuracy with flat held-out is rejected as Goodhart."""
    heldout = [0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25]
    search = [0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85]
    recs = _recs(heldout, search=search, step=10)
    verdict = classify_epochs(recs)
    assert verdict.verdict == "GOODHART"


def test_falsification_credit_ablation_sums_reproduce_injected_effects_within_10_percent():
    """Credit ablation sums reproduce injected effects within 10%."""
    injected_effects = {
        "prompt_optimizer": 0.040,
        "retrieval_filter": 0.035,
        "context_compressor": 0.025,
    }
    true_total_injected = sum(injected_effects.values())  # 0.100
    # Simulate leave-one-out ablations with small noise (< 5%)
    simulated_ablation_deltas = {
        "prompt_optimizer": 0.039,
        "retrieval_filter": 0.036,
        "context_compressor": 0.024,
    }
    table = credit_table(total_gain=true_total_injected, ablation_deltas=simulated_ablation_deltas)
    assert table["attributed"] is True
    explained_sum = table["explained"]
    relative_error = abs(explained_sum - true_total_injected) / true_total_injected
    assert relative_error <= 0.10  # within 10% reproduction



def test_nan_and_infinite_metric_guards():
    """Explicit NaN/Inf metric inputs must raise ValueError or fail cleanly, never producing bogus acceleration."""
    with pytest.raises(ValueError, match="must be a valid real number"):
        compute_eta(float("nan"), 10.0)
    with pytest.raises(ValueError, match="must be a valid real number"):
        compute_eta(10.0, float("nan"))
    with pytest.raises(ValueError, match="must be a valid real number"):
        compute_eta(float("inf"), 10.0)
    with pytest.raises(ValueError, match="must be a valid real number"):
        compute_eta(10.0, float("inf"))
