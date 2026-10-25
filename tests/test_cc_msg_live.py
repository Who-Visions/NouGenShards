import json
import os
from types import SimpleNamespace

import pytest

from nougen_shards.nougenmsg import AgentPinger
from tools import cc_msg


def test_ping_claude_target_session_does_not_fan_out(tmp_path, monkeypatch):
    import nougen_shards.nougenmsg as nougenmsg

    target_socket = r"\\.\pipe\LOCAL\cc-msg-target"
    other_socket = r"\\.\pipe\LOCAL\cc-msg-other"
    received = []
    monkeypatch.setattr(AgentPinger, "_write_windows_named_pipe", staticmethod(
        lambda path, raw: received.append((path, raw)) or len(raw)
    ))
    real_os = nougenmsg.os
    monkeypatch.setattr(nougenmsg, "os", SimpleNamespace(
        name="nt", path=real_os.path, environ=real_os.environ,
    ))
    monkeypatch.setattr(nougenmsg, "get_current_node", lambda: "whoart")
    monkeypatch.setattr(AgentPinger, "_pipe_retries", staticmethod(lambda: 1))
    registry = tmp_path / "cc_sessions.json"
    registry.write_text(json.dumps({"sessions": {
        target_socket: {"session_id": "target-session", "socket": target_socket, "token": "target-token"},
        other_socket: {"session_id": "other-session", "socket": other_socket, "token": "other-token"},
    }}), encoding="utf-8")
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(registry)))
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(registry))
    monkeypatch.setenv("NOUGEN_CLAUDE_INBOX", str(tmp_path / "claude_inbox"))

    result = AgentPinger.ping_claude("LearnWithMrsB status", target_session="target-session")

    assert [item["session_id"] for item in result["delivered"]] == ["target-session"]
    assert len(received) == 1
    assert received[0][0] == target_socket
    assert b"LearnWithMrsB status" in received[0][1]
    assert b"other-token" not in received[0][1]
    assert result["inbox_file"] is None
    assert not list((tmp_path / "claude_inbox").glob("*.json"))


def test_claude_alias_resolves_only_one_live_registered_session(tmp_path, monkeypatch):
    registry = tmp_path / "cc_sessions.json"
    registry.write_text(json.dumps({"sessions": {
        r"\\.\pipe\LOCAL\cc-msg-active": {
            "session_id": "2a593c06-2f10-4037-b91c-5cf4e4ae12d6",
            "socket": r"\\.\pipe\LOCAL\cc-msg-active",
            "token": "never-return-this",
        },
        r"\\.\pipe\LOCAL\cc-msg-stale": {
            "session_id": "stale-session",
            "socket": r"\\.\pipe\LOCAL\cc-msg-stale",
            "token": "never-return-this-either",
        },
        r"\\.\pipe\LOCAL\cc-msg-other": {
            "session_id": "other-session",
            "socket": r"\\.\pipe\LOCAL\cc-msg-other",
            "token": "never-return-this-third",
        },
    }}), encoding="utf-8")
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(registry)))
    monkeypatch.setattr(AgentPinger, "_discover_claude_endpoints", staticmethod(
        lambda: [r"\\.\pipe\LOCAL\cc-msg-active"]
    ))

    session_id, error = cc_msg.resolve_claude_session("claude")
    assert error is None
    assert session_id == "2a593c06-2f10-4037-b91c-5cf4e4ae12d6"

    monkeypatch.setattr(AgentPinger, "_discover_claude_endpoints", staticmethod(
        lambda: [r"\\.\pipe\LOCAL\cc-msg-active", r"\\.\pipe\LOCAL\cc-msg-other"]
    ))
    session_id, error = cc_msg.resolve_claude_session("claude")
    assert session_id is None
    assert "More than one" in error
