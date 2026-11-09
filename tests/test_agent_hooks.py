"""`nougen hook` must wire a fresh install into Claude Code without touching anything else."""
import json
import sqlite3

import pytest

from nougen_shards import agent_hooks as ah


@pytest.fixture
def env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    con = sqlite3.connect(vault / "nougen_shards_1.db")
    con.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT, event_type TEXT, title TEXT)")
    con.execute("INSERT INTO shards (timestamp, event_type, title) VALUES ('2026-11-09T06:00:00Z','KNOWLEDGE','hooks ship publicly')")
    con.commit()
    con.close()
    from nougen_shards import core
    monkeypatch.setattr(core, "active_vault_dir", lambda: vault)
    handoffs = tmp_path / "handoffs"
    from nougen_shards import handoff
    monkeypatch.setattr(handoff, "HANDOFF_DIR", handoffs)
    # No vault mirror, triggers or network from a unit test.
    monkeypatch.setattr(handoff, "_log_context_event", lambda *a, **k: None)
    monkeypatch.setattr(handoff, "_fire_triggers", lambda *a, **k: [])
    work = tmp_path / "proj"
    work.mkdir()
    monkeypatch.chdir(work)  # not a git repo: git helpers return ""
    return tmp_path


def _manual_handoff(env, cwd, name="handoff_20991231_000000_claude-cli"):
    d = env / "handoffs" / "claude cli handoffs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps({"handoff_id": name, "cwd": str(cwd), "agent": "claude-cli"}), encoding="utf-8")


def _auto_records(env):
    out = []
    for f in (env / "handoffs").rglob("handoff_*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        if str(data.get("goal", "")).startswith("auto:"):
            out.append(data)
    return out


FOREIGN = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-own-stop-hook"}]}]},
           "model": "keep-me"}


def test_install_is_idempotent_and_keeps_foreign_hooks(env):
    settings = env / "settings.json"
    settings.write_text(json.dumps(FOREIGN), encoding="utf-8")
    first = ah.install(settings, python="/x/python")
    assert first["changed"] and "backup" in first
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["model"] == "keep-me"
    assert any(h["command"] == "my-own-stop-hook" for e in data["hooks"]["Stop"] for h in e["hooks"])
    for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
        assert sum(ah._ours(e) for e in data["hooks"][event]) == 1  # pylint: disable=protected-access
    second = ah.install(settings, python="/x/python")
    assert second["changed"] is False
    assert ah.status(settings)["missing"] == []


def test_uninstall_removes_only_ours(env):
    settings = env / "settings.json"
    settings.write_text(json.dumps(FOREIGN), encoding="utf-8")
    ah.install(settings, python="/x/python")
    ah.install(settings, python="/x/python", uninstall=True)
    assert json.loads(settings.read_text(encoding="utf-8")) == FOREIGN


def test_dry_run_writes_nothing(env):
    settings = env / "settings.json"
    rep = ah.install(settings, python="/x/python", dry_run=True)
    assert rep["changed"] and not settings.exists()


def test_session_start_injects_handoff_and_shards(env):
    d = env / "handoffs" / "claude cli handoffs"
    d.mkdir(parents=True)
    (d / "handoff_20261109_010000_claude-cli.md").write_text("# last handoff: ship hooks", encoding="utf-8")
    out = json.loads(ah.run("session-start", json.dumps({"session_id": "s1"})))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "ship hooks" in ctx and "hooks ship publicly" in ctx


def test_session_end_writes_registry_record_once(env):
    ah.run("session-start", json.dumps({"session_id": "s2"}))
    ah.run("session-end", json.dumps({"session_id": "s2"}))
    autos = _auto_records(env)
    assert len(autos) == 1 and autos[0]["cwd"] == str(env / "proj")
    from nougen_shards import handoff
    assert any(p.name.endswith(".json") for p in handoff.get_handoff_files())  # discoverable by the registry


def test_session_end_skips_when_this_session_wrote_one(env):
    ah.run("session-start", json.dumps({"session_id": "s3"}))
    _manual_handoff(env, env / "proj")
    ah.run("session-end", json.dumps({"session_id": "s3"}))
    assert not _auto_records(env)


def test_another_projects_handoff_does_not_suppress_ours(env):
    ah.run("session-start", json.dumps({"session_id": "s4"}))
    _manual_handoff(env, env / "some-other-project")
    ah.run("session-end", json.dumps({"session_id": "s4"}))
    assert len(_auto_records(env)) == 1


def test_mixed_entry_keeps_foreign_handler(env):
    settings = env / "settings.json"
    ah.install(settings, python="/x/python")
    data = json.loads(settings.read_text(encoding="utf-8"))
    ours = data["hooks"]["Stop"][0]["hooks"][0]
    data["hooks"]["Stop"] = [{"matcher": "*", "hooks": [{"type": "command", "command": "foreign"}, ours]}]
    settings.write_text(json.dumps(data), encoding="utf-8")
    ah.install(settings, python="/x/python", uninstall=True)
    after = json.loads(settings.read_text(encoding="utf-8"))
    assert after["hooks"]["Stop"] == [{"matcher": "*", "hooks": [{"type": "command", "command": "foreign"}]}]


@pytest.mark.parametrize("raw", ["", "[]", "null", "not json"])
def test_every_event_is_fail_soft(env, raw):
    for event in ah.EVENTS:
        json.loads(ah.run(event, raw))  # always valid JSON, never raises
