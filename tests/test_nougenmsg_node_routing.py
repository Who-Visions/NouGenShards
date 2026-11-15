"""Verify nougenmsg_node cross-node/fleet routing via NouGenMsgBus and 422 fallback when unavailable."""
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


def test_cross_node_target_routes_via_fleet_bus(server, monkeypatch):
    node, port = server
    calls = []

    class FakeBus:
        @staticmethod
        def emit_node(node: str, target: str, text: str, origin=None):
            calls.append((node, target, text, origin))
            return {node: "DELIVERED"}

    monkeypatch.setattr(node, "_get_fleet_bus", lambda: FakeBus)
    code, body = _post(port, "@blade:antigravity")
    assert code == 200
    assert body["delivered"] is True
    assert body["routed"] is True
    assert body["method"] == "fleet_bus"
    assert calls == [("blade", "antigravity", "ping", {"sender": "probe"})]
    if node.INBOX.exists():
        assert not list(node.INBOX.glob("*.json"))


def test_broadcast_target_routes_via_emit_fleet_background(server, monkeypatch):
    node, port = server
    calls = []

    class FakeBus:
        @staticmethod
        def emit_fleet(text: str, target: str = "all", origin=None, background: bool = False):
            calls.append((text, target, origin, background))
            return {"phoebus": "ok", "blade": {"queued": True}}

    monkeypatch.setattr(node, "_get_fleet_bus", lambda: FakeBus)
    code, body = _post(port, "@all")
    assert code == 200
    assert body["delivered"] is True
    assert body["routed"] is True
    assert calls == [("ping", "all", {"sender": "probe"}, True)]


def test_cross_node_route_error_returns_502_and_releases_claim(server, monkeypatch):
    node, port = server

    class FakeBus:
        @staticmethod
        def emit_node(node: str, target: str, text: str, origin=None):
            return {node: "Error: ssh timeout"}

    monkeypatch.setattr(node, "_get_fleet_bus", lambda: FakeBus)
    code, body = _post(port, "@blade")
    assert code == 502
    assert body["delivered"] is False
    assert body["routed"] is False
    assert body["status"] == "route_failed"


@pytest.mark.parametrize("target", ["@blade", "@whoart", "@all", "@fleet"])
def test_foreign_target_returns_422_when_bus_unavailable(server, monkeypatch, target):
    node, port = server
    monkeypatch.setattr(node, "_get_fleet_bus", lambda: None)
    code, body = _post(port, target)
    assert code == 422
    assert body["delivered"] is False
    assert body["routed"] is False
    assert body["status"] == "not_routed"


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
