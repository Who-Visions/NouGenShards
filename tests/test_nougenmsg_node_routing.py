"""Verify local-only nougenmsg_node refuses foreign/fleet targets instead of returning delivered:true."""
from __future__ import annotations

import importlib
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

TOKEN = "routing-test-token"
AUTH = {"Content-Type": "application/json", "X-NGS-Token": TOKEN}


@pytest.fixture()
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_NODE_NAME", "phoebus")
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", TOKEN)
    monkeypatch.setenv("NOUGEN_AGY_MSG_AUTH", "required")
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_MSG_STATE", str(tmp_path / "state.json"))
    for name in [m for m in sys.modules if m.startswith(("nougenmsg_node", "_agy_live"))]:
        del sys.modules[name]
    node = importlib.import_module("nougenmsg_node")
    srv = node.ThreadingHTTPServer(("127.0.0.1", 0), node.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield node, port
    srv.shutdown()
    srv.server_close()


def _post(port: int, target: str) -> tuple[int, dict]:
    data = json.dumps({"text": "ping", "sender": "probe", "target": target}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/msg", data=data, headers=AUTH)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


@pytest.mark.parametrize(
    "target",
    ["@blade", "blade", "@blade:antigravity", "@whoart", "@unknown-node", "@all", "@fleet", "fleet"],
)
def test_foreign_or_broadcast_target_is_not_routed(server, target):
    node, port = server
    code, body = _post(port, target)
    assert code == 422
    assert body["delivered"] is False
    assert body["routed"] is False
    assert body["status"] == "not_routed"
    if node.INBOX.exists():
        assert not list(node.INBOX.glob("*.json"))


@pytest.mark.parametrize(
    "target",
    ["@phoebus", "phoebus", "@phoebus:antigravity", "@antigravity", "all", "local", "self"],
)
def test_local_target_delivers_normally(server, target):
    _, port = server
    code, body = _post(port, target)
    assert code == 200
    assert body["delivered"] is True
    assert body["node"] == "phoebus"
