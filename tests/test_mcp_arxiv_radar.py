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



# --- regression: wrapper must call the radar's REAL API (run_pipeline), not run_radar_cycle ---

_RSS = b"<rss><channel><item><id>2609.00001</id></item><item><id>2609.00002</id></item></channel></rss>"


def _fake_radar(calls):
    """Mirror of arxiv_rss_radar's public surface. Deliberately has NO run_radar_cycle."""
    from types import SimpleNamespace

    def fetch(channel, cursor):
        calls.append(("fetch", channel, dict(cursor)))
        return _RSS, {}

    def parse(item):
        return {"id": item.findtext("id"), "title": "t-" + item.findtext("id"), "secret_internal": 1}

    def pipeline(mode, channels, broadcast_target):
        calls.append(("run_pipeline", mode, tuple(channels), broadcast_target))
        return {"status": "ran"}

    return SimpleNamespace(
        fetch_arxiv_rss_conditional=fetch,
        parse_arxiv_item=parse,
        compute_percentiles=lambda papers: papers,
        route_papers=lambda papers, recipe: {"beacon": papers[:1], "review": papers[1:], "shard": []},
        load_route_recipe=lambda: {},
        run_pipeline=pipeline,
    )


def test_radar_preview_uses_real_api_and_stays_read_only(monkeypatch):
    from nougen_shards import arxiv_radar

    calls = []
    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"radar": _fake_radar(calls)})
    res = arxiv_radar.run_arxiv_radar(mode="preview", channels=["cs.AR"], limit=1)
    assert res["status"] == "success" and res["mutation"] is False
    assert res["counts"] == {"beacon": 1, "review": 1, "shard": 0, "total": 2}
    assert len(res["lanes"]["beacon"]) == 1
    assert "secret_internal" not in res["lanes"]["beacon"][0]
    assert not [c for c in calls if c[0] == "run_pipeline"]
    # preview must fetch with an EMPTY cursor so scheduler ETag state is never read or written
    assert calls[0] == ("fetch", "cs.AR", {"channels": {}, "seen_ids": []})


def test_radar_commit_is_gated_by_operator_env(monkeypatch):
    from nougen_shards import arxiv_radar

    calls = []
    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"radar": _fake_radar(calls)})
    monkeypatch.delenv("NOUGEN_ARXIV_MCP_ALLOW_MUTATION", raising=False)
    res = arxiv_radar.run_arxiv_radar(mode="sweep", commit=True)
    assert res["status"] == "mutation_disabled" and res["mutation"] is False
    assert not calls

    monkeypatch.setenv("NOUGEN_ARXIV_MCP_ALLOW_MUTATION", "1")
    res = arxiv_radar.run_arxiv_radar(mode="preview", channels=["cs"], commit=True, broadcast_target="all")
    assert res["status"] == "committed" and res["mutation"] is True
    assert calls == [("run_pipeline", "reconcile", ("cs",), "all")]


def test_radar_rejects_unknown_mode(monkeypatch):
    from nougen_shards import arxiv_radar

    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"radar": _fake_radar([])})
    assert arxiv_radar.run_arxiv_radar(mode="nope")["status"] == "error"
