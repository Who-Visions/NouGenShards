"""
Unit tests for core_elevated module.
"""
from nougen_shards.core_elevated import (
    RelevanceTensor,
    compute_cosine_similarity,
    compute_routing_distribution
)

def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]

    assert compute_cosine_similarity(v1, v2) == 1.0
    assert compute_cosine_similarity(v1, v3) == 0.0

def test_relevance_tensor():
    rt = RelevanceTensor(bm25_score=0.8, cosine_similarity=0.9, utility_score=50.0)
    score = rt.blended_score()
    assert 0.0 <= score <= 1.0
    assert score > 0.70

def test_routing_distribution():
    hashes = ["a" * 32, "b" * 32, "c" * 32, "d" * 32]
    dist = compute_routing_distribution(hashes)
    assert len(dist) == 9
    assert sum(dist.values()) == 4
