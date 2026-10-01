"""Control-plane math: Pareto routing, Adherence, replay determinism, harness ledger."""
import random

import pytest

from nougen_shards import control_plane_math as C
from nougen_shards.decision.calibration import EvalReport

OBJ = {"quality": "max", "cost": "min", "latency": "min"}


def cand(i, q, c, lat):
    return {"id": i, "quality": q, "cost": c, "latency": lat}


def report(n=500, cost=0.10, ece=0.05):
    return EvalReport(n=n, accuracy=0.9, precision={}, recall={}, f1={}, confusion={},
                      weighted_false_negative_cost=cost, brier_score=0.1,
                      expected_calibration_error=ece, uncalibrated_rate=0.0, abstain_rate=0.0,
                      escalation_rate=0.0, stability_rate=1.0, p50_latency_ms=10.0,
                      p95_latency_ms=20.0, cost_per_1000=1.0)


GATE_OK = dict(fallback_tested=True, replay_stable=True)


def test_dominance_respects_each_objectives_direction():
    a, b = cand("a", 0.9, 1.0, 100), cand("b", 0.8, 2.0, 200)
    assert C.dominates(a, b, OBJ) and not C.dominates(b, a, OBJ)
    assert not C.dominates(a, a, OBJ)                      # equal never dominates
    with pytest.raises(ValueError):
        C.dominates(a, b, {"quality": "up"})


def test_front_keeps_tradeoffs_and_drops_the_dominated():
    cheap, best, bad = cand("cheap", 0.6, 0.1, 50), cand("best", 0.95, 5.0, 300), cand("bad", 0.5, 6.0, 400)
    assert [c["id"] for c in C.pareto_front([cheap, best, bad], OBJ)] == ["cheap", "best"]


def test_front_property_holds_on_random_candidates():
    rng = random.Random(7)
    cs = [cand(str(i), rng.random(), rng.random(), rng.random()) for i in range(60)]
    front = C.pareto_front(cs, OBJ)
    ids = {c["id"] for c in front}
    for c in cs:
        dominated = any(C.dominates(o, c, OBJ) for o in cs)
        assert (c["id"] in ids) == (not dominated)


def test_route_follows_weights_and_records_provenance():
    cheap, best = cand("cheap", 0.6, 0.1, 50), cand("best", 0.95, 5.0, 300)
    cs = [cheap, best, cand("bad", 0.5, 6.0, 400)]
    quality = C.route(cs, OBJ, {"quality": 1.0}, "pol-1")
    thrift = C.route(cs, OBJ, {"cost": 1.0, "latency": 1.0}, "pol-1")
    assert quality["chosen"] == "best" and thrift["chosen"] == "cheap"
    p = quality["provenance"]
    assert p["policy_version"] == "pol-1" and p["objectives"] == OBJ and len(p["inputs_digest"]) == 64
    assert quality["front"] == ["cheap", "best"]


def test_route_is_deterministic_and_ties_break_on_id():
    twins = [cand("b", 0.7, 1.0, 10), cand("a", 0.7, 1.0, 10)]
    forward = C.route(twins, OBJ, {"quality": 1.0}, "p")["chosen"]
    backward = C.route(list(reversed(twins)), OBJ, {"quality": 1.0}, "p")["chosen"]
    assert forward == backward == "a"                      # input order must not change the choice
    with pytest.raises(ValueError):
        C.route([], OBJ, {}, "p")


def test_adherence_reports_coverage_and_undeclared_separately():
    declared = [("plan", "build"), ("build", "test"), ("test", "ship")]
    observed = [("plan", "build"), ("build", "test"), ("build", "deploy")]
    a = C.adherence(declared, observed)
    assert a["coverage"] == pytest.approx(2 / 3) and a["undeclared"] == pytest.approx(1 / 3)
    assert a["missing_edges"] == [("test", "ship")] and a["undeclared_edges"] == [("build", "deploy")]
    empty = C.adherence([], [])
    assert empty["coverage"] is None and empty["undeclared"] is None     # unmeasured, not 0


def _decide(event, policy):
    return C.route(event["candidates"], OBJ, event["weights"], policy)


LOG = [{"candidates": [cand("x", 0.6, 0.1, 50), cand("y", 0.95, 5.0, 300)], "weights": {"quality": 1.0}},
       {"candidates": [cand("x", 0.6, 0.1, 50), cand("y", 0.95, 5.0, 300)], "weights": {"cost": 1.0}}]


def test_replay_same_log_and_policy_gives_identical_decisions_and_digest():
    r1, r2 = C.replay(LOG, "pol-1", _decide), C.replay(LOG, "pol-1", _decide)
    assert r1 == r2 and [d["chosen"] for d in r1["decisions"]] == ["y", "x"]
    assert [d["provenance"]["event_index"] for d in r1["decisions"]] == [0, 1]
    assert C.replay(LOG, "pol-2", _decide)["digest"] != r1["digest"]       # policy version is part of identity
    assert C.replay(LOG[::-1], "pol-1", _decide)["digest"] != r1["digest"]  # order is part of identity


def test_candidate_harness_cannot_promote_without_passing_the_gate():
    ledger = C.HarnessLedger()
    ledger.propose("h1"); ledger.propose("h2", parent="h1")
    regress = ledger.promote("h2", report(cost=0.30), report(cost=0.10), **GATE_OK)
    assert regress["promoted"] is False and any("regressed" in f for f in regress["failed_gates"])
    assert ledger.live is None
    assert ledger.negative_evidence[0]["harness"] == "h2" and ledger.negative_evidence[0]["parent"] == "h1"
    untested = ledger.promote("h2", report(), report())                    # fallback/replay not tested
    assert untested["promoted"] is False and len(untested["failed_gates"]) == 2


def test_passing_harness_promotes_and_rollback_restores_the_previous_one():
    ledger = C.HarnessLedger()
    ledger.propose("h1"); ledger.propose("h2", parent="h1")
    assert ledger.promote("h1", report(), report(cost=0.20), **GATE_OK)["promoted"]
    assert ledger.promote("h2", report(cost=0.05), report(), **GATE_OK)["promoted"]
    assert ledger.live == "h2" and ledger.rollback() == "h1" and ledger.rollback() is None
    assert ledger.negative_evidence == []


def test_ledger_rejects_unknown_and_duplicate_harnesses():
    ledger = C.HarnessLedger()
    with pytest.raises(KeyError):
        ledger.promote("ghost", report(), report(), **GATE_OK)
    ledger.propose("h1")
    with pytest.raises(ValueError):
        ledger.propose("h1")
