"""Shards-first receipts and the protected-mutation gate (#1084)."""
import json
import time

import pytest

from nougen_shards import agent_hooks, context_receipt as cr


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECEIPTS_DIR", str(tmp_path / "receipts"))
    relay = tmp_path / "relay"
    (relay / "claims").mkdir(parents=True)
    (relay / "leg1.json").write_text("{}")
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(relay))
    monkeypatch.setenv("NOUGEN_TENANT", "tenant-a")
    for k in ("NOUGEN_DEGRADED_MODE", "NOUGEN_CTX_GATE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NOUGEN_SHARDS_GATE", "deny")


FULL_EMPTY = {"tier": "full", "partial": False, "shards": [], "elapsed_ms": 40}
FULL_HITS = {"tier": "node", "partial": False, "shards": [{"id": "s1", "body": "secret body"}]}
PARTIAL = {"tier": "keyword", "partial": True, "shards": [{"id": "s2"}], "reason": "vector lane slow"}
NONE = {"tier": "none", "partial": True, "shards": [], "reason": "budget exhausted"}


def _commit(sid="s"):
    return {"session_id": sid, "tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}


def _decision(out):
    return out.get("hookSpecificOutput", {}).get("permissionDecision")


def test_empty_but_complete_is_complete():
    r = cr.build("s", "fix the nougen relay", FULL_EMPTY)
    assert r["status"] == cr.COMPLETE and r["recall"]["fanout"] == 0
    assert "real 'no match'" in cr.status_line(r)


def test_partial_is_degraded_and_none_is_unknown():
    assert cr.build("s", "x", PARTIAL)["status"] == cr.DEGRADED
    r = cr.build("s", "x", NONE)
    assert r["status"] == cr.UNKNOWN
    line = cr.status_line(r)
    assert "UNKNOWN" in line and "do not say 'no memory'" in line


def test_relay_down_is_degraded(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "missing"))
    assert cr.build("s", "x", FULL_HITS)["status"] == cr.DEGRADED


def test_receipt_holds_refs_not_bodies_or_prompt():
    r = cr.build("s", "my password is hunter2 nougen", FULL_HITS)
    blob = json.dumps(r)
    assert "secret body" not in blob and "hunter2" not in blob
    assert r["recall"]["shard_refs"] == ["s1"] and r["tenant"] == "tenant-a"


def test_gate_allows_fresh_complete_receipt():
    cr.save(cr.build("s", "x", FULL_EMPTY))
    assert agent_hooks.pre_tool(_commit()) == {}


@pytest.mark.parametrize("recall", [PARTIAL, NONE])
def test_gate_denies_degraded_and_unknown(recall):
    cr.save(cr.build("s", "x", recall))
    out = agent_hooks.pre_tool(_commit())
    assert _decision(out) == "deny"
    assert "protected mutation" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_reviewed_degraded_mode_downgrades_to_warning(monkeypatch):
    cr.save(cr.build("s", "x", NONE))
    monkeypatch.setenv("NOUGEN_DEGRADED_MODE", "reviewed")
    out = agent_hooks.pre_tool(_commit())
    assert _decision(out) is None and "additionalContext" in out["hookSpecificOutput"]


def test_stale_receipt_denied():
    r = cr.build("s", "x", FULL_EMPTY)
    r["created_ts"] = time.time() - r["ttl_s"] - 5
    cr.save(r)
    assert _decision(agent_hooks.pre_tool(_commit())) == "deny"


def test_other_tenant_receipt_is_invisible(monkeypatch):
    cr.save(cr.build("s", "x", FULL_EMPTY))
    monkeypatch.setenv("NOUGEN_TENANT", "tenant-b")
    assert cr.load("s") is None
    ok, why = cr.validate(cr.build("s", "x", FULL_EMPTY) | {"tenant": "tenant-a"}, "s")
    assert not ok and "tenant" in why


def test_other_session_receipt_rejected():
    r = cr.build("other", "x", FULL_EMPTY)
    assert cr.validate(r, "s") == (False, "receipt belongs to another session")


