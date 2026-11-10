"""recall_hook: budgeted, host-facing recall (wargame muse-review-elevations E1/E11).

Invariants:
- never raises, never blocks far past the budget;
- an unfinished sweep is labelled partial, never reported as "no matching shards";
- a captured shard comes back by ref with the mark contract attached;
- the Claude Code adapter emits a UserPromptSubmit hookSpecificOutput envelope.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nougen_shards import core, recall_hook  # noqa: E402


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "0")       # no live node in tests unless a test opts in
    # core resolves GLOBAL_DIR from NOUGEN_VAULT_DIR at import, which happened
    # before this fixture ran; repoint the live global as other suites do.
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")            # no Ollama in CI
    monkeypatch.setenv("NOUGEN_EMBED_CAPTURE_TIMEOUT_S", "0.2")
    monkeypatch.setenv("NOUGEN_RECON_SWEEP_TRIGGER", "never")
    return tmp_path


def test_empty_vault_never_raises(vault):
    from nougen_shards import snapshot_mode
    assert core.get_db_path(4).parent == vault, (core.get_db_path(4), snapshot_mode.enabled(), snapshot_mode.root())
    r = recall_hook.recall_hook("anything at all about bridges", budget_ms=3000)
    assert r["shards"] == []
    assert r["tier"] in ("full", "keyword", "none")
    assert "mark" in r and "worked" in r["mark"]
    assert r["elapsed_ms"] < 10_000


def test_short_message_is_refused_cheaply(vault):
    r = recall_hook.recall_hook("hi")
    assert r["tier"] == "none" and r["reason"] == "message too short"
    assert "too short" in recall_hook.format_block(r)


def test_captured_shard_comes_back_with_mark_contract(vault):
    res = core.capture("test", "Bridge token rotation",
                       "The bridge token rotates every Tuesday at noon and the old one is revoked.")
    assert res.get("captured", True) is not False
    r = recall_hook.recall_hook("when does the bridge token rotate", budget_ms=5000)
    refs = [s["ref"] for s in r["shards"]]
    assert refs, r
    assert any(ref.endswith(f"@db{res.get('db_index')}") for ref in refs), (refs, res)
    block = recall_hook.format_block(r)
    assert refs[0] in block
    assert "nougen mark <id> --db <db> --worked" in block


def test_budget_is_honoured_and_partial_is_labelled(vault, monkeypatch):
    import time

    def slow_retrieve(*_a, **_k):
        time.sleep(2.0)
        return []

    def slow_keyword(*_a, **_k):
        time.sleep(2.0)
        return []

    monkeypatch.setattr(core, "retrieve", slow_retrieve)
    monkeypatch.setattr(core, "_keyword_retrieve", slow_keyword)
    r = recall_hook.recall_hook("a query that will time out", budget_ms=100)
    assert r["elapsed_ms"] < 1500
    assert r["tier"] == "none" and r["partial"] is True
    block = recall_hook.format_block(r)
    assert "did not finish" in block
    assert "no matching shards" not in block


def test_keyword_lane_wins_when_vector_lane_is_slow(vault, monkeypatch):
    import time

    def slow_retrieve(*_a, **_k):
        time.sleep(2.0)
        return []

    monkeypatch.setattr(core, "retrieve", slow_retrieve)
    monkeypatch.setattr(core, "_keyword_retrieve",
                        lambda *a, **k: [{"id": 7, "_db_index": 3, "title": "kw hit", "content": "body"}])
    r = recall_hook.recall_hook("keyword only please", budget_ms=300)
    assert r["tier"] == "keyword" and r["partial"] is True
    assert r["shards"][0]["ref"] == "7@db3"


def test_node_lane_wins_when_it_answers(vault, monkeypatch):
    import time
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")
    monkeypatch.setattr(recall_hook, "_node_search",
                        lambda q, limit, timeout_s, token=None: [{"id": 11, "_db_index": 2, "title": "node hit", "content": "warm"}])

    def slow_retrieve(*_a, **_k):
        time.sleep(2.0)
        return []

    monkeypatch.setattr(core, "retrieve", slow_retrieve)
    r = recall_hook.recall_hook("warm index please", budget_ms=500)
    assert r["tier"] == "node" and r["partial"] is False
    assert r["shards"][0]["ref"] == "11@db2"
    assert r["elapsed_ms"] < 500


def test_node_down_falls_through_to_in_process_lanes(vault, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "1")

    def refused(q, limit, timeout_s, token=None):
        raise ConnectionRefusedError("no node on :4444")

    monkeypatch.setattr(recall_hook, "_node_search", refused)
    res = core.capture("test", "Node fallback", "The node is down but the keyword lane still answers.")
    r = recall_hook.recall_hook("node is down keyword lane answers", budget_ms=5000)
    assert r["tier"] in ("full", "keyword")
    assert any(s["ref"].endswith(f"@db{res.get('db_index')}") for s in r["shards"]), r
    assert "node" in r.get("errors", {})


def test_node_disabled_by_env_never_calls_it(vault, monkeypatch):
    called = []
    monkeypatch.setattr(recall_hook, "_node_search", lambda *a, **k: called.append(1) or [])
    recall_hook.recall_hook("node is off", budget_ms=2000)
    assert called == []


def test_claude_code_adapter_envelope(vault):
    out = json.loads(recall_hook.claude_code_hook(json.dumps({"prompt": "bridge token"}), budget_ms=2000))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    assert hso["additionalContext"].startswith("[NouGen recall")


def test_claude_code_hook_tolerates_non_object_json():
    import json as _json
    from nougen_shards import recall_hook as rh
    for raw in ("[]", "null", '"text"', "42"):
        out = _json.loads(rh.claude_code_hook(raw))
        assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"


def test_recall_threads_inherit_caller_vault_context(monkeypatch):
    """A tenant host's bind_active_vault must reach the worker threads."""
    from nougen_shards import core, recall_hook as rh
    seen = []
    monkeypatch.setattr(core, "retrieve", lambda q, limit=5: seen.append(core._ACTIVE_TENANT_ID.get()) or [])  # pylint: disable=protected-access
    monkeypatch.setattr(core, "_keyword_retrieve", lambda q, limit=5, domain_key="*": [])
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "0")
    token = core._ACTIVE_TENANT_ID.set("tenant-x")  # pylint: disable=protected-access
    try:
        rh.recall_hook("what is the tenant isolation rule", budget_ms=2000)
    finally:
        core._ACTIVE_TENANT_ID.reset(token)  # pylint: disable=protected-access
    assert seen == ["tenant-x"]


def test_partial_keyword_with_no_hits_says_incomplete():
    from nougen_shards import recall_hook as rh
    block = rh.format_block({"tier": "keyword", "partial": True, "reason": "vector lane did not finish inside budget", "shards": []})
    assert "did not finish" in block
