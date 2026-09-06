"""Kaedra read-only tool path (war game Move 3)."""
import json

import pytest

from nougen_shards import kaedra_tools as kt


EXPECTED = ["fleet_whoami", "shards_search", "shards_recall",
            "relay_latest", "relay_open", "reach_state"]


def test_tools_schema():
    assert [t["function"]["name"] for t in kt.TOOLS] == EXPECTED
    for t in kt.TOOLS:
        assert t["type"] == "function"
        params = t["function"]["parameters"]
        assert params["type"] == "object"
        assert isinstance(params["properties"], dict)
        assert isinstance(params["required"], list)
        assert "cite only" in t["function"]["description"].lower()
        assert "could not check" in t["function"]["description"].lower()


def test_dispatch_unknown_and_never_raises(monkeypatch):
    assert kt.dispatch("rm_rf", {}) == {"error": "unknown tool"}

    def boom(args):
        raise RuntimeError("backing blew up")
    monkeypatch.setitem(kt._DISPATCH, "fleet_whoami", boom)
    out = kt.dispatch("fleet_whoami", {})
    assert out == {"error": "backing blew up"}


def test_shards_search_only_returns_backing_ids(monkeypatch):
    from nougen_shards import core
    fake = [{"id": 11, "db_index": 0, "title": "a", "score": 0.9, "content": "x"},
            {"id": 22, "db_index": 1, "title": "b", "score": 0.5}]
    monkeypatch.setattr(core, "retrieve", lambda q, limit=3, **kw: fake)
    out = kt.dispatch("shards_search", {"query": "fleet", "limit": 50})
    assert [s["id"] for s in out["shards"]] == [11, 22]
    assert all("content" not in s for s in out["shards"])


def test_shards_recall_binds_get_shard_by_id(monkeypatch):
    from nougen_shards import core
    seen = {}

    def fake_get(shard_id, db_index):
        seen["args"] = (shard_id, db_index)
        return {"id": shard_id, "title": "t", "content": "body"}
    monkeypatch.setattr(core, "get_shard_by_id", fake_get)
    out = kt.dispatch("shards_recall", {"shard_id": "7", "db_index": 2})
    assert seen["args"] == (7, 2)
    assert out["shard"]["id"] == 7
    assert kt.dispatch("shards_recall", {}) == {
        "error": "shard_id and db_index (integers) are required"}


def test_relay_open_filters_closed_legs(monkeypatch):
    from nougen_shards import handoff
    feed = [{"id": "leg-1", "agent": "a", "live_status": "completed", "goal": "g"},
            {"id": "leg-2", "agent": "b", "live_status": "open", "goal": "g"},
            {"id": "leg-3", "agent": "c", "live_status": "in_progress", "goal": "g"}]
    monkeypatch.setattr(handoff, "handoff_feed", lambda agent=None, limit=25: feed)
    latest = kt.dispatch("relay_latest", {"limit": 2})
    assert [l["id"] for l in latest["legs"]] == ["leg-1", "leg-2"]
    opened = kt.dispatch("relay_open", {})
    assert [l["id"] for l in opened["legs"]] == ["leg-2", "leg-3"]


def test_reach_state_unavailable_when_module_missing(monkeypatch):
    import importlib

    real_import = importlib.import_module

    def _no_reach(name, *a, **k):
        if name == "reach_matrix":
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(importlib, "import_module", _no_reach)
    out = kt.dispatch("reach_state", {})
    assert out.get("unavailable") is True
    assert "reason" in out


def test_reach_state_binds_run_without_calling_main(monkeypatch):
    import importlib
    import types

    calls = []
    fake = types.SimpleNamespace(
        load_manifest=lambda: {"m": 1},
        node_token=lambda: None,
        run=lambda manifest, token: calls.append((manifest, token)) or {"ok": True},
        main=lambda *a, **k: (_ for _ in ()).throw(AssertionError("main() must not run")),
    )
    real_import = importlib.import_module
    monkeypatch.setattr(importlib, "import_module",
                        lambda name, *a, **k: fake if name == "reach_matrix" else real_import(name, *a, **k))
    out = kt.dispatch("reach_state", {})
    assert out == {"state": {"ok": True}}
    assert calls == [({"m": 1}, None)]


def _always_calls(name, args=None):
    def chat_fn(model, messages, tools=None):
        assert tools is kt.TOOLS
        return {"message": {"role": "assistant", "content": "",
                            "tool_calls": [{"function": {"name": name,
                                                         "arguments": args or {}}}]}}
    return chat_fn


def test_loop_terminates_at_max_rounds(monkeypatch):
    monkeypatch.setitem(kt._DISPATCH, "fleet_whoami", lambda a: {"host": "x"})
    text, log = kt.run_tool_loop(_always_calls("fleet_whoami"), "m", [], max_rounds=3)
    assert len(log) == 3
    assert all(e["tool"] == "fleet_whoami" and e["ok"] for e in log)
    assert "round limit" in text


def test_loop_reads_rounds_from_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_KAEDRA_TOOL_ROUNDS", "2")
    monkeypatch.setitem(kt._DISPATCH, "fleet_whoami", lambda a: {"host": "x"})
    _, log = kt.run_tool_loop(_always_calls("fleet_whoami"), "m", [])
    assert len(log) == 2


def test_loop_refuses_non_allowlisted_tool():
    calls = {"n": 0}

    def chat_fn(model, messages, tools=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"message": {"role": "assistant", "content": "",
                                "tool_calls": [{"function": {"name": "shards_forget",
                                                             "arguments": {"id": 1}}}]}}
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert json.loads(tool_msgs[-1]["content"]) == {"error": "unknown tool"}
        return {"message": {"role": "assistant", "content": "done"}}

    text, log = kt.run_tool_loop(chat_fn, "m", [{"role": "user", "content": "hi"}])
    assert text == "done"
    assert log == [{"tool": "shards_forget", "args": {"id": 1}, "result_size": 0,
                    "ok": False, "refused": True}]


def test_loop_no_tool_calls_returns_content():
    text, log = kt.run_tool_loop(
        lambda m, msgs, tools=None: {"message": {"content": "plain"}}, "m", [])
    assert text == "plain" and log == []
