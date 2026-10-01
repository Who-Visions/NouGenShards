"""arxiv_lab_watch: read-only preview by default, mutation gated, edge schema honoured."""
import ast
import re
from pathlib import Path

import pytest

from nougen_shards import arxiv_radar

ROOT = Path(__file__).resolve().parent.parent


def _entry(i, score, graft=True, tier="graft"):
    return {"id": f"2610.{i:05d}", "title": f"t{i}", "score": score, "classes": ["c"],
            "tier": tier, "graft": graft}


class FakeLab:
    def __init__(self):
        self.run_calls = []
        self.fetch_cursors = []

    def _radar(self):
        return object()

    def fetch_feed(self, channel, cursor, radar):
        self.fetch_cursors.append(cursor)
        return [_entry(1, 5), _entry(2, 9), _entry(2, 9), _entry(3, 1, graft=False, tier="watch")], {}

    def backfill_recent(self, channel):
        return [_entry(4, 7)]

    def run(self, channel="cs.AR", backfill=False):
        self.run_calls.append((channel, backfill))
        return {"channel": channel, "candidates_added": 1}


@pytest.fixture
def lab(monkeypatch):
    fake = FakeLab()
    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"lab": fake})
    monkeypatch.delenv(arxiv_radar.MUTATION_ENV, raising=False)
    return fake


def test_default_is_read_only_preview(lab):
    res = arxiv_radar.run_arxiv_lab_watch("cs.AR")
    assert res["status"] == "success" and res["mutated"] is False
    assert lab.run_calls == []
    assert lab.fetch_cursors == [{}]          # empty cursor: nothing persisted
    r = res["result"]
    assert r["screened"] == 3                 # duplicate id collapsed
    assert [e["score"] for e in r["graft_top"]] == [9, 5]
    assert r["auto_shard"] is False and res["novelty"] == "unjudged"


def test_limit_clips_and_backfill_included(lab):
    res = arxiv_radar.run_arxiv_lab_watch("cs.AR", backfill=True, limit=1)
    assert [e["id"] for e in res["result"]["graft_top"]] == ["2610.00002"]
    assert res["result"]["graft_candidates"] == 3


def test_commit_refused_without_operator_env(lab):
    res = arxiv_radar.run_arxiv_lab_watch("cs.AR", commit=True)
    assert res["status"] == "mutation_disabled" and res["mutated"] is False
    assert lab.run_calls == []


def test_commit_runs_lab_when_operator_allows(lab, monkeypatch):
    monkeypatch.setenv(arxiv_radar.MUTATION_ENV, "1")
    res = arxiv_radar.run_arxiv_lab_watch("cs.AR", backfill=True, commit=True)
    assert res["status"] == "success" and res["mutated"] is True
    assert lab.run_calls == [("cs.AR", True)]


@pytest.mark.parametrize("kw", [{"channel": "../x"}, {"channel": 5}, {"limit": 0}, {"limit": 51}, {"limit": True}])
def test_bad_arguments_rejected_before_any_fetch(lab, kw):
    res = arxiv_radar.run_arxiv_lab_watch(**{"channel": "cs.AR", **kw})
    assert res["status"] == "error"
    assert lab.fetch_cursors == [] and lab.run_calls == []


def _edge_properties():
    """tool name -> advertised property names, parsed from the edge tool-list JSON."""
    text = (ROOT / "tools" / "nougen-fleet-mcp-patched.js").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'"name":\s*"(arxiv_lab_watch)",.*?"inputSchema":\s*\{\s*"properties":\s*\{(.*?)\n      \},', text, re.S):
        out[m.group(1)] = set(re.findall(r'^        "(\w+)":\s*\{', m.group(2), re.M))
    return out


def _handler_params(path, name):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return {a.arg for a in n.args.args}
    raise AssertionError(f"{name} not in {path}")


def test_handlers_accept_every_property_the_edge_advertises():
    props = _edge_properties().get("arxiv_lab_watch")
    assert props, "edge schema for arxiv_lab_watch not found"
    for path in ("app.py", "src/nougen_shards/mcp.py"):
        missing = props - _handler_params(path, "arxiv_lab_watch")
        assert not missing, f"{path} arxiv_lab_watch ignores advertised {sorted(missing)}"
