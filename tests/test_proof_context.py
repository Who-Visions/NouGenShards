"""ProofContext: one envelope for canonical, temporal and recall answers."""
import dataclasses
import json

import pytest

from nougen_shards import proof_context as pc
from nougen_shards.canonical_facts import CanonicalFactIndex
from nougen_shards.temporal_fabric import TemporalFabric

from test_canonical_facts import snapshot

MACHINES = ["blade1tb", "phoebus", "whoart"]


def _canonical(tmp_path, with_snapshot=True):
    index = CanonicalFactIndex(tmp_path / "facts.sqlite")
    if with_snapshot:
        index.put(snapshot())
    return index.resolve("token_usage:fleet:YTD:2026", expected_machines=MACHINES)


def test_canonical_present_carries_snapshot_id_and_hashes(tmp_path):
    result = _canonical(tmp_path)
    ctx = pc.from_canonical_resolve(result, query_intent="fleet tokens ytd")
    assert ctx.verdict == "present" and ctx.answered and ctx.verify()
    assert ctx.canonical_snapshot_id == result["snapshot"]["snapshot_id"]
    assert ctx.supporting_shard_hashes == ("a" * 64,)
    assert ctx.plane == "canonical" and ctx.conflict_state == "none" and not ctx.missing_sources


def test_canonical_negative_with_no_coverage_is_not_provable_absence(tmp_path):
    """cannot_determine from an empty index reports present_machines=[]: absence is unproven, not proven."""
    ctx = pc.from_canonical_resolve(_canonical(tmp_path, with_snapshot=False), query_intent="fleet tokens ytd")
    assert ctx.verdict == "absent_unproven" and not ctx.absence_provable
    assert set(ctx.missing_sources) == {f"machine:{m}" for m in MACHINES}


def test_temporal_resolution_and_negative(tmp_path):
    fabric = TemporalFabric(tmp_path / "t.sqlite", node_id="n")
    fabric.record_version("policy", {"value": "draft"}, valid_from_ms=100, known_from_ms=110)
    hit = pc.from_temporal_resolve(fabric.resolve_as_of("policy", valid_as_of_ms=150, known_as_of_ms=150), query_intent="policy at 150")
    assert (hit.verdict, hit.valid_time_ms, hit.known_time_ms) == ("present", 150, 150)
    miss = pc.from_temporal_resolve(fabric.resolve_as_of("policy", valid_as_of_ms=150, known_as_of_ms=50), query_intent="policy known at 50")
    assert miss.verdict == "absent_proven" and miss.absence_provable and miss.verify()
    assert hit.receipt_hash != miss.receipt_hash


def test_failed_or_timed_out_source_blocks_absence_proof():
    base = dict(plane="recall", query_intent="x", answered=False, expected_sources=["phoebus", "blade", "whoart"])
    assert pc.build(**base, succeeded_sources=["phoebus", "blade", "whoart"]).verdict == "absent_proven"
    timed = pc.build(**base, succeeded_sources=["phoebus", "blade", "whoart"], timed_out_sources=["blade"])
    assert timed.verdict == "absent_unproven" and "blade" not in timed.succeeded_sources
    failed = pc.build(**base, succeeded_sources=["phoebus"], failed_sources=["whoart"])
    assert failed.verdict == "absent_unproven" and set(failed.missing_sources) == {"blade", "whoart"}


def test_recall_body_dropped_lane_means_absence_unproven():
    """The 200-with-dropped-lane failure mode: complete:false must never read as 'not found'."""
    body = {"complete": False, "dropped_lanes": [{"lane": "blade", "error": "timed out after 20s"}, "whoart"], "results": []}
    ctx = pc.from_recall(body, query_intent="q", expected_sources=["phoebus", "blade", "whoart"])
    assert ctx.verdict == "absent_unproven"
    assert ctx.timed_out_sources == ("blade",) and ctx.failed_sources == ("whoart",)
    clean = pc.from_recall({"complete": True, "dropped_lanes": [], "results": []}, query_intent="q", expected_sources=["phoebus"])
    assert clean.verdict == "absent_proven"
    found = pc.from_recall({"complete": True, "results": [{"id": 1}]}, query_intent="q", expected_sources=["phoebus"], shard_hashes=["h1"])
    assert found.verdict == "present" and found.supporting_shard_hashes == ("h1",)


def test_multiple_candidates_surface_conflict():
    ctx = pc.build(plane="canonical", query_intent="q", answered=True, expected_sources=["a"], succeeded_sources=["a"], candidate_count=2)
    assert ctx.verdict == "conflicted" and ctx.conflict_state == "conflicted"


def test_same_evidence_yields_byte_identical_receipt_regardless_of_input_order():
    one = pc.build(plane="recall", query_intent="q", answered=True, expected_sources=["b", "a"], succeeded_sources=["a", "b"], supporting_shard_hashes=["z", "y"])
    two = pc.build(plane="recall", query_intent="q", answered=True, expected_sources=["a", "b"], succeeded_sources=["b", "a"], supporting_shard_hashes=["y", "z", "y"])
    assert json.dumps(one.to_dict(), sort_keys=True) == json.dumps(two.to_dict(), sort_keys=True)
    assert one.receipt_hash == two.receipt_hash and len(one.receipt_hash) == 64


@pytest.mark.parametrize("field,value", [
    ("verdict", "present"), ("canonical_snapshot_id", "x"), ("retraction_state", "retracted"),
    ("query_intent", "other"), ("answered", True), ("valid_time_ms", 7),
])
def test_tampering_with_any_field_breaks_verification(field, value):
    ctx = pc.build(plane="canonical", query_intent="q", answered=False, expected_sources=["a"], succeeded_sources=[])
    assert ctx.verify()
    assert not dataclasses.replace(ctx, **{field: value}).verify()


def test_validation_rejects_bad_inputs():
    with pytest.raises(ValueError):
        pc.build(plane="bogus", query_intent="q", answered=True, expected_sources=[], succeeded_sources=[])
    with pytest.raises(ValueError):
        pc.build(plane="recall", query_intent="  ", answered=True, expected_sources=[], succeeded_sources=[])
    with pytest.raises(ValueError):
        pc.build(plane="recall", query_intent="q", answered=True, expected_sources=[], succeeded_sources=[], retraction_state="maybe")
