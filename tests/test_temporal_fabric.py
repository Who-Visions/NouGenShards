import sqlite3
from datetime import datetime, timezone

import pytest

from nougen_shards.temporal_fabric import (
    HybridLogicalClock,
    TemporalEnvelope,
    TemporalFabric,
    advance_hlc,
    causal_relation,
    extract_temporal_mentions,
    route_temporal_query,
    to_epoch_ms,
)


def test_epoch_milliseconds_preserve_subsecond_precision_and_require_zone():
    assert to_epoch_ms("2026-09-16") == to_epoch_ms("2026-09-16T00:00:00Z")
    assert to_epoch_ms("2026-09-16T12:00:00.123Z") == to_epoch_ms("2026-09-16T08:00:00.123-04:00")
    assert to_epoch_ms("2026-09-16T12:00:00.124Z") - to_epoch_ms("2026-09-16T12:00:00.123Z") == 1
    with pytest.raises(ValueError, match="timezone is required"):
        to_epoch_ms("2026-09-16T12:00:00")


def test_temporal_envelope_keeps_distinct_clocks_and_precision():
    envelope = TemporalEnvelope.from_timestamps("artifact-1", {
        "created_at": "2025-11-01T01:02:03.123Z",
        "event_at": "2025-10-31",
        "ai_touched_at": "2026-09-16T12:00:00.123456Z",
        "valid_from": "2025-10-31",
        "system_at": "2026-09-16T12:00:01Z",
    }, clock_offset_ms=6_000, clock_uncertainty_ms=8)
    assert envelope.created_at_ms != envelope.event_at_ms
    assert envelope.ai_touched_at_ms > envelope.created_at_ms
    assert envelope.original_precision["created_at"] == "millisecond"
    assert envelope.original_precision["ai_touched_at"] == "microsecond"
    assert envelope.drift_flag is True
    assert envelope.clock_uncertainty_ms == 8
    assert envelope.to_dict()["normalized_timestamps"]["created_at"].endswith("Z")
    assert envelope.to_dict()["normalized_timestamps"]["migrated_at"] is None


def test_hlc_is_monotonic_and_clock_uncertainty_blocks_causal_claims():
    previous = HybridLogicalClock(100, 4, "node-a", "event-a")
    observed = HybridLogicalClock(100, 8, "node-b", "event-b")
    advanced = advance_hlc(99, "node-a", "event-c", previous, observed)
    assert advanced == HybridLogicalClock(100, 9, "node-a", "event-c")
    assert causal_relation(100, 10, 105, 10) == "uncertain_or_concurrent"
    assert causal_relation(100, 1, 105, 1) == "definitely_before"
    assert causal_relation(100, None, 105, 0) == "uncertain_or_concurrent"


def test_bitemporal_resolution_distinguishes_when_true_from_when_known(tmp_path):
    fabric = TemporalFabric(tmp_path / "temporal.sqlite", node_id="test-node")
    fabric.record_version("policy", {"value": "draft"}, valid_from_ms=100, known_from_ms=110,
                          valid_to_ms=200, event_id="draft")
    fabric.record_version("policy", {"value": "corrected"}, valid_from_ms=100, known_from_ms=150,
                          event_id="correction")

    before_correction = fabric.resolve_as_of("policy", valid_as_of_ms=160, known_as_of_ms=120)
    after_correction = fabric.resolve_as_of("policy", valid_as_of_ms=160, known_as_of_ms=160)
    assert before_correction["version"]["payload"]["content"]["value"] == "draft"
    assert after_correction["version"]["payload"]["content"]["value"] == "corrected"
    assert fabric.resolve_as_of("policy", valid_as_of_ms=160, known_as_of_ms=109)["status"] == "cannot_determine"
    ended = fabric.events_for_range("valid_to", 199, 201, artifact_id="policy")
    assert [event["event_id"] for event in ended] == ["draft"]


