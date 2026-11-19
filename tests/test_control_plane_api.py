import json

import pytest

from nougen_shards.control_plane_api import (
    OBJECTIVES,
    adherence_evaluate,
    context_select,
    pareto_route,
)


def test_context_adapter_uses_bounded_graph_packet_and_provenance():
    nodes = [{"id": 1, "title": "Alpha report", "content": "alpha finding", "importance": 0.8}]
    result = context_select("alpha report", 2000, json.dumps(nodes))
    assert result["metrics"]["roots"] == 1
    assert result["metrics"]["query_coverage"] == 1
    assert result["provenance_chain"][0]["content_hash"].startswith("sha256:")
    assert len(result["replay_hash"]) == 64


def test_context_adapter_rejects_bad_or_unbounded_inputs():
    with pytest.raises(ValueError, match="1000 candidate nodes"):
        context_select("alpha", 100, json.dumps([{"id": i} for i in range(1001)]))
    with pytest.raises(ValueError, match="non-empty"):
        context_select(" ", 100, "[]")


def test_pareto_adapter_requires_complete_task_weights_and_returns_provenance():
    rows = [
        {"id": "fast", "quality": .7, "truth": .9, "latency_ms": 5, "cost_usd": .1,
         "robustness": .8, "memory_fidelity": .9, "safety_score": .9},
        {"id": "accurate", "quality": .95, "truth": .99, "latency_ms": 100, "cost_usd": 1,
         "robustness": .9, "memory_fidelity": .95, "safety_score": .99},
    ]
    weights = {name: 0.0 for name in OBJECTIVES}
    weights["quality"] = 1.0
    result = pareto_route(json.dumps(rows), json.dumps(weights))
    assert result["chosen"] == "accurate"
    assert set(result["front"]) == {"fast", "accurate"}
    assert len(result["provenance"]["policy_digest"]) == 64
    with pytest.raises(ValueError, match="exactly these objectives"):
        pareto_route(json.dumps(rows), json.dumps({"quality": 1}))


def test_pareto_adapter_rejects_duplicate_ids_and_missing_objectives():
    incomplete = [{"id": "route-a", "quality": .9}]
    weights = {name: 1.0 for name in OBJECTIVES}
    with pytest.raises(ValueError, match="missing finite objective"):
        pareto_route(json.dumps(incomplete), json.dumps(weights))


def test_adherence_adapter_distinguishes_coverage_undeclared_and_unmeasured():
    result = adherence_evaluate(
        json.dumps([["plan", "build"], ["build", "test"]]),
        json.dumps([["plan", "build"], ["build", "deploy"]]),
        threshold=.75,
    )
    assert result["coverage"] == .5
    assert result["undeclared"] == .5
    assert result["status"] == "below_threshold"
    assert result["missing_edges"] == [("build", "test")]
    assert result["undeclared_edges"] == [("build", "deploy")]
    empty = adherence_evaluate("[]", "[]")
    assert empty["status"] == "unmeasured"
    assert empty["coverage"] is None and empty["undeclared"] is None


def test_adherence_adapter_validates_edges_and_threshold():
    with pytest.raises(ValueError, match="string pair"):
        adherence_evaluate('[{"from":"a","to":"b"}]', "[]")
    with pytest.raises(ValueError, match="between 0 and 1"):
        adherence_evaluate("[]", "[]", threshold=1.1)
