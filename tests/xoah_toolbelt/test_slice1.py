"""All canon here is INVENTED placeholder data ("Vale", "the ferry chase"); it is not Shadow Dweller lore."""
import pytest

from nougen_shards.xoah_toolbelt import (PacketUnavailable, load_packet, packet_from_dict, power_ceiling,
                                         scene_pressure_test, scene_receipt, timeline_trace)

def P(n):
    return {"shard_id": n, "db": "db1", "node": "test", "phrase": f"fixture {n}"}
PACKET = packet_from_dict({
    "revision": "fixture-r1",
    "records": [
        {"id": "R_KNOWS_MAP", "kind": "locked", "statement": "Vale has the ferry map.", "provenance": [P(2)]},
        {"id": "R_NO_FLY", "kind": "locked", "statement": "Vale never flies unaided.",
         "topics": ["vale", "flies"], "contradicts": ["flies unaided"], "provenance": [P(4)]},
        {"id": "R_ENGINE", "kind": "locked", "statement": "Rigs overheat after 3 burns.",
         "topics": ["rig", "burn"], "contradicts": ["never overheat"], "provenance": [P(5)]},
        {"id": "R_TWIN", "kind": "candidate", "statement": "Vale may have a twin.",
         "contradicts": ["only child"], "provenance": [P(6)]},
    ],
    "scenes": [{"scene_id": "v1_chase", "route": "prime", "variant": "base", "volume": 1, "order": 5},
               {"scene_id": "v1_x2", "route": "x2", "variant": "base", "volume": 1, "order": 5}],
    "timeline": [
        {"fact_id": "R_KNOWS_MAP", "route": "prime", "order": 2, "statement": "gets map", "provenance": [P(2)]},
        {"fact_id": "F_TRAITOR", "route": "prime", "order": 9, "statement": "pilot is traitor",
         "patterns": ["pilot betrayed"], "provenance": [P(3)]},
    ],
    "capabilities": [{"id": "leap", "level": 2, "patterns": ["\\bleaps?\\b"]},
                     {"id": "veil step", "level": 3, "patterns": ["veil step"]},
                     {"id": "tear space", "level": 7, "patterns": ["tears? space"]}],
    "level_locks": {"1": [1, 3]},
    "level_lock_provenance": [P(1)],
})
TEXT = "Vale leaps the rail and veil steps past the gate."
KW = dict(actions=("leap", "veil step"), refs=("R_KNOWS_MAP",))


def test_timeline_only_knows_the_past_and_is_route_aware():
    f = timeline_trace(PACKET, "v1_chase").findings[0]
    assert f["knowledge_before"] == ["R_KNOWS_MAP"] and f["forbidden_future_knowledge"] == ["F_TRAITOR"]
    assert timeline_trace(PACKET, "v1_x2").findings[0]["knowledge_before"] == []


def test_unknown_scene_is_insufficient_context():
    r = timeline_trace(PACKET, "nope")
    assert r.verdict == "insufficient_context" and r.findings[0]["missing"] == ["scene:nope"]


def test_power_ceiling_allows_l3_blocks_l7_with_nearest_legal_and_cites():
    assert power_ceiling(PACKET, "veil step", scene_id="v1_chase").verdict == "allowed"
    r = power_ceiling(PACKET, "tear space", scene_id="v1_chase")
    assert r.verdict == "disallowed" and r.findings[0]["nearest_legal_expression"] == "veil step"
    assert r.sources and r.sources[0].shard_id == 1


def test_power_ceiling_fails_closed_without_lock():
    r = power_ceiling(PACKET, "leap", volume=9)
    assert r.verdict == "no_ceiling_defined" and r.findings[0]["allowed"] is False


def test_clean_chase_passes_and_receipt_names_every_source():
    r = scene_receipt(PACKET, "v1_chase", TEXT, model_and_prompt="m|p", **KW)
    s = r.findings[0]
    assert r.verdict == "pass" and s["conflicts_remaining"] == []
    assert set(s["canon_sources"]) == {"R_KNOWS_MAP", "R_NO_FLY", "R_ENGINE"}
    assert s["timeline_state"]["forbidden_future_knowledge"] == ["F_TRAITOR"]
    assert r.receipt_id and r == scene_receipt(PACKET, "v1_chase", TEXT, model_and_prompt="m|p", **KW)


def test_over_ceiling_action_is_hard_with_repair():
    r = scene_pressure_test(PACKET, "v1_chase", "Vale tears space open.", actions=("tear space",))
    assert r.verdict == "hard_contradiction" and r.findings[1]["repair"] == "use 'veil step'"


def test_forbidden_future_knowledge_by_ref_and_by_text():
    r = scene_pressure_test(PACKET, "v1_chase", "Vale realises the pilot betrayed them.", refs=("F_TRAITOR",))
    assert [f["check"] for f in r.findings[1:]] == ["forbidden_future_knowledge"]   # one flag per fact


def test_regression_irrelevant_lock_does_not_fire_false_fact_conflict():
    engineering = "The ferry hull coating claims it can never overheat in the sun."
    r = scene_pressure_test(PACKET, "v1_chase", engineering)
    assert r.verdict == "pass"
    assert r.findings[0]["suppressed_irrelevant"] == [{"record": "R_ENGINE", "matched": "never overheat",
                                                       "reason": "scene does not touch this record's topics"}]
    real = scene_pressure_test(PACKET, "v1_chase", "Her rig will never overheat, however many burn cycles.")
    assert real.verdict == "hard_contradiction" and real.findings[1]["ref"] == "R_ENGINE"


def test_non_locked_records_never_hard_and_stay_distinct():
    r = scene_receipt(PACKET, "v1_chase", "Vale was an only child.", refs=("R_TWIN",))
    s = r.findings[0]
    assert r.verdict == "soft_flags" and s["candidate_sources"] == ["R_TWIN"]
    assert "R_TWIN" not in s["canon_sources"]


def test_missing_packet_raises(monkeypatch):
    monkeypatch.delenv("NOUGEN_XOAH_PACKET", raising=False)
    with pytest.raises(PacketUnavailable):
        load_packet()
