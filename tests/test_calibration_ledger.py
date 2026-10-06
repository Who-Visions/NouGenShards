import pytest

from nougen_shards.calibration_ledger import CalibrationLedger, ForecastLocked, effective_lanes, weighted_consensus


@pytest.fixture
def ledger(tmp_path):
    return CalibrationLedger(tmp_path / "cal.db")


def test_forecast_is_write_once_and_validated(ledger):
    ledger.forecast("a", "c1", 0.7)
    with pytest.raises(ForecastLocked):
        ledger.forecast("a", "c1", 0.9)
    with pytest.raises(ValueError):
        ledger.forecast("a", "c2", 1.5)
    with pytest.raises(ValueError):
        ledger.forecast("", "c2", 0.5)


def test_resolve_needs_prior_forecast_and_resolves_once(ledger):
    ledger.forecast("a", "c1", 0.8)
    assert ledger.resolve("c1", {"a": True, "b": False}) == 1
    assert ledger.resolve("c1", {"a": False}) == 0
    cal = ledger.calibration()
    assert set(cal) == {"a"}
    assert cal["a"].brier == pytest.approx(0.04)


def test_calibration_by_family(ledger):
    ledger.forecast("a", "c1", 1.0, family="code")
    ledger.forecast("a", "c2", 1.0, family="temporal")
    ledger.resolve("c1", {"a": True})
    ledger.resolve("c2", {"a": False})
    assert ledger.calibration(family="code")["a"].brier == 0.0
    assert ledger.calibration(family="temporal")["a"].brier == 1.0


def _fill(ledger, harness, lane, p, outcomes):
    for i, ok in enumerate(outcomes):
        ledger.forecast(lane, f"{harness}-{i}", p, harness=harness)
        ledger.resolve(f"{harness}-{i}", {lane: ok}, harness=harness)


def test_promotion_refuses_calibration_regression(ledger):
    _fill(ledger, "base", "a", 0.5, [True, False] * 15)
    _fill(ledger, "good", "a", 0.5, [True, False] * 15)
    _fill(ledger, "bad", "a", 0.9, [True, False] * 15)
    ok, _ = ledger.promotion_ok("base", "good")
    assert ok
    ok, deltas = ledger.promotion_ok("base", "bad")
    assert not ok and deltas["a"] > 0.02


def test_promotion_fails_closed_without_evidence(ledger):
    _fill(ledger, "base", "a", 0.5, [True] * 5)
    _fill(ledger, "cand", "a", 0.5, [True] * 5)
    assert ledger.promotion_ok("base", "cand") == (False, {})


def test_correlated_lanes_lose_weight(ledger):
    # a and b fail together; c fails on different cases.
    for i in range(20):
        a_ok = b_ok = i % 4 != 0
        c_ok = i % 4 != 1
        for lane in "abc":
            ledger.forecast(lane, f"k{i}", 0.75)
        ledger.resolve(f"k{i}", {"a": a_ok, "b": b_ok, "c": c_ok})
    w = ledger.weights()
    assert w["c"] > w["a"]
    assert w["a"] == pytest.approx(w["b"])


def test_weighted_consensus():
    assert weighted_consensus({"a": 0.6}, {}) == 0.0
    one = weighted_consensus({"a": 0.6}, {"a": 1.0})
    assert one == pytest.approx(0.6)
    # Two half-weight correlated votes equal one full independent vote.
    assert weighted_consensus({"a": 0.6, "b": 0.6}, {"a": 0.5, "b": 0.5}) == pytest.approx(one)
    assert weighted_consensus({"a": 1.0}, {"a": 0.1}) == 1.0


def test_effective_lanes_collapses_identical_lanes(ledger):
    for i in range(20):
        ok = i % 3 != 0
        for lane in "abc":
            ledger.forecast(lane, f"n{i}", 0.6)
        ledger.resolve(f"n{i}", {"a": ok, "b": ok, "c": ok})
    n_eff, rho = effective_lanes(ledger)
    assert rho == pytest.approx(1.0)
    assert n_eff == pytest.approx(1.0)


def test_effective_lanes_independent_lanes_count_fully(ledger):
    # a and b disagree half the time with balanced outcomes -> phi = 0.
    pattern = [(1, 1), (1, 0), (0, 1), (0, 0)] * 5
    for i, (x, y) in enumerate(pattern):
        for lane in "ab":
            ledger.forecast(lane, f"m{i}", 0.5)
        ledger.resolve(f"m{i}", {"a": bool(x), "b": bool(y)})
    n_eff, rho = effective_lanes(ledger)
    assert rho == pytest.approx(0.0)
    assert n_eff == pytest.approx(2.0)


def test_effective_lanes_empty(ledger):
    assert effective_lanes(ledger) == (0.0, 0.0)
