"""Tests for ArXiv 0.01% Retrieval Donors & Cascade Engine.

Verifies donor method registry, late interaction MaxSim, deterministic RRF fusion,
and end-to-end evidence-locked cascade execution.
"""

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
    assert DonorCategory.TRIPLE_STORE_ARCHITECTURE in categories
    for d in CANONICAL_DONORS:
        assert 0 <= d.applicability_bps <= 10000
        assert len(d.failure_modes) > 0
        assert len(d.deterministic_controls) > 0


def test_late_interaction_maxsim():
    retriever = ArxivCascadeRetriever()
    q_tokens = ["neural", "manifold"]
    doc_match = ["neural", "manifold", "geometry", "expansion"]
    doc_mismatch = ["unrelated", "database", "index"]

    score_match = retriever.late_interaction_maxsim(q_tokens, doc_match)
    score_mismatch = retriever.late_interaction_maxsim(q_tokens, doc_mismatch)

    assert score_match > 8000
    assert score_mismatch < 2000
    assert score_match > score_mismatch


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
    # Scores must be strictly between 0 and 10000
    for doc_id, score in fused:
        assert 0 <= score <= 10000


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
        fast_path_hit={"artifact_id": "fast_001", "content": "Instant result"}
    )
    assert res_fast.grounded_evidence_ids == ["fast_001"]
    assert "Instant result" in res_fast.primary_answer
