"""Tests for Reconstructive Recall & Evidence-Locked Temporal Multi-Store.

Verifies conflict-at-write gating, provenance path finding, staged pulse execution,
and evidence lock enforcement across multi-store events.
"""

from dataclasses import replace

import pytest
from nougen_shards.reconstructive_recall_v2 import (
    AssociativeEdge,
    ContradictionState,
    EvidenceLockError,
    MemoryEvent,
    ReconstructiveRecallEngine,
    SourceType,
)


@pytest.fixture
def populated_engine():
    engine = ReconstructiveRecallEngine()

    # Event 1: Apollo telemetry
    ev1 = MemoryEvent(
        event_id="ev_apollo_01",
        event_ms=1763500000000,
        created_ms=1763500000000,
        updated_ms=1763500000000,
        ai_touched_ms=0,
        migrated_ms=0,
        source_node="apollo",
        source_type=SourceType.EPISODIC_RELAY,
        content="Apollo node initialized with 8GB VRAM RTX 2080 Super",
        contradiction_group="apollo_gpu_spec"
    )
    engine.insert_event(ev1)

    # Event 2: Hyperion telemetry
    ev2 = MemoryEvent(
        event_id="ev_hyperion_01",
        event_ms=1789500000000,
        created_ms=1789500000000,
        updated_ms=1789500000000,
        ai_touched_ms=0,
        migrated_ms=0,
        source_node="hyperion",
        source_type=SourceType.DOCUMENTARY_SHARD,
        content="Hyperion node initialized with 6GB VRAM RTX 4050",
        contradiction_group="hyperion_gpu_spec"
    )
    engine.insert_event(ev2)

    # Associative Edges: entity:fleet -> ev_apollo_01, entity:fleet -> ev_hyperion_01
    engine.add_edge(AssociativeEdge(
        source_id="entity:fleet",
        target_id="ev_apollo_01",
        relation="CONTAINS_NODE",
        weight_bps=9000
    ))
    engine.add_edge(AssociativeEdge(
        source_id="entity:fleet",
        target_id="ev_hyperion_01",
        relation="CONTAINS_NODE",
        weight_bps=9500
    ))
    # Edge bridge: ev_apollo_01 -> bridge_node -> ev_hyperion_01
    engine.add_edge(AssociativeEdge(
        source_id="ev_apollo_01",
        target_id="mesh_bridge",
        relation="BRIDGES_TO",
        weight_bps=8000
    ))
    engine.add_edge(AssociativeEdge(
        source_id="mesh_bridge",
        target_id="ev_hyperion_01",
        relation="BRIDGES_TO",
        weight_bps=8000
    ))

    return engine


def test_conflict_at_write_gating(populated_engine):
    # Test versioned supersession
    ev_superseded = MemoryEvent(
        event_id="ev_apollo_02",
        event_ms=1789600000000,
        created_ms=1789600000000,
        updated_ms=1789600000000,
        ai_touched_ms=0,
        migrated_ms=0,
        source_node="apollo",
        source_type=SourceType.EPISODIC_RELAY,
        content="Apollo node upgraded with custom cooling and higher clock limit",
        supersedes="ev_apollo_01",
        contradiction_group="apollo_gpu_spec"
    )
    ok, c_state = populated_engine.insert_event(ev_superseded)
    assert ok is True
    assert c_state == ContradictionState.VERSIONED

    # Test conflicting un-superseded insert -> QUARANTINED
    ev_conflict = MemoryEvent(
        event_id="ev_apollo_conflict",
        event_ms=1789600000000,
        created_ms=1789600000000,
        updated_ms=1789600000000,
        ai_touched_ms=0,
        migrated_ms=0,
        source_node="apollo",
        source_type=SourceType.EPISODIC_RELAY,
        content="Apollo node has 24GB VRAM",
        contradiction_group="apollo_gpu_spec"
    )
    ok2, c_state2 = populated_engine.insert_event(ev_conflict)
    assert ok2 is True
    assert c_state2 == ContradictionState.QUARANTINED


def test_associative_provenance_path(populated_engine):
    path = populated_engine.find_provenance_path("ev_apollo_01", "ev_hyperion_01")
    assert path == ["ev_apollo_01", "mesh_bridge", "ev_hyperion_01"]


def test_pulse_retrieval_and_evidence_lock(populated_engine):
    envelope = populated_engine.execute_pulse_retrieval("Apollo VRAM 8GB spec")
    assert envelope.abstention_reason is None
    assert "ev_apollo_01" in envelope.opened_evidence_ids
    assert len(envelope.provenance_lock_sha) == 64
    assert envelope.vault_coverage_pct_bps == 10000
    assert "ev_apollo_01" in envelope.reconstructed_text
    assert envelope.latency_by_phase_us["pulse_1_us"] >= 0
    assert envelope.latency_by_phase_us["pulse_2_us"] >= 0


