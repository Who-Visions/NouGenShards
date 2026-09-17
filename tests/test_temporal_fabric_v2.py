"""Unit tests for nougen_shards.temporal_fabric_v2 (Temporal Fabric v2)."""
from datetime import datetime, timezone
from nougen_shards.temporal_fabric_v2 import (
    HLCTracker,
    HybridLogicalClock,
    TemporalEnvelope,
    extract_temporal_mentions,
    route_temporal_query,
)


def test_bitemporal_envelope_non_collapsing():
    """Verify distinct lifecycle epochs: created != migrated != captured != ai_touched."""
    dt_created = datetime(2024, 11, 15, 0, 0, 0, tzinfo=timezone.utc)
    dt_migrated = datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc)
    dt_captured = datetime(2026, 9, 16, 20, 20, 0, tzinfo=timezone.utc)

    created_ms = int(dt_created.timestamp() * 1000)
    migrated_ms = int(dt_migrated.timestamp() * 1000)
    captured_ms = int(dt_captured.timestamp() * 1000)

    env = TemporalEnvelope(
        created_at_ms=created_ms,
        migrated_at_ms=migrated_ms,
        captured_at_ms=captured_ms,
        ai_touched_at_ms=captured_ms + 500,
    )

    # Invariant: migrated_at does NOT overwrite created_at
    assert env.created_at_ms == created_ms
    assert env.migrated_at_ms == migrated_ms
    assert env.created_at_ms < env.migrated_at_ms < env.captured_at_ms

    iso_dict = env.to_iso_dict()
    assert "2024-11-15" in iso_dict["created_at_iso"]
    assert "2026-07-05" in iso_dict["migrated_at_iso"]


def test_hybrid_logical_clock_deterministic_ordering():
    """Verify HLC monotonicity and distributed tie-breaking."""
    tracker = HLCTracker(node_id="whoart")
    
    t1 = tracker.now(event_id="ev1")
    t2 = tracker.now(event_id="ev2")
    
    assert t1 < t2
    assert t1.node_id == "whoart"
    assert t2.node_id == "whoart"

    # Cross-node tie-break
    t_blade = HybridLogicalClock(physical_ms=1000, logical_counter=0, node_id="blade1tb", event_id="a")
    t_whoart = HybridLogicalClock(physical_ms=1000, logical_counter=0, node_id="whoart", event_id="a")
    assert t_blade < t_whoart  # 'blade1tb' < 'whoart' alphabetically


def test_inline_temporal_mention_extraction_with_anchors():
    """Verify extraction of absolute dates and preserved relative anchors."""
    anchor = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
    text = "We agreed on 2025-11-26 that yesterday the system was patched, and by Nov 28 we launch."
    
    mentions = extract_temporal_mentions(text, anchor_dt=anchor)
    assert len(mentions) >= 3

    # ISO date
    m_iso = [m for m in mentions if m.raw_text == "2025-11-26"][0]
    assert m_iso.semantic_role == "event_date"
    assert "2025-11-26" in datetime.fromtimestamp(m_iso.normalized_start_ms / 1000.0, tz=timezone.utc).isoformat()

    # Relative 'yesterday'
    m_rel = [m for m in mentions if m.raw_text.lower() == "yesterday"][0]
    assert m_rel.semantic_role == "relative_reference"
    assert m_rel.anchor_ms == int(anchor.timestamp() * 1000)
    assert "2026-09-15" in datetime.fromtimestamp(m_rel.normalized_start_ms / 1000.0, tz=timezone.utc).isoformat()

    # Month Day 'Nov 28'
    m_mon = [m for m in mentions if "Nov 28" in m.raw_text][0]
    assert "11-28" in datetime.fromtimestamp(m_mon.normalized_start_ms / 1000.0, tz=timezone.utc).isoformat()


def test_temporal_query_routing():
    """Verify accurate dimension routing for temporal queries."""
    assert route_temporal_query("When did the breach happen?") == "event_at_ms"
    assert route_temporal_query("When was this shard touched by AI?") == "ai_touched_at_ms"
    assert route_temporal_query("When was the legacy data migrated?") == "migrated_at_ms"
    assert route_temporal_query("When was this document created?") == "created_at_ms"
