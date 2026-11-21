"""Recall keeps a hit only with absolute evidence (constant-recall incident, 2026-11-20).

Relevance is min-max normalised inside each candidate set, so before this fix
the best of an all-noise set always scored 1.0 and every query, gibberish
included, returned the same newest dense shards. Now a hit needs an all-terms
lexical match, an exact title/token, or a vector cosine over the floor.
"""
import pytest

from nougen_shards import core

NOW = "2026-11-20T12:00:00+00:00"


def _row(i, title, sim=None, **extra):
    r = {"id": i, "_db_index": 1, "title": title, "content": title, "timestamp": NOW,
         "utility_score": 1.0, "density_score": 1.0}
    if sim is not None:
        r["_vec_sim"] = sim
    r.update(extra)
    return r


@pytest.fixture
def lanes(monkeypatch):
    state = {"kw": [], "vec": []}
    monkeypatch.setattr(core, "_keyword_retrieve", lambda *a, **k: [dict(r) for r in state["kw"]])
    monkeypatch.setattr(core, "_vector_retrieve", lambda *a, **k: [dict(r) for r in state["vec"]])
    monkeypatch.setattr(core, "_embed_query", lambda *a, **k: [0.1, 0.2])
    monkeypatch.setattr(core, "_title_lane_enabled", lambda: False)
    monkeypatch.setenv("NOUGEN_DISTILL_LANES", "0")  # hermetic: no real sidecar
    monkeypatch.delenv("NOUGEN_RECALL_MIN_SIM", raising=False)
    monkeypatch.delenv("NOUGEN_RECALL_MIN_SIM_ALONE", raising=False)
    return state


def _ids(query, **kw):
    return sorted(r["id"] for r in core.retrieve(query, limit=5, domain_key="*", **kw) or [])


def test_gibberish_with_only_weak_vector_neighbours_returns_nothing(lanes):
    lanes["vec"] = [_row(1, "newest dense shard", sim=0.59), _row(2, "other", sim=0.55)]
    assert _ids("zzqx vorpalqq fhtagnwub") == []


def test_or_retry_hit_keeps_itself_but_does_not_vouch_for_vector_noise(lanes):
    # A one-token OR hit really contains a query token, so it stays; it does not
    # lower the vector floor, so 0.60 noise (under the 0.65 alone floor) is cut.
    lanes["kw"] = [_row(3, "blob with vzzt inside", _or_retry=True)]
    lanes["vec"] = [_row(4, "noise", sim=0.60)]
    assert _ids("qqxv plorbnik vzzt kwarfle") == [3]


def test_all_terms_lexical_hit_survives_without_vector(lanes):
    lanes["kw"] = [_row(5, "relay_open graphql fallback")]
    assert _ids("relay_open graphql fallback") == [5]


def test_vector_only_hit_needs_base_floor_when_query_has_lexical_support(lanes):
    lanes["kw"] = [_row(6, "edge tunnel config")]
    lanes["vec"] = [_row(7, "related", sim=0.58), _row(8, "unrelated", sim=0.47)]
    assert _ids("edge tunnel config") == [6, 7]


def test_strong_vector_only_hit_survives_alone(lanes):
    lanes["vec"] = [_row(9, "paraphrase", sim=0.72), _row(10, "noise", sim=0.6)]
    assert _ids("a paraphrased question") == [9]


def test_unrelated_queries_do_not_share_the_same_noise_hits(lanes):
    lanes["vec"] = [_row(1, "newest dense shard", sim=0.5), _row(2, "other", sim=0.49)]
    first = _ids("Write flatten(x) for nested lists")
    second = _ids("Write roman_to_int(s)")
    assert first == second == []


def test_go_lane_rows_without_cosine_are_kept(lanes):
    lanes["vec"] = [_row(11, "go lane row", _vec_sim=None)]
    lanes["kw"] = [_row(12, "anchor")]
    assert 11 in _ids("anchor")


def test_floor_off_restores_legacy_top_hit(lanes, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_MIN_SIM", "off")
    lanes["vec"] = [_row(1, "newest dense shard", sim=0.2)]
    assert _ids("zzqx") == [1]


def test_bad_floor_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_MIN_SIM", "high")
    assert core._recall_min_sim() == core._RECALL_MIN_SIM_DEFAULT
