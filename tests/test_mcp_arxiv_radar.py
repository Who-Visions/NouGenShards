"""Tests for arXiv research radar and lab watcher FastMCP tools."""

import json
from unittest.mock import MagicMock

from nougen_shards import mcp


def test_mcp_arxiv_radar_success(monkeypatch):
    mock_run = MagicMock(return_value={
        "status": "success",
        "available": True,
        "mode": "sweep",
        "result": {"status": "noop", "papers_count": 0},
    })
    monkeypatch.setattr("nougen_shards.arxiv_radar.run_arxiv_radar", mock_run)
    res = json.loads(mcp.arxiv_radar(mode="sweep"))
    assert res["status"] == "success"
    assert res["available"] is True
    assert res["mode"] == "sweep"
    assert res["result"]["status"] == "noop"


def test_mcp_arxiv_radar_degraded(monkeypatch):
    mock_run = MagicMock(return_value={
        "status": "degraded",
        "available": False,
        "error": "nougen-radar repository not installed or arxiv_rss_radar.py missing",
    })
    monkeypatch.setattr("nougen_shards.arxiv_radar.run_arxiv_radar", mock_run)
    res = json.loads(mcp.arxiv_radar())
    assert res["status"] == "degraded"
    assert res["available"] is False
    assert "error" in res


def test_mcp_arxiv_lab_watch_success(monkeypatch):
    mock_run = MagicMock(return_value={
        "status": "success",
        "available": True,
        "channel": "cs.AR",
        "result": {"channel": "cs.AR", "screened": 10, "candidates_added": 2},
        "novelty": "unjudged",
    })
    monkeypatch.setattr("nougen_shards.arxiv_radar.run_arxiv_lab_watch", mock_run)
    res = json.loads(mcp.arxiv_lab_watch(channel="cs.AR"))
    assert res["status"] == "success"
    assert res["novelty"] == "unjudged"
    assert res["result"]["candidates_added"] == 2


def test_mcp_arxiv_paper_lookup_and_claim(monkeypatch):
    mock_paper = MagicMock(return_value={
        "status": "success",
        "available": True,
        "action": "lookup",
        "paper_id": "2609.34785",
        "metadata": {"title": "Test Paper", "authors": ["Author One"]},
    })
    monkeypatch.setattr("nougen_shards.arxiv_radar.run_arxiv_paper", mock_paper)
    res = json.loads(mcp.arxiv_paper(action="lookup", ref="2609.34785"))
    assert res["status"] == "success"
    assert res["paper_id"] == "2609.34785"
    assert res["metadata"]["title"] == "Test Paper"


def test_mcp_morph_gate_success(monkeypatch):
    mock_gate = MagicMock(return_value={
        "status": "success",
        "available": True,
        "evidence": {
            "source": "arXiv:2609.34785",
            "confidence": 1.0,
            "evidence_type": "paper_body",
            "found": ["55.0%"],
            "missing": [],
        }
    })
    monkeypatch.setattr("nougen_shards.arxiv_radar.run_morph_gate", mock_gate)
    res = json.loads(mcp.morph_gate(ref="2609.34785", claims=["55.0%"]))
    assert res["status"] == "success"
    assert res["evidence"]["evidence_type"] == "paper_body"
    assert res["evidence"]["confidence"] == 1.0


import pytest


def test_arxiv_radar_integration_direct():
    """Verify live integration directly resolves against Outpost/nougen-radar when available."""
    from nougen_shards.arxiv_radar import find_radar_root, get_radar_tools
    root = find_radar_root()
    if root is None:
        pytest.skip("nougen-radar repository not installed in environment (expected in CI runner)")
    tools = get_radar_tools()
    assert tools is not None
    assert tools["radar"] is not None
    assert tools["lab"] is not None
    assert tools["paper"] is not None
    assert tools["morph"] is not None

