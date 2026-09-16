"""Tests for Reconstructive Recall & Evidence-Locked Temporal Multi-Store.

Verifies conflict-at-write gating, provenance path finding, staged pulse execution,
and evidence lock enforcement across multi-store events.
"""

import pytest
from nougen_shards.reconstructive_recall_v2 import (
    AssociativeEdge,
    ContradictionState,
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
