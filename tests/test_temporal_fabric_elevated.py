"""
Unit tests for temporal_fabric_elevated module.
"""
from nougen_shards.temporal_fabric_elevated import VectorClock, compute_causal_matrix

def test_vector_clock_causality():
    v1 = VectorClock({"node_a": 1, "node_b": 0})
    v2 = v1.increment("node_a")  # {"node_a": 2, "node_b": 0}
    v3 = v1.increment("node_b")  # {"node_a": 1, "node_b": 1}

    assert v1.compare(v2) == "definitely_before"
    assert v2.compare(v1) == "definitely_after"
    assert v2.compare(v3) == "concurrent"  # (2,0) vs (1,1) is concurrent

def test_vector_clock_merge():
    v1 = VectorClock({"node_a": 2, "node_b": 1})
    v2 = VectorClock({"node_a": 1, "node_b": 3, "node_c": 1})
    merged = v1.merge(v2)
    assert merged.clock_vector == {"node_a": 2, "node_b": 3, "node_c": 1}

def test_causal_matrix():
    v1 = VectorClock({"node_a": 1})
    v2 = v1.increment("node_a")
    matrix = compute_causal_matrix({"e1": v1, "e2": v2})
    assert matrix[("e1", "e2")] == "definitely_before"
    assert matrix[("e2", "e1")] == "definitely_after"
