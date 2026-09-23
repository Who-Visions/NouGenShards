"""ping_claude must read both cc_sessions.json shapes, even mixed in one file."""
import json
import os
import socket
import tempfile
import threading

import pytest
from nougen_shards.nougenmsg import AgentPinger


def _serve(path, got):
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(path)
    srv.listen(1)

    def run():
        conn, _ = srv.accept()
        got.append(conn.recv(4096))
        conn.close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return srv, t


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="AF_UNIX sockets not supported on this OS")
def test_empty_nested_sessions_does_not_mask_top_level_entries(tmp_path, monkeypatch):
    sock = os.path.join(tempfile.mkdtemp(prefix="cc", dir="/tmp"), "s.sock")  # AF_UNIX path limit
    got = []
    srv, t = _serve(sock, got)
    reg = tmp_path / "cc_sessions.json"
    reg.write_text(json.dumps({"sessions": {}, "abc123": {"socket": sock, "token": "tok"}}))
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(reg))
    monkeypatch.setenv("NOUGEN_CLAUDE_INBOX", str(tmp_path / "inbox"))
    res = AgentPinger.ping_claude("hello")
    t.join(2)
    srv.close()
    assert res["registered"] == 1
    assert len(res["delivered"]) == 1
    assert b"hello" in got[0]
