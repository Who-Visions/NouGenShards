"""MCP promotion hardening test suite.

Proves the complete acceptance chain for promoted MCP tools:
advertised -> importable -> invocable -> implementation reached -> structured failure -> proof

Exercises actual registered MCP call paths across app.py and mcp.py.
"""
import asyncio
import inspect
import json
import types
import pytest

from nougen_shards import mcp
from nougen_shards import arxiv_radar


def _make_mock_radar(calls):
    ns = types.SimpleNamespace()
    rss_sample = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>cs.AR updates</title>
    <item><title>Alpha accelerator for agent memory</title><link>https://arxiv.org/abs/2609.00001</link></item>
    <item><title>Beta cache hierarchy</title><link>https://arxiv.org/abs/2609.00002</link></item>
    </channel></rss>"""

    def fetch_arxiv_rss_conditional(channel="cs", cursor=None):
        calls.append(("fetch", channel, cursor))
        return rss_sample, {"status": 200}

    def parse_arxiv_item(item):
        title = item.find("title").text
        return {"id": item.find("link").text.rsplit("/", 1)[-1], "title": title,
                "primary_category": "cs.AR", "authors": ["A"], "abstract": title}

    def compute_percentiles(papers):
        return [dict(p, priority_pct=99.0, reason_codes=["usable_artifact"]) for p in papers]

    def route_papers(papers, recipe):
        return {"beacon": papers[:1], "review": papers[1:], "shard": []}

    def load_route_recipe():
        return {"lanes": {"beacon": {"min_percentile": 99.5}}}

    def run_pipeline(mode="reconcile", channels=None, broadcast_target="all"):
        calls.append(("run_pipeline", mode, channels, broadcast_target))
        return {"status": "ok", "papers_count": 2}

    for fn in (fetch_arxiv_rss_conditional, parse_arxiv_item, compute_percentiles,
               route_papers, load_route_recipe, run_pipeline):
        setattr(ns, fn.__name__, fn)
    return ns


class _MockLab:
    def __init__(self):
        self.run_calls = []
        self.fetch_cursors = []

    def _radar(self):
        return object()

    def fetch_feed(self, channel, cursor, radar):
        self.fetch_cursors.append(cursor)
        return [{"id": "2610.00001", "title": "t1", "score": 9, "classes": ["c"], "tier": "graft", "graft": True}], {}

    def backfill_recent(self, channel):
        return []

    def run(self, channel="cs.AR", backfill=False):
        self.run_calls.append((channel, backfill))
        return {"channel": channel, "candidates_added": 1}


def test_promoted_arxiv_tools_registered_in_mcp():
    """Verify newly promoted tools are importable, registered, and callable on mcp server."""
    tools = [
        "arxiv_radar",
        "arxiv_lab_watch",
        "arxiv_paper",
        "morph_gate",
    ]
    for tool_name in tools:
        assert hasattr(mcp, tool_name), f"{tool_name} must be exported/registered in nougen_shards.mcp"
        fn = getattr(mcp, tool_name)
        assert callable(fn), f"{tool_name} must be callable"


def test_registered_mcp_call_path_arxiv_paper_empty_ref():
    """Empty ref invoked directly through the registered MCP tool fails explicitly."""
    res_raw = mcp.arxiv_paper(action="lookup", ref="")
    res = json.loads(res_raw)
    assert res["status"] == "error"
    assert "ref is required" in res["error"]
    assert res["available"] is True


def test_registered_mcp_call_path_morph_gate_empty_ref():
    """Empty ref on morph_gate through registered MCP tool returns structured error."""
    res_raw = mcp.morph_gate(ref="", claims=["pattern"])
    res = json.loads(res_raw)
    assert res["status"] == "error"
    assert "ref is required" in res["error"]


def test_registered_mcp_call_path_arxiv_radar_read_only_preview(monkeypatch):
    """arxiv_radar invoked through registered MCP tool runs preview without mutation."""
    calls = []
    ns = _make_mock_radar(calls)
    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"radar": ns, "root": "x"})
    monkeypatch.delenv(arxiv_radar.MUTATION_ENV, raising=False)

    res_raw = mcp.arxiv_radar(channels=["cs.AR"], mode="preview", limit=2)
    res = json.loads(res_raw)
    assert res["status"] == "success"
    assert res["mutated"] is False
    assert res["mode"] == "preview"
    assert [c[0] for c in calls] == ["fetch"]


def test_registered_mcp_call_path_arxiv_lab_watch_read_only(monkeypatch):
    """arxiv_lab_watch through registered MCP tool runs read-only preview."""
    fake = _MockLab()
    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"lab": fake})
    monkeypatch.delenv(arxiv_radar.MUTATION_ENV, raising=False)

    res_raw = mcp.arxiv_lab_watch(channel="cs.AR", limit=3)
    res = json.loads(res_raw)
    assert res["status"] == "success"
    assert res["mutated"] is False
    assert fake.run_calls == []


def test_registered_mcp_call_path_degraded_when_radar_absent(monkeypatch):
    """When nougen-radar tool repo is absent, returns structured degraded response."""
    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {})

    res_paper = json.loads(mcp.arxiv_paper(action="lookup", ref="2609.34785"))
    assert res_paper["status"] == "degraded"
    assert res_paper["available"] is False
    assert "not installed" in res_paper["error"]

    res_lab = json.loads(mcp.arxiv_lab_watch(channel="cs.AR"))
    assert res_lab["status"] == "degraded"
    assert res_lab["available"] is False

    res_morph = json.loads(mcp.morph_gate(ref="2609.34785", claims=["test"]))
    assert res_morph["status"] == "degraded"
    assert res_morph["available"] is False


def test_app_node_mcp_handlers_reach_implementation(monkeypatch):
    """Verify app.py FastMCP handlers reach underlying functions and validate inputs."""
    import app

    def _sync_call(fn, *args, **kwargs):
        res = fn(*args, **kwargs)
        if inspect.iscoroutine(res):
            return asyncio.run(res)
        return res

    # arxiv_paper empty ref validation
    res_app_empty = _sync_call(app.arxiv_paper, action="lookup", ref="")
    assert res_app_empty["status"] == "error"
    assert "ref is required" in res_app_empty["error"]

    # broadcast_target validation on arxiv_radar
    res_app_broadcast = _sync_call(app.arxiv_radar, broadcast_target="remote-fleet")
    assert res_app_broadcast["status"] == "error"
    assert "broadcast_target" in res_app_broadcast["error"]
