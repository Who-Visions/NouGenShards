"""Tests for expanded FastMCP tool surface (relay leg 20260925T210536Z)."""

import json
from unittest.mock import MagicMock

from nougen_shards import mcp


def test_mcp_search_shards(monkeypatch):
    monkeypatch.setattr("nougen_shards.federation.federated_retrieve", lambda query, limit=5: [{"id": 1, "title": "Test Shard", "content": "Sample content"}])
    res = json.loads(mcp.search_shards("test query", limit=3))
    assert res["query"] == "test query"
    assert res["count"] == 1
    assert res["shards"][0]["id"] == 1


def test_mcp_add_shard(monkeypatch):
    monkeypatch.setattr("nougen_shards.core.capture", lambda **kwargs: True)
    res = json.loads(mcp.add_shard("Important insight from voice", title="Voice Insight", tags=["voice", "test"]))
    assert res["status"] == "ok"
    assert res["title"] == "Voice Insight"


def test_mcp_session_bye(monkeypatch):
    mock_report = MagicMock()
    mock_report.__dict__ = {"summary": "Session closed cleanly", "total_dirty": 0}
    monkeypatch.setattr("nougen_shards.session_probe.run_bye", lambda **kwargs: mock_report)
    res = json.loads(mcp.session_bye(summary="Work done"))
    assert res["summary"] == "Session closed cleanly"
    assert res["total_dirty"] == 0


def test_mcp_relay_open(monkeypatch):
    mock_relay = {
        "armed": True,
        "count": 2,
        "legs": [{"id": "leg-1", "goal": "task 1"}, {"id": "leg-2", "goal": "task 2"}]
    }
    monkeypatch.setattr("nougen_shards.session_probe.read_relay", lambda: mock_relay)
    res = json.loads(mcp.relay_open(limit=1))
    assert res["armed"] is True
    assert res["total_open"] == 2
    assert len(res["legs"]) == 1
    assert res["legs"][0]["id"] == "leg-1"