def test_missing_receipt_passes_silently():
    # No sensitive prompt was classified this session: nothing to enforce.
    assert agent_hooks.pre_tool(_commit("fresh")) == {}
    assert cr.validate(None, "fresh") == (False, "no context receipt for this session (recall never ran)")


def test_unprotected_command_passes():
    cr.save(cr.build("s", "x", NONE))
    evt = {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "git status"}}
    assert agent_hooks.pre_tool(evt) == {}


@pytest.mark.parametrize("cmd", ["git push origin x", "gh pr merge 1 --squash", "gh pr create -t x",
                                 "wrangler deploy", "nougen forget 12"])
def test_protected_commands_detected(cmd):
    assert cr.protected_reason("Bash", cmd)


def test_protected_mcp_tool_detected():
    assert cr.protected_reason("mcp__nougen-shards__shards_forget", "")
    assert cr.protected_reason("mcp__nougen-shards__cf_deploy_worker", "")


def test_relay_check_reads_handoffs_claims_separately(tmp_path, monkeypatch):
    relay = tmp_path / "relay2"
    claims = relay / ".handoffs" / "claims"
    claims.mkdir(parents=True)
    (relay / "leg_a.json").write_text("{}")
    (claims / "claim_1.json").write_text("{}")
    (claims / "claim_2.json").write_text("{}")
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(relay))
    res = cr.relay_check()
    assert res["ok"] is True
    assert res["claims"] == 2
    assert res["legs"] == 1


def test_failed_receipt_save_invalidates_prior_complete_receipt(monkeypatch):
    from nougen_shards import recall_hook
    cr.save(cr.build("s", "first nougen prompt", FULL_EMPTY))
    assert agent_hooks.pre_tool(_commit("s")) == {}

    monkeypatch.setattr(recall_hook, "recall_hook", lambda text, **k: dict(NONE, query=text))
    orig_save = cr.save

    def broken_save(receipt):
        if receipt.get("task_hash"):
            raise OSError("disk full")
        return orig_save(receipt)

    monkeypatch.setattr(cr, "save", broken_save)
    out = agent_hooks.prompt({"session_id": "s", "prompt": "second nougen prompt"})
    assert "UNKNOWN" in out["hookSpecificOutput"]["additionalContext"]
    assert _decision(agent_hooks.pre_tool(_commit("s"))) == "deny"


def test_gate_off(monkeypatch):
    cr.save(cr.build("s", "x", NONE))
    monkeypatch.setenv("NOUGEN_SHARDS_GATE", "off")
    assert agent_hooks.pre_tool(_commit()) == {}


def test_crashing_gate_fails_closed_on_protected(monkeypatch):
    def boom(evt):
        raise RuntimeError("x")
    monkeypatch.setitem(agent_hooks.HANDLERS, "pre-tool", boom)
    out = json.loads(agent_hooks.run("pre-tool", json.dumps(_commit())))
    assert _decision(out) == "deny"
    safe = {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    assert json.loads(agent_hooks.run("pre-tool", json.dumps(safe))) == {}


def test_prompt_hook_records_receipt_for_sensitive(monkeypatch):
    from nougen_shards import recall_hook
    monkeypatch.setattr(recall_hook, "recall_hook", lambda text, **k: dict(NONE, query=text))
    out = agent_hooks.prompt({"session_id": "p1", "prompt": "check the nougen relay"})
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "Shards receipt: UNKNOWN" in ctx
    assert cr.load("p1")["status"] == cr.UNKNOWN


def test_prompt_hook_skips_receipt_for_trivial(monkeypatch):
    from nougen_shards import recall_hook
    monkeypatch.setattr(recall_hook, "recall_hook", lambda text, **k: dict(FULL_EMPTY, query=text))
    agent_hooks.prompt({"session_id": "p2", "prompt": "what is 2+2"})
    assert cr.load("p2") is None


def test_default_mode_is_observe_only(monkeypatch):
    monkeypatch.delenv("NOUGEN_SHARDS_GATE")
    cr.save(cr.build("s", "x", NONE))
    out = agent_hooks.pre_tool(_commit())
    assert _decision(out) is None and "UNKNOWN" in json.dumps(out)
