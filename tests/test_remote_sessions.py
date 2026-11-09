"""Phone Sessions screen: list Claude Code sessions, send to exactly one live one."""
import importlib.util
import json
from pathlib import Path

import pytest

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import AgentPinger

SECRET = "tok-should-never-leave"


def _load_bridge():
    mod_path = Path(__file__).resolve().parents[1] / "tools" / "nougen_remote.py"
    spec = importlib.util.spec_from_file_location("nougen_remote_sessions_under_test", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def registry(tmp_path, monkeypatch):
    reg = {
        "sessions": {
            r"\\.\pipe\LOCAL\cc-msg-aaa": {
                "socket": r"\\.\pipe\LOCAL\cc-msg-aaa", "token": SECRET, "session_id": "11111111-aaaa",
                "cwd": r"C:\work\NouGenRemote-Android", "machine": "blade1tb", "agent": "claude",
                "registered_utc": "2026-11-08T10:00:00Z",
            },
            r"\\.\pipe\LOCAL\cc-msg-bbb": {
                "socket": r"\\.\pipe\LOCAL\cc-msg-bbb", "token": SECRET, "session_id": "22222222-bbbb",
                "cwd": r"C:\work\NouGenShards", "machine": "blade1tb", "agent": "claude",
                "registered_utc": "2026-11-08T12:00:00Z",
            },
        },
        # phoebus-style top-level entry, idle
        "33333333-cccc": {"socket": r"\\.\pipe\LOCAL\cc-msg-ccc", "token": SECRET,
                          "cwd": "/srv/apps/site", "registered_utc": "2026-11-08T13:00:00Z"},
    }
    path = tmp_path / "cc_sessions.json"
    path.write_text(json.dumps(reg), encoding="utf-8")
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(path))
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: False)
    monkeypatch.setattr(AgentPinger, "_discover_claude_endpoints",
                        staticmethod(lambda: [r"\\.\pipe\LOCAL\cc-msg-aaa", r"\\.\pipe\LOCAL\cc-msg-bbb"]))
    return path


def test_list_sessions_hides_token_and_socket(registry):
    rows = AgentPinger.list_sessions()
    blob = json.dumps(rows)
    assert SECRET not in blob
    assert "cc-msg" not in blob
    assert {r["session_id"] for r in rows} == {"11111111-aaaa", "22222222-bbbb", "33333333-cccc"}


def test_list_sessions_live_first_newest_first(registry):
    rows = AgentPinger.list_sessions()
    assert [r["session_id"] for r in rows] == ["22222222-bbbb", "11111111-aaaa", "33333333-cccc"]
    assert [r["live"] for r in rows] == [True, True, False]
    assert rows[0]["project"] == "NouGenShards"
    assert rows[2]["project"] == "site"


def test_list_sessions_empty_for_tenant(registry, monkeypatch):
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: True)
    assert AgentPinger.list_sessions() == []


def test_list_sessions_missing_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(tmp_path / "absent.json"))
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: False)
    assert AgentPinger.list_sessions() == []


def test_bridge_list_reports_live_count(registry):
    res = _load_bridge().list_agent_sessions()
    assert res["ok"] is True and res["live"] == 2 and len(res["sessions"]) == 3


@pytest.mark.parametrize("sid,text,status", [
    ("", "hi", 400),
    ("11111111-aaaa", "   ", 400),
    ("99999999-zzzz", "hi", 404),
    ("33333333-cccc", "hi", 409),
])
def test_bridge_send_rejects(registry, sid, text, status):
    res = _load_bridge().send_to_agent_session(sid, text)
    assert res["ok"] is False and res["status"] == status


def test_bridge_send_length_cap(registry, monkeypatch):
    monkeypatch.setenv("NOUGEN_REMOTE_SESSION_MSG_MAX", "5")
    res = _load_bridge().send_to_agent_session("11111111-aaaa", "123456")
    assert res["status"] == 413


def test_bridge_send_targets_one_session(registry, monkeypatch):
    calls = []

    def fake_ping(prompt, origin=None, target_session=None):
        calls.append((prompt, target_session))
        return {"delivered": [{"session_id": target_session}]}

    monkeypatch.setattr(AgentPinger, "ping_claude", staticmethod(fake_ping))
    res = _load_bridge().send_to_agent_session("11111111-aaaa", "run the tests")
    assert res["ok"] is True and res["delivered"] == 1 and res["project"] == "NouGenRemote-Android"
    assert calls == [("[from phone] run the tests", "11111111-aaaa")]


def test_bridge_send_pipe_refused(registry, monkeypatch):
    monkeypatch.setattr(AgentPinger, "ping_claude",
                        staticmethod(lambda *a, **k: {"delivered": [], "reason": "not_found"}))
    res = _load_bridge().send_to_agent_session("11111111-aaaa", "hi")
    assert res["ok"] is False and res["status"] == 502 and res["error"] == "not_found"