def test_ai_touch_is_append_only_and_does_not_mutate_canonical_version(tmp_path):
    fabric = TemporalFabric(tmp_path / "temporal.sqlite", node_id="test-node")
    version = fabric.record_version("fact", {"value": 7}, valid_from_ms=10, known_from_ms=20,
                                    event_id="version-1")
    touch = fabric.record_ai_touch("fact", event_id="touch-1", touched_at_ms=30, system_at_ms=31)
    resolved = fabric.resolve_as_of("fact", valid_as_of_ms=25, known_as_of_ms=40)
    assert touch["event_type"] == "ai_touch"
    assert touch["clock_uncertainty_ms"] is None
    assert touch["causal_confidence"] == "uncertain"
    assert resolved["version"]["event_id"] == version["event_id"]

    with fabric._connect() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE temporal_events SET physical_ms=0 WHERE event_id='touch-1'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM temporal_events WHERE event_id='touch-1'")


def test_lifecycle_capture_migration_and_touch_remain_distinct(tmp_path):
    fabric = TemporalFabric(tmp_path / "temporal.sqlite", node_id="test-node")
    envelope = TemporalEnvelope.from_timestamps("artifact", {
        "created_at": "2025-11-01T00:00:00.001Z",
        "event_at": "2025-10-31T23:59:59.999Z",
        "captured_at": "2026-09-16T12:00:00.000Z",
        "migrated_at": "2026-09-16T12:00:01.000Z",
        "ai_touched_at": "2026-09-16T12:00:02.000Z",
    })
    events = fabric.record_envelope(envelope)
    assert {event["event_type"] for event in events} == {"created", "event", "capture", "migration", "ai_touch"}
    clocks = {event["payload_json"]: event["physical_ms"] for event in events}
    assert envelope.created_at_ms != envelope.event_at_ms
    assert envelope.created_at_ms < envelope.captured_at_ms < envelope.migrated_at_ms < envelope.ai_touched_at_ms
    assert len(clocks) == len(events)


def test_inline_mentions_are_anchored_indexed_and_queryable(tmp_path):
    anchor = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    mentions = extract_temporal_mentions(
        "Created November 2025; we reviewed it yesterday and on 2025-11-03.",
        anchor, "America/New_York",
    )
    assert [mention["raw_text"] for mention in mentions] == [
        "November 2025", "yesterday", "2025-11-03",
    ]
    assert mentions[0]["precision"] == "month"
    assert mentions[0]["semantic_role"] == "created_at"
    assert mentions[1]["normalized_start_ms"] == to_epoch_ms("2026-09-15T00:00:00-04:00")

    fabric = TemporalFabric(tmp_path / "temporal.sqlite", node_id="test-node")
    indexed = fabric.index_mentions("artifact", "We reviewed it yesterday.", anchor=anchor,
                                    timezone_name="America/New_York", captured_at_ms=99)
    found = fabric.mentions_between(indexed[0]["normalized_start_ms"],
                                    indexed[0]["normalized_end_ms"], artifact_id="artifact")
    assert found[0]["raw_text"] == "yesterday"
    assert found[0]["anchor_ms"] == to_epoch_ms(anchor)
    assert route_temporal_query("What did the AI touch yesterday?")["routes"][0]["dimension"] == "ai_touched_at"


def test_temporal_range_uses_explicit_dimension_and_index(tmp_path):
    fabric = TemporalFabric(tmp_path / "temporal.sqlite", node_id="test-node")
    fabric.record_lifecycle("artifact", "migration", raw_timestamp="2025-11-03T10:00:00.123Z")
    assert len(fabric.events_for_range("migrated_at", to_epoch_ms("2025-11-03"),
                                       to_epoch_ms("2025-11-04"))) == 1
    assert fabric.events_for_range("system_at_ms", 0, 2**63 - 1)
    with fabric._connect() as conn:
        plan = conn.execute("""EXPLAIN QUERY PLAN SELECT event_id FROM temporal_events
            WHERE event_type=? AND physical_ms>=? AND physical_ms<?""",
            ("migration", 1762128000000, 1762214400000)).fetchall()
    assert any("idx_temporal_physical_range" in row["detail"] for row in plan)
