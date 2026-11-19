"""ping_antigravity must not reach live sessions from the test suite.

Redirecting the inbox files (conftest ``isolated_msg_home``) was not enough: the
same call also sends the payload to every live session socket, and the session
on the other end writes it into the operator's real inbox.
"""
import glob as real_glob
import json
import os
import socket
import threading

import pytest

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import AgentPinger


def test_defaults_are_the_live_endpoints(monkeypatch):
    monkeypatch.delenv("NOUGEN_AGY_SOCK_DIR", raising=False)
    monkeypatch.delenv("NOUGEN_AGY_PIPE", raising=False)
    assert nougenmsg._agy_live_socket_glob() == os.path.join("/tmp/agy-socks", "*.sock")
    assert nougenmsg._agy_live_pipe() == r"\\.\pipe\LOCAL\agy-msg-antigravity"


def test_the_suite_points_both_endpoints_away_from_live_sessions(isolated_msg_home):
    pattern = nougenmsg._agy_live_socket_glob()
    assert pattern.startswith(str(isolated_msg_home))
    assert "/tmp/agy-socks" not in pattern
    assert real_glob.glob(pattern) == []
    assert nougenmsg._agy_live_pipe().endswith("nougen-tests-no-listener")


@pytest.mark.skipif(os.name == "nt", reason="POSIX socket transport")
def test_ping_antigravity_searches_only_the_isolated_socket_dir(isolated_msg_home, monkeypatch):
    searched = []
    found = []
    # Saved before patching: real_glob is the same module object nougenmsg imported, so calling
    # real_glob.glob from inside the wrapper would call the wrapper again and recurse. The
    # transport swallows that RecursionError, which would leave this test green for nothing.
    original_glob = real_glob.glob

    def recording_glob(pattern, *args, **kwargs):
        searched.append(pattern)
        hits = original_glob(pattern, *args, **kwargs)
        found.append(hits)
        return hits

    monkeypatch.setattr(real_glob, "glob", recording_glob)
    result = AgentPinger.ping_antigravity("isolation probe")

    assert result["status"] == "dropped"
    assert searched, "ping_antigravity no longer looks for session sockets"
    assert all(p.startswith(str(isolated_msg_home)) for p in searched)
    # Every search really ran (one result per search) and found no socket to send to.
    assert len(found) == len(searched) and all(hits == [] for hits in found)
    # The inbox copies stayed inside the throwaway home too.
    assert result["files"]
    assert all(f.startswith(str(isolated_msg_home)) for f in result["files"])


@pytest.mark.skipif(os.name == "nt", reason="POSIX socket transport")
def test_a_socket_in_the_override_dir_still_receives_the_payload(monkeypatch):
    # AF_UNIX paths are short (about 104 bytes on macOS) and pytest's tmp_path is
    # deeper than that, so this one directory lives directly under /tmp.
    import shutil
    import tempfile

    sock_dir = tempfile.mkdtemp(prefix="ngs", dir="/tmp")
    monkeypatch.setenv("NOUGEN_AGY_SOCK_DIR", sock_dir)
    path = os.path.join(sock_dir, "a.sock")

    received = []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    server.settimeout(10)

    def serve():
        try:
            conn, _ = server.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(10)
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            received.append(data)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        AgentPinger.ping_antigravity("override probe")
    finally:
        thread.join(timeout=10)
        server.close()
        shutil.rmtree(sock_dir, ignore_errors=True)

    assert received, "the socket in NOUGEN_AGY_SOCK_DIR was not contacted"
    payload = json.loads(received[0].decode("utf-8"))
    assert "override probe" in json.dumps(payload)
