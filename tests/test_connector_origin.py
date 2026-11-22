"""A message relayed by the fleet connector keeps the caller's node.

Regression: app.py's ``nougenmsg`` tool took no ``origin`` argument, so the
node/lane the connector forwards were dropped and the receiving box stamped
its own name on every remote lane's message. Synthetic node names only.
"""
import ast
from pathlib import Path
from typing import Optional

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import NouGenMsgBus, display_sender

_origin_envelope = NouGenMsgBus._origin_envelope

APP = Path(__file__).resolve().parents[1] / "app.py"


def _load_helper():
    """Exec only _connector_origin from app.py (importing app.py boots a node)."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    keep = [n for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name == "_connector_origin")
            or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_CONNECTOR_ORIGIN_KEYS"
                                                  for t in n.targets))]
    ns = {"Optional": Optional}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(APP), "exec"), ns)
    return ns["_connector_origin"]


def test_tool_accepts_origin():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "nougenmsg")
    assert "origin" in [a.arg for a in fn.args.args]


def test_no_origin_means_local_caller():
    f = _load_helper()
    assert f(None) is None and f({}) is None


def test_missing_machine_never_becomes_the_box():
    o = _load_helper()({"lane": "claude-app"})
    assert o["machine"] == "remote" and o["original_sender"] == "remote-claude-app"


def test_connector_origin_is_forwarded_not_stamped(monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE", "nodea")
    o = _load_helper()({"machine": "nodeb", "lane": "claude-app", "transport": "nougen-fleet-mcp",
                        "evil": {"x": 1}})
    assert "evil" not in o
    env = _origin_envelope(o, forwarded=True)
    assert env["machine"] == "nodeb" and env["origin_trust"] == "forwarded-unverified"
    label = display_sender(env)
    assert label.startswith("nodeb") and "(asserted)" in label and "nodea" not in label


def test_send_resolved_threads_forwarded(monkeypatch):
    seen = {}

    def fake_emit_node(node, agent, text, origin=None, audience=None, forwarded=False, **_kw):
        seen["forwarded"], seen["origin"] = forwarded, origin
        return {node: "ok"}

    monkeypatch.setattr(NouGenMsgBus, "emit_node", staticmethod(fake_emit_node))
    monkeypatch.setattr(nougenmsg, "get_current_node", lambda: "nodea")
    monkeypatch.setattr(nougenmsg, "resolve_target", lambda t: type("R", (), {
        "ok": True, "kind": "node", "deliveries": [type("D", (), {"node": "nodea", "lane": "claude"})()],
        "as_dict": lambda self: {}})())
    NouGenMsgBus.send_resolved("nodea", "hi", origin={"machine": "nodeb"}, forwarded=True)
    assert seen == {"forwarded": True, "origin": {"machine": "nodeb"}}
