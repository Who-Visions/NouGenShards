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


def test_claude_code_adapter_envelope(vault):
    out = json.loads(recall_hook.claude_code_hook(json.dumps({"prompt": "bridge token"}), budget_ms=2000))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    assert hso["additionalContext"].startswith("[NouGen recall")
