"""Unit tests for nougen_shards.retrieval_v2 (Retrieval Engine v2 & Recovery Dispatcher)."""
from datetime import datetime, timezone
import pytest
from nougen_shards.retrieval_v2 import (
    ArtifactCandidate,
    CanonicalEntity,
    MultiAxisStateVector,
    OrthogonalFlags,
    QueryReceipt,
    RetrievalIntent,
    TemporalDeixis,
    compile_retrieval_intent,
    create_query_receipt,
    next_recovery_action,
    normalize_nfkc,
    parse_temporal_deixis,
    reciprocal_rank_fusion,
)


def test_typed_query_compiler_temporal_and_entities():
    """Verify deterministic intent compilation, NFKC normalization, temporal parsing, and entity extraction."""
    now = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
    
    entities = [
        CanonicalEntity("ent-blade", "Blade1TB", aliases=("blade", "razer"), machine_binding="blade1tb"),
        CanonicalEntity("ent-phoebus", "Phoebus", aliases=("mac mini",), machine_binding="phoebus"),
    ]
    
    # 1. YTD query across fleet
    intent_ytd = compile_retrieval_intent("What is our total YTD token usage across all machines?", now=now, entities_registry=entities)
    assert intent_ytd.metric == "token_usage"
    assert intent_ytd.temporal.period == "YTD"
    assert intent_ytd.temporal.year == 2026
    assert intent_ytd.scope == "fleet"
    assert intent_ytd.canonical_key == "token_usage::fleet::YTD::2026"

    # 2. Node specific query
    intent_node = compile_retrieval_intent("Show blade token spend today", now=now, entities_registry=entities)
    assert intent_node.metric == "token_usage"
    assert intent_node.temporal.period == "DAILY"
    assert intent_node.scope == "node"
    assert len(intent_node.required_entities) == 1
    assert intent_node.required_entities[0].canonical_name == "Blade1TB"


def test_multi_axis_state_vector_schema_validation():
    """Verify contradiction detection in multi-axis state vectors."""
    # Valid state
    valid_state = MultiAxisStateVector(
        completeness="COMPLETE",
        conflict="CONSISTENT",
        freshness="CURRENT",
        truth_quality="EXACT",
        canonicality="CANONICAL",
        flags=OrthogonalFlags(missing_expected_nodes=False, coverage_complete=True)
    )
    assert valid_state.validate_schema() == []

    # Contradictory state: complete=True with missing_expected_nodes=True
    contradictory_state = MultiAxisStateVector(
        completeness="COMPLETE",
        flags=OrthogonalFlags(missing_expected_nodes=True)
    )
    violations = contradictory_state.validate_schema()
    assert len(violations) > 0
    assert any("missing_expected_nodes" in v for v in violations)


def test_deterministic_recovery_dispatcher():
    """Verify deterministic recovery action dispatching across all failure regimes."""
    # 1. Partial completeness with missing nodes -> CONTINUE_FEDERATION
    s_partial = MultiAxisStateVector(
        completeness="PARTIAL",
        flags=OrthogonalFlags(missing_expected_nodes=True, retryable=True)
    )
    assert next_recovery_action(s_partial) == "CONTINUE_FEDERATION"

    # 2. Conflict detected -> TRACE_PROVENANCE
    s_conflict = MultiAxisStateVector(
        conflict="CONFLICTED",
        flags=OrthogonalFlags(traceable=True)
    )
    assert next_recovery_action(s_conflict) == "TRACE_PROVENANCE"

    # 3. Stale canonical fact -> REFRESH_CANONICAL
    s_stale = MultiAxisStateVector(
        freshness="STALE",
        canonical_key="token_usage::fleet::YTD::2026"
    )
    assert next_recovery_action(s_stale) == "REFRESH_CANONICAL"

    # 4. No hit with incomplete coverage -> EXPAND_RETRIEVAL
    s_nohit_inc = MultiAxisStateVector(
        retrieval="NO_HIT",
        flags=OrthogonalFlags(coverage_complete=False)
    )
    assert next_recovery_action(s_nohit_inc) == "EXPAND_RETRIEVAL"

    # 5. No hit with full coverage but deeper search available -> DRIFT_RECURSE
    s_nohit_recurse = MultiAxisStateVector(
        retrieval="NO_HIT",
        flags=OrthogonalFlags(coverage_complete=True, deeper_search_available=True)
    )
    assert next_recovery_action(s_nohit_recurse) == "DRIFT_RECURSE"

    # 6. Timeout with failover route -> FAILOVER
    s_timeout = MultiAxisStateVector(
        availability="TIMEOUT",
        flags=OrthogonalFlags(failover_available=True)
    )
    assert next_recovery_action(s_timeout) == "FAILOVER"

    # 7. Superseded revision -> FOLLOW_SUPERSESSION
    s_super = MultiAxisStateVector(
        canonicality="SUPERSEDED"
    )
    assert next_recovery_action(s_super) == "FOLLOW_SUPERSESSION"


def test_deterministic_reciprocal_rank_fusion():
    """Verify deterministic multi-lane candidate fusion with stable tie-breaking."""
    lane_exact = [
        ArtifactCandidate(candidate_id="art-001", title="YTD Fleet Rollup 2026", lane="exact", raw_score=1.0),
        ArtifactCandidate(candidate_id="art-002", title="Blade Node Summary", lane="exact", raw_score=0.9),
    ]
    lane_bm25 = [
        ArtifactCandidate(candidate_id="art-002", title="Blade Node Summary", lane="bm25", raw_score=15.4),
        ArtifactCandidate(candidate_id="art-003", title="Phoebus Node Summary", lane="bm25", raw_score=12.1),
    ]
    lane_ann = [
        ArtifactCandidate(candidate_id="art-001", title="YTD Fleet Rollup 2026", lane="ann", raw_score=0.88),
        ArtifactCandidate(candidate_id="art-003", title="Phoebus Node Summary", lane="ann", raw_score=0.82),
    ]

    fused = reciprocal_rank_fusion({
        "exact": lane_exact,
        "bm25": lane_bm25,
        "ann": lane_ann,
    }, k=60, top_n=5)

    assert len(fused) == 3
    # art-001 and art-002 appear in multiple lanes with high ranks -> top positions
    top_candidate, top_score = fused[0]
    assert top_candidate.candidate_id in ("art-001", "art-002")
    assert top_score > 0.03


def test_query_receipt_generation_and_serialization():
    """Verify QueryReceipt generation, deterministic hashing, and JSON fidelity."""
    intent = compile_retrieval_intent("YTD tokens across all nodes")
    state = MultiAxisStateVector(
        completeness="COMPLETE",
        conflict="CONSISTENT",
        freshness="CURRENT",
        canonical_key=intent.canonical_key,
    )
    candidates = [
        ArtifactCandidate(candidate_id="art-001", title="YTD Fleet Rollup", lane="exact", raw_score=1.0)
    ]

    receipt = create_query_receipt(
        intent=intent,
        state=state,
        fused_candidates=candidates,
        coverage_nodes=("whoart", "blade1tb", "phoebus"),
        latency_ms=12.4
    )

    assert receipt.recommended_action == "STOP_WITH_EXPLICIT_STATE"
    assert len(receipt.receipt_hash) == 16
    json_str = receipt.to_json()
    assert "token_usage::fleet::YTD::2026" in json_str
    assert "qr-" in receipt.query_id
