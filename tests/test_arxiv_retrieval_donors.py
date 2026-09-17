"""Tests for ArXiv 0.01% Retrieval Donors & Cascade Engine.

Verifies donor method registry, late interaction MaxSim, deterministic RRF fusion,
and end-to-end evidence-locked cascade execution.
"""

import hashlib

from nougen_shards.arxiv_retrieval_donors import (
    CANONICAL_DONORS,
    ArxivCascadeRetriever,
    DonorCategory,
)


def test_canonical_donors_matrix():
    assert len(CANONICAL_DONORS) >= 5
    categories = {d.primary_category for d in CANONICAL_DONORS}
    assert DonorCategory.LATE_INTERACTION in categories
    assert DonorCategory.SUBGRAPH_EXTRACTION in categories
    assert DonorCategory.PROVENANCE_LOCK in categories
    for d in CANONICAL_DONORS:
        assert d.arxiv_id
        assert d.evidence
        assert d.integration_status
        assert d.limitation
    agent_zero = next(d for d in CANONICAL_DONORS if d.arxiv_id == "2608.29606")
    assert "Provenance-Aware Long-Term Memory" in agent_zero.title
    assert "DESIGN_ONLY" in {
        d.integration_status for d in CANONICAL_DONORS if d.arxiv_id == "2112.01488"
    }


def test_sparse_candidate_lanes_use_exact_tokens_not_substrings():
    retriever = ArxivCascadeRetriever()
    corpus = {"d1": {"content": "concatenate strings safely"}}
    result = retriever.execute_cascade("cat retrieval", corpus)
    assert result.abstention_reason == "ZERO_CANDIDATES_ACROSS_ALL_LANES"


def test_deterministic_rrf():
    retriever = ArxivCascadeRetriever()
    rank_lists = {
        "lexical": ["doc_A", "doc_B", "doc_C"],
        "sparse": ["doc_B", "doc_A", "doc_D"],
        "graph": ["doc_A", "doc_B", "doc_E"]
    }
    fused = retriever.reciprocal_rank_fusion(rank_lists, k=60)
    assert len(fused) == 5
    # doc_A and doc_B are in all 3 lists, should top the rankings
    top_docs = [x[0] for x in fused[:2]]
    assert "doc_A" in top_docs
    assert "doc_B" in top_docs
    assert all(score > 0 for _, score in fused)
    assert fused == retriever.reciprocal_rank_fusion(dict(reversed(list(rank_lists.items()))), k=60)
    assert retriever.reciprocal_rank_fusion({"lane": ["doc_A", "doc_A"]}) == [
        ("doc_A", 1 / 61)
    ]


def test_end_to_end_cascade_execution():
    retriever = ArxivCascadeRetriever()
    corpus = {
        "doc_1": {
            "content": "ColBERTv2 uses token-level late interaction and residual compression.",
            "entities": ["ColBERTv2", "compression"]
        },
        "doc_2": {
            "content": "G-Retriever performs prize-collecting Steiner tree subgraph extraction on textual graphs.",
            "entities": ["G-Retriever", "graph"]
        },
        "doc_3": {
            "content": "Standard SQLite table creation and relational queries.",
            "entities": ["SQLite"]
        }
    }

    # Query 1: Graph extraction
    res_graph = retriever.execute_cascade("G-Retriever graph extraction", corpus)
    assert res_graph.abstention_reason is None
    assert "doc_2" in res_graph.grounded_evidence_ids
    assert len(res_graph.query_receipt_sha) == 64

    # Query 2: Unmatched query -> abstention
    res_unmatched = retriever.execute_cascade("quantum teleportation astrophysics", corpus)
    assert res_unmatched.abstention_reason == "ZERO_CANDIDATES_ACROSS_ALL_LANES"
    assert len(res_unmatched.grounded_evidence_ids) == 0

    # Query 3: Fast path shortcut
    res_fast = retriever.execute_cascade(
        "direct fast query",
        corpus,
        fast_path_hit={
            "artifact_id": "fast_001",
            "content": "Instant result",
            "opened": True,
            "provenance_sha": hashlib.sha256(b"Instant result").hexdigest(),
        },
    )
    assert res_fast.grounded_evidence_ids == ["fast_001"]
    assert "Instant result" in res_fast.primary_answer
    assert res_fast.evidence_hashes == {"fast_001": hashlib.sha256(b"Instant result").hexdigest()}
    changed = retriever.execute_cascade(
        "direct fast query",
        corpus,
        fast_path_hit={
            "artifact_id": "fast_001",
            "content": "Changed result",
            "opened": True,
            "provenance_sha": hashlib.sha256(b"Changed result").hexdigest(),
        },
    )
    assert changed.query_receipt_sha != res_fast.query_receipt_sha


def test_unopened_or_hash_mismatched_fast_path_cannot_bypass_retrieval():
    retriever = ArxivCascadeRetriever()
    corpus = {"doc": {"content": "ordinary indexed text"}}
    unopened = retriever.execute_cascade(
        "unmatched phrase", corpus,
        fast_path_hit={"artifact_id": "fast", "content": "fabricated", "opened": False},
    )
    mismatched = retriever.execute_cascade(
        "unmatched phrase", corpus,
        fast_path_hit={"artifact_id": "fast", "content": "fabricated", "opened": True,
                       "provenance_sha": "0" * 64},
    )
    assert unopened.abstention_reason == "ZERO_CANDIDATES_ACROSS_ALL_LANES"
    assert mismatched.abstention_reason == "ZERO_CANDIDATES_ACROSS_ALL_LANES"


def test_weak_and_ambiguous_matches_abstain():
    retriever = ArxivCascadeRetriever()
    weak = retriever.execute_cascade("ordinary rareterm", {
        "doc": {"content": "ordinary content with unrelated detail"}
    })
    ambiguous = retriever.execute_cascade("shared phrase", {
        "a": {"content": "shared phrase in alpha"},
        "b": {"content": "shared phrase in beta"},
    })
    assert weak.abstention_reason == "LOW_EVIDENCE_OVERLAP"
    assert ambiguous.abstention_reason == "AMBIGUOUS_TOP_EVIDENCE"
