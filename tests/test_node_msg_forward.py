"""POST /msg on the shard node forwards to the co-located NouGenMsg node.

The connector sends @whoart / @blade messages to <node origin>/msg; before this
route every peer send answered 404 "Nothing delivered" (2026-11-12)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def _fake_msg_node(status=200):
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got["path"] = self.path
            got["token"] = self.headers.get("X-NGS-Token")
            got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "queued": 1}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, got


def _client(monkeypatch):
    import app as node
    from fastapi.testclient import TestClient
    monkeypatch.setattr(node, "NODE_TOKEN", "owner-tok")
    return TestClient(node.app, raise_server_exceptions=False)


def test_msg_requires_owner_token(monkeypatch):
    c = _client(monkeypatch)
    assert c.post("/msg", json={"text": "hi"}).status_code == 401


def test_msg_is_forwarded_with_local_token_and_status_passed_through(monkeypatch):
    srv, got = _fake_msg_node()
    try:
        monkeypatch.setenv("NOUGEN_MSG_LOCAL_URL", f"http://127.0.0.1:{srv.server_port}/msg")
        monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", "msg-tok")
        c = _client(monkeypatch)
        r = c.post("/msg", json={"text": "hello", "sender": "t"}, headers={"X-NGS-Token": "owner-tok"})
        assert r.status_code == 200 and r.json()["queued"] == 1
        assert got == {"path": "/msg", "token": "msg-tok", "body": {"text": "hello", "sender": "t"}}
    finally:
        srv.shutdown()


def test_local_refusal_is_not_hidden(monkeypatch):
    srv, _ = _fake_msg_node(status=401)
    try:
        monkeypatch.setenv("NOUGEN_MSG_LOCAL_URL", f"http://127.0.0.1:{srv.server_port}/msg")
        c = _client(monkeypatch)
        assert c.post("/msg", json={"text": "x"}, headers={"X-NGS-Token": "owner-tok"}).status_code == 401
    finally:
        srv.shutdown()


def test_dead_local_node_is_502_not_200(monkeypatch):
    monkeypatch.setenv("NOUGEN_MSG_LOCAL_URL", "http://127.0.0.1:9/msg")
    c = _client(monkeypatch)
    assert c.post("/msg", json={"text": "x"}, headers={"X-NGS-Token": "owner-tok"}).status_code == 502
