"""emit_fleet(background=True): local delivery now, SSH fan-out in a daemon thread.

Regression for 2026-09-14: the node's nougenmsg tool fanned out to peers one at
a time over SSH (76s observed) inside the connector's 20s gateway budget, so the
connector fell back and the message arrived twice.
"""
import ast
import threading
import time
from pathlib import Path

import nougen_shards.nougenmsg as m

APP = Path(__file__).resolve().parents[1] / "app.py"


def _stub(monkeypatch, peer_delay=0.0):
    calls, done = [], threading.Event()
    monkeypatch.setattr(m, "get_current_node", lambda: "phoebus")
    monkeypatch.setattr(m.NouGenMsgBus, "live_ping",
                        classmethod(lambda cls, target, text, origin=None, **k: {"local": "ok"}))

    def fake_emit_node(cls, node, target, text, origin=None):
        time.sleep(peer_delay)
        calls.append(node)
        if len(calls) == 2:
            done.set()
        return {node: "delivered"}
    monkeypatch.setattr(m.NouGenMsgBus, "emit_node", classmethod(fake_emit_node))
    return calls, done


def test_background_returns_before_slow_peers_and_still_delivers(monkeypatch):
    calls, done = _stub(monkeypatch, peer_delay=0.5)
    t0 = time.monotonic()
    res = m.NouGenMsgBus.emit_fleet("hi", target="all", background=True)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.3, f"background emit_fleet blocked for {elapsed:.2f}s"
    assert res["phoebus"] == {"local": "ok"}
    assert res["blade"] == {"queued": True, "via": "ssh"}
    assert res["whoart"] == {"queued": True, "via": "ssh"}
    assert done.wait(5), "background fan-out never reached both peers"
    assert sorted(calls) == ["blade", "whoart"]


def test_default_stays_synchronous(monkeypatch):
    calls, _ = _stub(monkeypatch)
    res = m.NouGenMsgBus.emit_fleet("hi", target="all")
    assert res["blade"] == "delivered" and res["whoart"] == "delivered"
    assert sorted(calls) == ["blade", "whoart"]


def test_background_failure_is_logged_not_raised(monkeypatch, capsys):
    monkeypatch.setattr(m, "get_current_node", lambda: "phoebus")
    monkeypatch.setattr(m.NouGenMsgBus, "live_ping",
                        classmethod(lambda cls, target, text, origin=None, **k: {"local": "ok"}))
    monkeypatch.setattr(m.NouGenMsgBus, "emit_node",
                        classmethod(lambda cls, node, target, text, origin=None: {node: "Error: TimeoutExpired"}))
    m.NouGenMsgBus.emit_fleet("hi", target="all", background=True)
    m.NouGenMsgBus._last_fanout_thread.join(5)
    assert "background fan-out to blade failed" in capsys.readouterr().err


def test_node_tools_request_background_fanout():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for name in ("nougenmsg", "fleet_send"):
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
        calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and ast.unparse(c.func).endswith("emit_fleet")]
        assert calls and all(any(k.arg == "background" for k in c.keywords) for c in calls), name
