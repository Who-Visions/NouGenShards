"""Xoah Toolbelt first slice. SYNTHETIC canon only -- this repo is public.

The fixture is a neutral stand-in (a courier "Ari", a lantern, a bridge), not
Xoah lore. It mirrors the SHAPE of the done-when: a Vol 1 chase scene must
(1) show only knowledge she has, (2) stay inside the volume's level lock,
(3) draw no conflict from an irrelevant lock, (4) receipt every canon source.
"""
from nougen_shards.xoah_toolbelt.packet import from_dict
from nougen_shards.xoah_toolbelt.power import power_ceiling
from nougen_shards.xoah_toolbelt.pressure import scene_pressure_test
from nougen_shards.xoah_toolbelt.scene_receipt import scene_receipt
from nougen_shards.xoah_toolbelt.timeline import timeline_trace

import pytest


def P(phrase, sid):
    return [{"shard_id": sid, "db": "db9", "node": "fixture", "phrase": phrase}]


PACKET = from_dict({
    "revision": "fixture-1",
    "records": [
        {"id": "lock-lantern", "kind": "locked", "statement": "The lantern stays broken through Vol 1.",
         "topics": ["lantern"], "contradicts": [r"lantern (works|lights|flares)"], "volumes": [1],
         "provenance": P("LOCK: lantern broken in Vol 1", 101)},
        {"id": "lock-bridge", "kind": "locked", "statement": "The east bridge fell before the story.",
         "topics": ["bridge"], "contradicts": [r"\b(fix|repair|rebuild)\w*"],
         "provenance": P("LOCK: east bridge fell", 102)},
        {"id": "cand-scar", "kind": "candidate", "statement": "Ari may carry a hand scar.",
         "topics": ["scar"], "contradicts": [r"unscarred|no scar"],
         "provenance": P("candidate: hand scar", 103)},
    ],
    "scenes": [
        {"scene_id": "v1-s1", "route": "prime", "variant": "A", "volume": 1, "order": 1,
         "text": "Ari takes the job at the dock."},
        {"scene_id": "v1-s3-chase", "route": "prime", "variant": "A", "volume": 1, "order": 3,
         "text": "Ari sprints the rooftops, vaults the gap and shoulders through the gate."},
        {"scene_id": "v2-s1", "route": "prime", "variant": "A", "volume": 2, "order": 10, "text": ""},
    ],
    "timeline": [
        {"fact_id": "knows-job", "route": "prime", "order": 1, "statement": "Ari took the dock job.",
         "patterns": [r"\bthe job\b"], "provenance": P("timeline: dock job", 201)},
        {"fact_id": "knows-traitor", "route": "prime", "order": 7, "statement": "The client is the traitor.",
         "patterns": [r"client (is|was) the traitor", r"\btraitor\b"], "provenance": P("timeline: traitor reveal", 202)},
    ],
    "capabilities": [
        {"id": "vault", "level": 1, "statement": "Parkour vaulting.", "patterns": [r"\bvault"],
         "provenance": P("cap L1 vault", 301)},
        {"id": "shoulder", "level": 2, "statement": "Shoulder breach.", "patterns": [r"\bshoulder"],
         "provenance": P("cap L2 shoulder breach", 302)},
        {"id": "phase", "level": 5, "statement": "Phase through walls.", "patterns": [r"\bphas(e|es|ing)\b"],
         "provenance": P("cap L5 phase", 303)},
    ],
    "level_locks": {"1": [1, 3]},
    "level_lock_provenance": P("LOCK: Vol 1 is Level 1-3", 400),
})
CHASE = "v1-s3-chase"


# --- done-when (1): only what she should know --------------------------------
def test_timeline_trace_splits_known_and_forbidden():
    r = timeline_trace(PACKET, CHASE)
    f = r.findings[0]
    assert r.verdict == "pass"
    assert f["knowledge_before"] == ["knows-job"] and f["forbidden_future_knowledge"] == ["knows-traitor"]


