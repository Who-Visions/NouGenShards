"""
Unit tests for graph_elevated module.
"""
from nougen_shards.graph_elevated import compute_pagerank, compute_graph_density

def test_pagerank_computation():
    edges = [("node_a", "node_b"), ("node_b", "node_c"), ("node_c", "node_a")]
    pr = compute_pagerank(edges)
    assert len(pr) == 3
    assert all(0.0 <= score <= 1.0 for score in pr.values())
    assert abs(sum(pr.values()) - 1.0) < 0.05

def test_graph_density():
    density = compute_graph_density(node_count=4, edge_count=6, directed=True)
    assert 0.0 <= density <= 1.0
    assert density == 0.5  # 6 / (4 * 3) = 0.5
