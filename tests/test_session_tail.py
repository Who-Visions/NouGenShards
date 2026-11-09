"""Phone live view: tail of one Claude Code session transcript."""
import importlib.util
import json
from pathlib import Path

import pytest

from nougen_shards.nougenmsg import AgentPinger

SID = "11111111-aaaa"


def _load_bridge():
    mod_path = Path(__file__).resolve().parents[1] / "tools" / "nougen_remote.py"
    spec = importlib.util.spec_from_file_location("nougen_remote_tail_under_test", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def transcript(tmp_path, monkeypatch):
    proj = tmp_path / "projects" / "some-project"
    proj.mkdir(parents=True)
    rows = [
        {"type": "user", "timestamp": "t1", "message": {"role": "user", "content": "build the thing"}},
        {"type": "user", "timestamp": "t1b", "message": {"role": "user", "content": "<system-reminder>noise</system-reminder>"}},
        {"type": "assistant", "timestamp": "t2", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Building it now."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "gradlew build", "description": "Build the app"}}]}},
        {"type": "mode", "timestamp": "t3"},
        {"type": "assistant", "timestamp": "t4", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done, build-124 is out."}]}},
    ]
    (proj / f"{SID}.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(AgentPinger, "list_sessions", staticmethod(lambda: [{"session_id": SID, "live": True}]))
    return proj


def test_tail_keeps_order_text_and_tools(transcript):
    res = _load_bridge().session_tail(SID, 10)
    assert res["ok"] is True
    kinds = [(e["role"], e["kind"], e.get("tool")) for e in res["events"]]
    assert kinds == [("user", "text", None), ("assistant", "text", None), ("assistant", "tool", "Bash"), ("assistant", "text", None)]
    assert res["events"][2]["text"] == "Build the app"
    assert res["events"][-1]["text"] == "Done, build-124 is out."
    assert all("system-reminder" not in e["text"] for e in res["events"])


def test_tail_limit_keeps_newest(transcript):
    res = _load_bridge().session_tail(SID, 2)
    assert [e["text"] for e in res["events"]] == ["Build the app", "Done, build-124 is out."]


def test_tail_rejects_unregistered(transcript, monkeypatch):
    monkeypatch.setattr(AgentPinger, "list_sessions", staticmethod(lambda: []))
    res = _load_bridge().session_tail(SID)
    assert res["ok"] is False and res["status"] == 404


def test_tail_missing_transcript(transcript, monkeypatch):
    monkeypatch.setattr(AgentPinger, "list_sessions", staticmethod(lambda: [{"session_id": "22222222-bbbb"}]))
    res = _load_bridge().session_tail("22222222-bbbb")
    assert res["ok"] is False and res["status"] == 404


def test_tail_fails_closed_without_redactor(transcript, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "nougen_shards.brain_scan.redaction":
            raise ImportError("no redactor")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    res = _load_bridge().session_tail(SID)
    assert res["ok"] is False and res["status"] == 503 and "events" not in res
