"""Regression coverage for the 2026-09-14 fault: a self-model seed authored
with "summary" instead of "statement", and "contradicts" holding shard
reference strings instead of match patterns, made every candidate score
UNKNOWN (recall_records degraded silently) and made the rare finding that DID
fire raise KeyError inside the request handler (rec["statement"]).

All fixture data is synthetic and invented for this test; it names no real
person, character, or story.
"""
from __future__ import annotations


from nougen_shards import canon_pressure as cp


def _model(records=None, fixed_points=None):
    return {
        "version": "1.0.0",
        "records": records or [],
        "fixed_points": fixed_points or [],
        "temporal_self": [],
        "themes": [],
        "branches": ["U0"],
        "conflict_groups": [],
    }


def test_statement_falls_back_to_summary():
    rec = {"id": "r1", "summary": "The tower was built in year one hundred."}
    assert cp._statement(rec) == "The tower was built in year one hundred."


def test_statement_prefers_statement_over_summary():
    rec = {"id": "r1", "statement": "S", "summary": "M"}
    assert cp._statement(rec) == "S"


def test_statement_missing_both_is_blank_not_a_crash():
    assert cp._statement({"id": "r1"}) == ""


def test_summary_only_record_does_not_crash_and_produces_a_finding():
    """The exact shape of the 2026-09-14 production seed: "summary" instead
    of "statement", "contradicts" present and phrased as a match pattern."""
    model = _model(records=[{
        "id": "tower_built_year_100",
        "status": "locked",
        "authority": "gm_lock",
        "topics": ["tower", "founding"],
        "summary": "Character A's tower was founded in year one hundred.",
        "contradicts": [r"tower (was|is) founded in year two hundred"],
        "provenance": ["shard:1@db1"],
    }])
    out = cp.pressure(
        "In this scene the tower is founded in year two hundred",
        register=False, model=model,
    )
    assert out["verdict"] == "FACT_CONFLICT"
    f = out["findings"][0]
    assert f["because"] == "Character A's tower was founded in year one hundred."
    assert f["record"] == "tower_built_year_100"


def test_contradicts_as_shard_id_never_matches_stays_unknown():
    """Documents the failure mode directly: when contradicts holds a shard
    id instead of a pattern that could appear in prose, the record can never
    fire, no matter how squarely the candidate contradicts it."""
    model = _model(records=[{
        "id": "tower_built_year_100",
        "status": "locked",
        "authority": "gm_lock",
        "topics": ["tower", "founding"],
        "summary": "Character A's tower was founded in year one hundred.",
        "contradicts": ["shard:1@db1"],
        "provenance": ["shard:1@db1"],
    }])
    out = cp.pressure(
        "In this scene the tower is founded in year two hundred",
        register=False, model=model,
    )
    assert out["verdict"] == "UNKNOWN"


def test_negative_control_claim_contradicting_a_lock_is_not_unknown():
    """The 2026-09-14 incident control: a claim built to contradict a locked
    fact must score as a conflict, not UNKNOWN. If this ever regresses to
    UNKNOWN again, the engine has stopped reading its own canon."""
    model = _model(records=[{
        "id": "founder_alive",
        "status": "locked",
        "authority": "gm_lock",
        "topics": ["founder", "fate"],
        "summary": "The founder is alive at the end of the story.",
        "contradicts": [r"founder (dies|is dead|is killed)"],
        "provenance": ["shard:2@db1"],
    }])
    out = cp.pressure("The founder dies in the final act", register=False, model=model)
    assert out["verdict"] != "UNKNOWN"
    assert out["confidence"] > 0.35


def test_fixed_point_with_summary_only_does_not_crash():
    model = _model(fixed_points=[{
        "id": "eclipse_fixed",
        "summary": "The eclipse happens on the appointed day no matter what.",
        "breaks_if": [r"eclipse (never happens|is cancelled)"],
        "dependents": ["harvest_festival"],
        "provenance": ["shard:3@db1"],
    }])
    out = cp.pressure("The eclipse never happens this year", register=False, model=model)
    assert out["verdict"] == "CAUSAL_DESTINY_CONFLICT"
    assert out["findings"][0]["because"].startswith("The eclipse happens")


def test_fixed_point_missing_provenance_does_not_crash():
    """Production data shape found 2026-09-14: fixed_points shared an id with
    a record but had no "provenance" key of their own (fp["provenance"]
    KeyError'd inside a live request)."""
    model = _model(fixed_points=[{
        "id": "eclipse_fixed",
        "summary": "The eclipse happens on the appointed day no matter what.",
        "breaks_if": [r"eclipse (never happens|is cancelled)"],
    }])
    out = cp.pressure("The eclipse never happens this year", register=False, model=model)
    assert out["verdict"] == "CAUSAL_DESTINY_CONFLICT"
    assert out["findings"][0]["evidence"] == []


def test_short_candidate_is_rejected():
    assert "error" in cp.pressure("hi", register=False, model=_model())
