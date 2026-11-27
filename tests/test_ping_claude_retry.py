"""AgentPinger.ping_claude retry loop: no sleep after the last attempt, and
the unix socket is closed on every failed attempt.

Before the fix the loop slept NOUGEN_CLAUDE_PIPE_RETRY_WAIT_S (0.7 s default)
after the final failed attempt too (pure dead time per busy session, before
the inbox fallback), and on POSIX a connect/sendall OSError skipped
s.close(), leaking one socket per attempt per session. Same fix as
nougenmsg elev/ping-retry.
"""
from __future__ import annotations

import errno
import json
import socket

import pytest

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import AgentPinger


@pytest.fixture
def env(tmp_path, monkeypatch):
    reg = tmp_path / "cc_sessions.json"
    reg.write_text(json.dumps({"sessions": {"sock-a": {"token": "t", "session_id": "s1"}}}), encoding="utf-8")
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: False)
    monkeypatch.setattr(nougenmsg, "_ping_seen_before", lambda *a, **k: False)
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(reg)))
    monkeypatch.setattr(AgentPinger, "_claude_inbox_dir", staticmethod(lambda: str(tmp_path / "inbox")))
    monkeypatch.setenv("NOUGEN_CLAUDE_PIPE_RETRY_WAIT_S", "0")
    sleeps = []
    monkeypatch.setattr(nougenmsg.time, "sleep", lambda s: sleeps.append(s))
    return sleeps


def _busy():
    exc = OSError(errno.EAGAIN, "busy")
    exc.winerror = 231  # ERROR_PIPE_BUSY: alive, not gone
    return exc


def _ping(osname, fake_socket=None):
    """Patch os.name (and socket.socket) only for the call: leaving them
    patched breaks pytest's own failure reporting (pathlib)."""
    saved = (nougenmsg.os.name, socket.socket, getattr(socket, "AF_UNIX", None))
    nougenmsg.os.name = osname
    if fake_socket is not None:
        socket.socket = fake_socket
        if saved[2] is None:
            socket.AF_UNIX = 1
    try:
        return AgentPinger.ping_claude("hello")
    finally:
        nougenmsg.os.name, socket.socket = saved[0], saved[1]
        if saved[2] is None and hasattr(socket, "AF_UNIX"):
            del socket.AF_UNIX


@pytest.mark.parametrize("retries", [1, 2, 3])
def test_no_sleep_after_final_attempt(env, monkeypatch, retries):
    monkeypatch.setenv("NOUGEN_CLAUDE_PIPE_RETRIES", str(retries))
    calls = []

    def busy_pipe(sock, raw):
        calls.append(sock)
        raise _busy()

    monkeypatch.setattr(AgentPinger, "_write_windows_named_pipe", staticmethod(busy_pipe))
    out = _ping("nt")
    assert len(calls) == retries
    assert len(env) == retries - 1
    assert out["delivered"] == [] and out["errors"][0]["pruned"] is False


def test_success_on_retry_still_waits_between_attempts(env, monkeypatch):
    monkeypatch.setenv("NOUGEN_CLAUDE_PIPE_RETRIES", "3")
    state = {"n": 0}

    def flaky(sock, raw):
        state["n"] += 1
        if state["n"] == 1:
            raise _busy()
        return len(raw)

    monkeypatch.setattr(AgentPinger, "_write_windows_named_pipe", staticmethod(flaky))
    out = _ping("nt")
    assert len(env) == 1
    assert out["delivered"][0]["attempt"] == 2 and out["errors"] == []


class _FakeSocket:
    opened: list = []

    def __init__(self, *a, **k):
        self.closed = False
        _FakeSocket.opened.append(self)

    def connect(self, path):
        raise OSError(errno.EAGAIN, "busy")

    def sendall(self, data):  # pragma: no cover - connect always fails
        pass

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def test_posix_socket_closed_on_failed_attempts(env, monkeypatch):
    monkeypatch.setenv("NOUGEN_CLAUDE_PIPE_RETRIES", "3")
    _FakeSocket.opened = []
    out = _ping("posix", _FakeSocket)
    assert len(_FakeSocket.opened) == 3
    assert all(s.closed for s in _FakeSocket.opened)
    assert out["delivered"] == [] and len(out["errors"]) == 1
