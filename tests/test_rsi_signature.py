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