def test_timeline_catches_accidental_omniscience():
    r = timeline_trace(PACKET, CHASE, "Ari runs, sure now the client is the traitor.")
    assert r.verdict == "knowledge_violation"
    assert r.findings[0]["violations"][0]["fact_id"] == "knows-traitor"


# --- done-when (2): stays inside Level 1-3 ------------------------------------
def test_power_ceiling_allows_in_lock_and_refuses_over_lock():
    ok = power_ceiling(PACKET, CHASE, "she vaults the gap")
    assert ok.verdict == "allowed" and ok.findings[0]["level_lock"] == [1, 3]
    bad = power_ceiling(PACKET, CHASE, "she phases through the wall")
    assert bad.verdict == "disallowed" and bad.findings[0]["disallowed"][0]["over_by"] == 2
    assert [c["id"] for c in bad.findings[0]["nearest_legal_expression"]] == ["shoulder", "vault"]


def test_power_ceiling_missing_lock_or_unknown_action_is_never_a_pass():
    assert power_ceiling(PACKET, "v2-s1", "vaults").verdict == "no_lock_for_volume"
    assert power_ceiling(PACKET, CHASE, "she whistles").verdict == "unclassified"
    assert power_ceiling(PACKET, "nope", "vaults").verdict == "unknown_scene"


# --- done-when (3): no false conflict from irrelevant locks ------------------
def test_engineering_question_draws_no_canon_conflict():
    # regression for the ask_xoah false positive: an engineering question that
    # happens to contain a lock's contradiction word ("fix") must not fire it.
    r = scene_pressure_test(PACKET, text="How do I fix the flaky pytest in the CI branch?",
                            route="prime", volume=1)
    assert r.verdict == "out_of_domain" and r.findings[0]["skipped_irrelevant"] == 3


def test_irrelevant_lock_does_not_fire_inside_a_story_scene():
    r = scene_pressure_test(PACKET, CHASE, "Ari will fix her route map mid-run and vault the gap.")
    assert r.verdict == "pass"
    assert r.findings[0]["relevant_records"] == [] and r.findings[0]["hard"] == []


def test_relevant_lock_still_fires_and_scope_is_respected():
    r = scene_pressure_test(PACKET, CHASE, "The lantern flares as Ari vaults.")
    assert r.verdict == "hard_contradictions" and r.findings[0]["hard"][0]["record"] == "lock-lantern"
    # same text outside the lock's volume scope: lock not consulted
    r2 = scene_pressure_test(PACKET, text="The lantern flares.", route="prime", volume=2)
    assert r2.verdict == "pass"


def test_candidate_lore_only_soft_flags():
    r = scene_pressure_test(PACKET, CHASE, "Ari, unscarred, vaults the scar-less wall; no scar yet.")
    assert r.verdict == "soft_flags" and r.findings[0]["soft"][0]["kind"] == "candidate"


def test_power_and_timeline_feed_the_pressure_test():
    r = scene_pressure_test(PACKET, CHASE, "Ari phases through the gate.")
    assert r.verdict == "hard_contradictions" and r.findings[0]["hard"][0]["check"] == "power"


# --- done-when (4): receipt names every canon source used ---------------------
def test_scene_receipt_names_every_canon_source_and_is_reproducible():
    a = scene_receipt(PACKET, CHASE, model_and_prompt_hash="m1")
    b = scene_receipt(PACKET, CHASE, model_and_prompt_hash="m1")
    assert a.receipt_id == b.receipt_id and a.verdict == "clean"
    f = a.findings[0]
    srcs = " ".join(f["canon_sources"])
    for phrase in ("dock job", "traitor reveal", "Vol 1 is Level 1-3", "cap L1 vault", "cap L2 shoulder"):
        assert phrase in srcs, phrase
    assert "east bridge" not in srcs  # irrelevant lock never counted as used
    assert f["power_state"]["verdict"] == "allowed" and f["conflicts_remaining"] == []


def test_packet_refuses_records_without_provenance():
    with pytest.raises(ValueError):
        from_dict({"revision": "x", "records": [{"id": "r", "kind": "locked", "statement": "s"}]})
