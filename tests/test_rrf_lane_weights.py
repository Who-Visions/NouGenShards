"""Per-lane RRF weights and k come from env, with safe fallbacks."""
from nougen_shards import core


def test_defaults_are_uniform(monkeypatch):
    monkeypatch.delenv("NOUGEN_RRF_WEIGHTS", raising=False)
    monkeypatch.delenv("NOUGEN_RRF_K", raising=False)
    assert core._rrf_lane_weights() == {lane: 1.0 for lane in core.RRF_LANES}
    assert core._rrf_k() == 60


def test_override_parses_known_lanes(monkeypatch):
    monkeypatch.setenv("NOUGEN_RRF_WEIGHTS", " Vector=1.5 , title=2")
    w = core._rrf_lane_weights()
    assert w["vector"] == 1.5 and w["title"] == 2.0 and w["keyword"] == 1.0


def test_bad_entries_fall_back(monkeypatch):
    monkeypatch.setenv("NOUGEN_RRF_WEIGHTS", "bogus=3,vector=abc,title=-1,exact=nan,keyword")
    assert core._rrf_lane_weights() == {lane: 1.0 for lane in core.RRF_LANES}


def test_k_fallbacks(monkeypatch):
    monkeypatch.setenv("NOUGEN_RRF_K", "20")
    assert core._rrf_k() == 20
    for bad in ("0", "-5", "x"):
        monkeypatch.setenv("NOUGEN_RRF_K", bad)
        assert core._rrf_k() == 60


def test_weights_change_fusion_order():
    a = [{"id": 1, "_db_index": 1}, {"id": 2, "_db_index": 1}]
    b = [{"id": 2, "_db_index": 1}, {"id": 1, "_db_index": 1}]
    top_uniform = core.reciprocal_rank_fusion([a, b], k=60, weights=[1.0, 1.0])
    top_b = core.reciprocal_rank_fusion([a, b], k=60, weights=[1.0, 3.0])
    assert top_b[0]["id"] == 2
    assert {r["id"] for r in top_uniform} == {1, 2}