def test_coverage_and_temporal_as_of(populated_engine):
    # As of Dec 2025 -> ev_hyperion_01 (Sep 2026) must NOT appear
    envelope = populated_engine.execute_pulse_retrieval(
        "fleet nodes VRAM",
        as_of_ms=1764000000000,
        required_nodes={"apollo", "hyperion"}
    )
    assert "ev_apollo_01" in envelope.opened_evidence_ids
    assert "ev_hyperion_01" not in envelope.opened_evidence_ids
    # Since hyperion is missing in as_of window, coverage should be 5000 bps (50%)
    assert envelope.vault_coverage_pct_bps == 5000


def test_quarantined_candidate_is_never_retrieved(populated_engine):
    conflict = MemoryEvent(
        event_id="ev_apollo_unverified",
        event_ms=1789600000000,
        created_ms=1789600000000,
        updated_ms=1789600000000,
        ai_touched_ms=0,
        migrated_ms=0,
        source_node="apollo",
        source_type=SourceType.EPISODIC_RELAY,
        content="Apollo has 24GB VRAM",
        contradiction_group="apollo_gpu_spec",
    )
    ok, state = populated_engine.insert_event(conflict)

    assert ok is True
    assert state is ContradictionState.QUARANTINED
    assert conflict.event_id not in populated_engine.events
    assert conflict.event_id in populated_engine.quarantined_events
    envelope = populated_engine.execute_pulse_retrieval("Apollo 24GB VRAM")
    assert conflict.event_id not in envelope.opened_evidence_ids
    assert "24GB VRAM" not in envelope.reconstructed_text


def test_bitemporal_filter_distinguishes_valid_from_recorded_time(populated_engine):
    late_record = MemoryEvent(
        event_id="ev_late_import",
        event_ms=1763500000000,
        created_ms=1765000000000,
        updated_ms=1765000000000,
        ai_touched_ms=0,
        migrated_ms=0,
        source_node="apollo",
        source_type=SourceType.EPISODIC_RELAY,
        content="late imported event marker",
    )
    populated_engine.insert_event(late_record)

    before_recorded = populated_engine.execute_pulse_retrieval(
        "late imported event marker", as_of_ms=1764000000000, known_as_of_ms=0
    )
    after_recorded = populated_engine.execute_pulse_retrieval(
        "late imported event marker", as_of_ms=1764000000000, known_as_of_ms=1765000000000
    )

    assert late_record.event_id not in before_recorded.opened_evidence_ids
    assert late_record.event_id in after_recorded.opened_evidence_ids
    assert "known_as_of_ms=0" in before_recorded.temporal_coverage


def test_evidence_lock_rejects_unopened_and_changed_sources(populated_engine):
    envelope = populated_engine.execute_pulse_retrieval("Apollo VRAM 8GB spec")
    assert populated_engine.verify_evidence_lock(envelope, {"ev_apollo_01"}) is True
    with pytest.raises(EvidenceLockError, match="not present"):
        populated_engine.verify_evidence_lock(envelope, {"ev_never_opened"})
    altered_manifest = dict(envelope.evidence_manifest)
    altered_manifest["ev_apollo_01"] = "0" * 64
    with pytest.raises(EvidenceLockError, match="changed"):
        populated_engine.verify_evidence_lock(replace(envelope, evidence_manifest=altered_manifest))

    current = populated_engine.events["ev_apollo_01"]
    populated_engine.events[current.event_id] = replace(current, content="mutated after read")
    with pytest.raises(EvidenceLockError, match="changed"):
        populated_engine.verify_evidence_lock(envelope)


def test_partial_source_lanes_report_degraded_coverage():
    engine = ReconstructiveRecallEngine(available_stores={SourceType.EPISODIC_RELAY})
    event = MemoryEvent(
        event_id="ev_local_only",
        event_ms=1,
        created_ms=1,
        updated_ms=1,
        ai_touched_ms=0,
        migrated_ms=0,
        source_node="apollo",
        source_type=SourceType.EPISODIC_RELAY,
        content="local source lane evidence",
    )
    engine.insert_event(event)

    envelope = engine.execute_pulse_retrieval("local source lane evidence")

    assert envelope.scanned_stores == [SourceType.EPISODIC_RELAY.value]
    assert envelope.store_coverage_bps == 2500
    assert envelope.vault_coverage_pct_bps == 2500
