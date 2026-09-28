"""
Unit tests for distill_elevated module.
"""
from nougen_shards.distill_elevated import compute_distillation_metrics, DistillationMetrics

def test_distillation_metrics():
    raw_text = "This is a detailed raw shard containing architectural decisions and fleet coordination rules." * 5
    atoms = [{"type": "constraint", "text": "Never fake acks"}, {"type": "fact", "text": "Apollo mesh runs on port 8765"}]
    entities = [{"name": "Apollo Mesh", "kind": "service"}]
    relations = [{"src": "Apollo Mesh", "rel": "runs_on", "dst": "Port 8765"}]

    metrics = compute_distillation_metrics(raw_text, atoms, entities, relations)
    assert isinstance(metrics, DistillationMetrics)
    assert 0.0 <= metrics.compression_ratio <= 1.0
    assert metrics.knowledge_density > 0.0
    assert metrics.atom_count == 2
