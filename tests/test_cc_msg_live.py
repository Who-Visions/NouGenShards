import json
from types import SimpleNamespace

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
    monkeypatch.setattr(AgentPinger, "_discover_claude_endpoints", staticmethod(
        lambda: [target_socket, other_socket]
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


def test_ping_claude_target_ignores_stale_pipe_for_same_session(tmp_path, monkeypatch):
    import nougen_shards.nougenmsg as nougenmsg

    stale_socket = r"\\.\pipe\LOCAL\cc-msg-stale"
    live_socket = r"\\.\pipe\LOCAL\cc-msg-live"
    session_id = "same-session"
    received = []
    monkeypatch.setattr(AgentPinger, "_write_windows_named_pipe", staticmethod(
        lambda path, raw: received.append((path, raw)) or len(raw)
    ))
    real_os = nougenmsg.os
    monkeypatch.setattr(nougenmsg, "os", SimpleNamespace(
        name="nt", path=real_os.path, environ=real_os.environ,
    ))
    monkeypatch.setattr(AgentPinger, "_discover_claude_endpoints", staticmethod(
        lambda: [live_socket]
    ))
    monkeypatch.setattr(AgentPinger, "_pipe_retries", staticmethod(lambda: 1))
    registry = tmp_path / "cc_sessions.json"
    registry.write_text(json.dumps({"sessions": {
        stale_socket: {"session_id": session_id, "socket": stale_socket, "token": "stale-token"},
        live_socket: {"session_id": session_id, "socket": live_socket, "token": "live-token"},
    }}), encoding="utf-8")
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(registry)))

    result = AgentPinger.ping_claude("LearnWithMrsB status", target_session=session_id)

    assert not result.get("error")
    assert [item["session_id"] for item in result["delivered"]] == [session_id]
    assert len(received) == 1
    assert received[0][0] == live_socket
    assert b"live-token" in received[0][1]
    assert b"stale-token" not in received[0][1]


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


def test_endpoint_gone_handles_winerror_2_3_5():
    err2 = OSError(2, "No such file or directory")
    err2.winerror = 2
    assert AgentPinger._endpoint_gone(err2) is True

    err3 = OSError(3, "Path not found")
    err3.winerror = 3
    assert AgentPinger._endpoint_gone(err3) is True

    err5 = PermissionError(13, "Access is denied")
    err5.winerror = 5
    assert AgentPinger._endpoint_gone(err5) is True

    # Busy pipe or timeout (WinError 231 ERROR_PIPE_BUSY or 121 ERROR_SEM_TIMEOUT) is NOT gone
    err_busy = OSError(231, "All pipe instances are busy")
    err_busy.winerror = 231
    assert AgentPinger._endpoint_gone(err_busy) is False


def test_ping_claude_prunes_winerror_5(tmp_path, monkeypatch):
    import nougen_shards.nougenmsg as nougenmsg

    denied_pipe = r"\\.\pipe\LOCAL\cc-msg-denied"
    notfound_pipe = r"\\.\pipe\LOCAL\cc-msg-notfound"
    live_pipe = r"\\.\pipe\LOCAL\cc-msg-live"

    def mock_write(path, raw):
        if path == denied_pipe:
            err = PermissionError(13, "Access is denied.")
            err.winerror = 5
            raise err
        if path == notfound_pipe:
            err = FileNotFoundError(2, "The system cannot find the file specified.")
            err.winerror = 2
            raise err
        return len(raw)

    monkeypatch.setattr(AgentPinger, "_write_windows_named_pipe", staticmethod(mock_write))
    real_os = nougenmsg.os
    monkeypatch.setattr(nougenmsg, "os", SimpleNamespace(
        name="nt", path=real_os.path, environ=real_os.environ, replace=real_os.replace, makedirs=real_os.makedirs,
    ))
    monkeypatch.setattr(AgentPinger, "_pipe_retries", staticmethod(lambda: 1))

    registry = tmp_path / "cc_sessions.json"
    registry.write_text(json.dumps({"sessions": {
        denied_pipe: {"session_id": "denied-session", "socket": denied_pipe, "token": "tok1"},
        notfound_pipe: {"session_id": "notfound-session", "socket": notfound_pipe, "token": "tok2"},
        live_pipe: {"session_id": "live-session", "socket": live_pipe, "token": "tok3"},
    }}), encoding="utf-8")
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(registry)))
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(registry))
    monkeypatch.setenv("NOUGEN_CLAUDE_INBOX", str(tmp_path / "claude_inbox"))

    res = AgentPinger.ping_claude("broadcast ping")

    assert [d["session_id"] for d in res["delivered"]] == ["live-session"]
    assert denied_pipe in res["pruned"]
    assert notfound_pipe in res["pruned"]

    # Verify updated registry on disk has only live_pipe left
    updated_reg = json.loads(registry.read_text(encoding="utf-8"))
    assert list(updated_reg["sessions"].keys()) == [live_pipe]

