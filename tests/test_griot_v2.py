"""Unit tests for nougen_shards.griot_v2 (HURRICANE KICK Griot v2 Golden Tests)."""
from nougen_shards.griot_v2 import (
    CompoundShardRef,
    EpistemicClass,
    gather_griot_archive,
    infer_epistemic_class,
)


def test_coverage_honesty_on_blade_timeout_and_whoart_502():
    """Golden Test 1: Blade timeout + WhoArt 502 MUST NOT return clean failures=[] or complete coverage."""
    simulated_errors = {
        "blade1tb": "TIMEOUT (connection deadline exceeded after 5000ms)",
        "whoart": "HTTP 502 Bad Gateway",
    }
    
    packet = gather_griot_archive(
        query="YTD token cost across fleet",
        simulated_node_failures=simulated_errors,
    )

    # Invariant 1: failures list must explicitly contain both failed nodes
    assert len(packet.coverage.failures) >= 2
    assert any("blade1tb" in f for f in packet.coverage.failures)
    assert any("whoart" in f for f in packet.coverage.failures)

    # Invariant 2: Coverage is NOT marked fully covered
    assert packet.coverage.is_fully_covered is False

    # Invariant 3: Multi-axis state is degraded / partial
    assert packet.state.completeness == "PARTIAL"
    assert packet.state.availability == "DEGRADED"

    # Invariant 4: Recovery dispatcher prescribes continuing federation
    assert packet.recommended_recovery == "CONTINUE_FEDERATION"


def test_compound_shard_id_formatting_and_parsing():
    """Golden Test 2: Shard IDs must use compound notation shard_id@db_index."""
    ref = CompoundShardRef(shard_id=29230, db_index=6)
    assert ref.compound_id == "29230@db6"

    parsed = CompoundShardRef.from_str("29475@db8")
    assert parsed is not None
    assert parsed.shard_id == 29475
    assert parsed.db_index == 8

    invalid = CompoundShardRef.from_str("naked_shard_123")
    assert invalid is None


def test_epistemic_typing_classification():
    """Golden Test 3: Knowledge shards are typed into distinct epistemic truth classes."""
    # 1. Telemetry / Receipt
    ep_telemetry = infer_epistemic_class("Token pull 2026-09-16", ["telemetry", "receipt"])
    assert ep_telemetry == EpistemicClass.VERIFIED_TELEMETRY

    # 2. User Canon
    ep_canon = infer_epistemic_class("Rhea Noir Lore Bible", ["lore", "canon", "character_vault"])
    assert ep_canon == EpistemicClass.USER_CANON

    # 3. External ArXiv Paper
    ep_arxiv = infer_epistemic_class("arxiv_cs_AI_20260521_RAG", ["arxiv", "research-doc"])
    assert ep_arxiv == EpistemicClass.EXTERNAL_PAPER

    # 4. Stale Fact
    ep_stale = infer_epistemic_class("Old Pricing Sheet", ["stale", "expired"])
    assert ep_stale == EpistemicClass.STALE_FACT


def test_truncation_transparency():
    """Golden Test 5: Top-k truncation is transparently reported in packet."""
    packet = gather_griot_archive(
        query="retrieval",
        max_top_k=2,
    )
    # Total candidates in 9-DB grid for 'retrieval' is high
    assert packet.candidate_total >= packet.returned_count
    if packet.candidate_total > packet.returned_count:
        assert packet.is_truncated is True
        assert packet.returned_count == 2
