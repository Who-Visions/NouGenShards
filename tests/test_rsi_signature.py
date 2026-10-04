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
    assert classify_epochs(_recs([0.3] * 6)).verdict == "NO_GAIN"


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
