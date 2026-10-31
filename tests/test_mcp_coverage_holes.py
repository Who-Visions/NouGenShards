"""The Hetty test: with one vault offline, recall tools must say the answer is partial.

federated_retrieve already records errored lanes; these tests pin that the MCP
tools agents actually call pass that hole through instead of returning an
answer that looks complete.
"""
import json

from nougen_shards import federation, mcp
from nougen_shards.federation import FederatedResult

_FAILURE = {"store": "lane:whoart", "error": "HTTP 530 gateway offline"}


def _fake_federated(rows):
    def fake(query, limit=3, sweep_report=None, **_kw):
        if sweep_report is not None:
            sweep_report.setdefault("errored", []).append(dict(_FAILURE))
        return FederatedResult(rows, lane_failures=[dict(_FAILURE)])
    return fake


def test_recall_with_offline_lane_and_no_hits_is_incomplete_not_empty(monkeypatch):
    monkeypatch.setattr(mcp, "federated_retrieve", _fake_federated([]))
    out = mcp.recall_memory("hetty mirror shard")
    assert out.startswith("Recall INCOMPLETE")
    assert "lane:whoart" in out
    assert "No relevant shards found" not in out


def test_recall_with_offline_lane_and_hits_carries_coverage_warning(monkeypatch):
    rows = [{"id": 1, "title": "mirror", "content": "fragment A at Woodstone", "event_type": "note"}]
    monkeypatch.setattr(mcp, "federated_retrieve", _fake_federated(rows))
    out = mcp.recall_memory("mirror")
    assert "[COVERAGE WARNING] Partial result" in out
    assert "lane:whoart" in out


def test_search_shards_reports_incomplete_coverage(monkeypatch):
    # search_shards imports federated_retrieve at call time, from federation.
    monkeypatch.setattr(federation, "federated_retrieve", _fake_federated([]))
    out = json.loads(mcp.search_shards("mirror"))
    assert out["coverage"]["complete"] is False
    assert out["coverage"]["lane_failures"][0]["store"] == "lane:whoart"


def test_search_shards_clean_sweep_reports_complete(monkeypatch):
    monkeypatch.setattr(federation, "federated_retrieve",
                        lambda query, limit=3, **_kw: FederatedResult([], lane_failures=[]))
    out = json.loads(mcp.search_shards("mirror"))
    assert out["coverage"] == {"complete": True, "lane_failures": []}
