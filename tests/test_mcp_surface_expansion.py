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


def test_mcp_six_tool_sequence_isolated(monkeypatch, tmp_path):
    """Deterministic, isolated end-to-end six-tool MCP test sequence for PR #571/#576."""
    from nougen_shards import lane_claim

    # 1. search_shards isolated with stubbed federation
    monkeypatch.setattr(
        "nougen_shards.federation.federated_retrieve",
        lambda query, limit=5: [{"id": 42, "title": "Synth Shard", "content": "Synthetic data"}],
    )
    res_search = json.loads(mcp.search_shards("synthetic query", limit=1))
    assert res_search["query"] == "synthetic query"
    assert res_search["count"] == 1
    assert res_search["shards"][0]["id"] == 42

    # 2. add_shard with realistic dict result
    captured_inputs = {}
    def mock_capture(**kwargs):
        captured_inputs.update(kwargs)
        return {"status": "captured", "shard_id": 999, "success": True}

    monkeypatch.setattr("nougen_shards.core.capture", mock_capture)
    res_add = json.loads(mcp.add_shard("Insight content", title="Custom Title", tags=["test", "isolated"]))
    assert res_add["status"] == "ok"
    assert res_add["title"] == "Custom Title"
    assert captured_inputs["title"] == "Custom Title"
    assert captured_inputs["content"] == "Insight content"
    assert captured_inputs["tags"] == ["test", "isolated"]

    # 3. relay_open with 2 legs and limit=1
    mock_relay = {
        "armed": True,
        "count": 2,
        "legs": [{"id": "leg-alpha", "goal": "task A"}, {"id": "leg-beta", "goal": "task B"}],
    }
    monkeypatch.setattr("nougen_shards.session_probe.read_relay", lambda: mock_relay)
    res_relay = json.loads(mcp.relay_open(limit=1))
    assert res_relay["total_open"] == 2
    assert len(res_relay["legs"]) == 1
    assert res_relay["legs"][0]["id"] == "leg-alpha"

    # 4. claim_lane redirected to tmp_path claims directory
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(lane_claim, "CLAIMS_DIR", claims_dir)
    monkeypatch.setattr(lane_claim, "AGENT", "synthetic_agent")
    monkeypatch.setattr(lane_claim, "MACHINE", "synthetic_box")
    # The node env vars outrank MACHINE; a fleet machine sets them.
    monkeypatch.delenv("NOUGEN_NODE", raising=False)
    monkeypatch.delenv("NOUGEN_MACHINE", raising=False)
    monkeypatch.setattr(lane_claim, "replicate_to_nougen_shards", lambda claim: True)
    monkeypatch.setattr(lane_claim, "dispatch_lane_wake", lambda claim, cmd=None: True)

    res_claim = json.loads(mcp.claim_lane(scope=["src/synthetic.py"], goal="isolated sequence test"))
    assert res_claim["status"] == "claimed"
    assert res_claim["claim"]["agent"] == "synthetic_agent"
    assert res_claim["claim"]["machine"] == "synthetic_box"
    assert "src/synthetic.py" in res_claim["claim"]["scope"]
    assert len(lane_claim.active_claims(claims_dir=claims_dir)) == 1

    # 5. session_bye with dry_run=True (produces no handoff/shard)
    bye_called = {}
    mock_report = MagicMock()
    mock_report.__dict__ = {"summary": "Dry run complete", "dry_run": True, "total_dirty": 0}
    def mock_run_bye(**kwargs):
        bye_called.update(kwargs)
        return mock_report

    monkeypatch.setattr("nougen_shards.session_probe.run_bye", mock_run_bye)
    res_bye = json.loads(mcp.session_bye(summary="Closing test session", dry_run=True))
    assert res_bye["dry_run"] is True
    assert bye_called.get("dry_run") is True

    # 6. release_lane
    res_release = json.loads(mcp.release_lane())
    assert res_release["released"] is True
    assert len(lane_claim.active_claims(claims_dir=claims_dir)) == 0

