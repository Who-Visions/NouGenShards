"""POST /msg must not report delivered:true for a target this node cannot reach.

The HTTP receiver writes its own inbox and wakes its own sessions; it never forwards to
another node. A POST addressed to another node used to come back delivered:true while only
the receiving node saw it (fleet leg 20261115T024443Z).
"""
import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
TOKEN = "t0k"


def _load_node(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", TOKEN)
    monkeypatch.setenv("NOUGEN_NODE_NAME", "nodea")
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("nougenmsg_node_foreign_t", TOOLS / "nougenmsg_node.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Fixed fleet view: nodea is this node, nodeb is another one.
    table = {"@nodeb": "nodeb", "@nodeb:claude": "nodeb", "@all": "fleet", "@claude": "local", "@nodea:claude": "nodea"}
    monkeypatch.setattr(mod, "_bus_view", lambda target: (table.get(target, "local"), {"nodea"}))
    monkeypatch.setattr(mod, "gate_and_deliver", lambda *a, **k: {"attempted": False})
    return mod


def _post(port, body):
    req = urllib.request.Request("http://127.0.0.1:{}/msg".format(port), data=json.dumps(body).encode(), method="POST",
                                 headers={"X-NGS-Token": TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _serve(node):
    server = node.BoundedThreadingHTTPServer(("127.0.0.1", 0), node.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def test_another_nodes_target_is_refused_and_nothing_is_written(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    server, port = _serve(node)
    try:
        for target in ("@nodeb", "@nodeb:claude"):
            code, reply = _post(port, {"text": "for the other node", "sender": "x/y", "target": target})
            assert code == 421
            assert reply["delivered"] is False and reply["routed"] is False
            assert reply["node"] == "nodea" and reply["target_node"] == "nodeb"
        inbox = tmp_path / "inbox"
        assert not inbox.exists() or not list(inbox.glob("msg_*.json")), "a refused message left an inbox file"
    finally:
        server.shutdown()


def test_refused_message_can_be_resent_locally_without_looking_like_a_repeat(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    server, port = _serve(node)
    try:
        body = {"text": "same words", "sender": "x/y", "message_id": "resend1"}
        assert _post(port, dict(body, target="@nodeb"))[0] == 421
        code, reply = _post(port, dict(body, target="nodea"))
        assert code == 200 and reply["delivered"] is True and reply["duplicate"] is False
    finally:
        server.shutdown()


def test_all_is_delivered_here_and_says_the_other_nodes_were_not_reached(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    server, port = _serve(node)
    try:
        code, reply = _post(port, {"text": "everyone", "sender": "x/y", "target": "@all"})
        assert code == 200 and reply["delivered"] is True
        assert reply["scope"] == {"scope": "fleet", "routed": False, "reached": ["nodea"]}
        assert list((tmp_path / "inbox").glob("msg_*.json"))
    finally:
        server.shutdown()


def test_local_targets_are_unchanged(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    server, port = _serve(node)
    try:
        for target in (None, "nodea", "@nodea", "@claude", "@nodea:claude"):
            body = {"text": "local {}".format(target), "sender": "x/y"}
            if target:
                body["target"] = target
            code, reply = _post(port, body)
            assert code == 200 and reply["delivered"] is True and reply["scope"] == {"scope": "local"}
    finally:
        server.shutdown()


def test_without_the_bus_parser_only_all_is_flagged(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)

    def boom(target):
        raise ImportError("no package")

    monkeypatch.setattr(node, "_bus_view", boom)
    assert node.delivery_scope("@all")["scope"] == "fleet"
    assert node.delivery_scope("@nodeb") == {"scope": "local"}
