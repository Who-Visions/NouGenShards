"""live_ping(models_async=True): model lanes answer in the background.

Regression for 2026-09-14: an @all node ping waited on the ollama/openrouter
model lanes (up to NOUGEN_MSG_MODEL_TIMEOUT_S=60s) and took 64.7s, while the
agent-lane-only @phoebus ping took 1.7s.
"""
import threading
import time

import nougen_shards.nougenmsg as m


def _stub(monkeypatch, delay=0.5):
    hits, done = [], threading.Event()
    monkeypatch.setenv("NOUGEN_MSG_MODEL_LANES_ON_ALL", "1")
    for name in ("ping_claude", "ping_codex"):
        monkeypatch.setattr(m.AgentPinger, name, staticmethod(lambda *a, _n=name, **k: hits.append(_n) or "ok"))
    monkeypatch.setattr(m.AgentPinger, "ping_antigravity", staticmethod(lambda *a, **k: hits.append("ping_antigravity") or "ok"))

    def slow(name):
        def f(*a, **k):
            time.sleep(delay)
            hits.append(name)
            if {"ping_ollama", "ping_openrouter"} <= set(hits):
                done.set()
            return {"status": "delivered"}
        return staticmethod(f)
    monkeypatch.setattr(m.AgentPinger, "ping_ollama", slow("ping_ollama"))
    monkeypatch.setattr(m.AgentPinger, "ping_openrouter", slow("ping_openrouter"))
    return hits, done


def test_models_async_returns_before_models_answer(monkeypatch):
    hits, done = _stub(monkeypatch)
    t0 = time.monotonic()
    res = m.NouGenMsgBus.live_ping(target="all", text="hi", models_async=True)
    assert time.monotonic() - t0 < 0.3
    assert res["ollama"] == {"queued": True, "via": "model"}
    assert res["openrouter"] == {"queued": True, "via": "model"}
    assert {"ping_claude", "ping_codex", "ping_antigravity"} <= set(hits)
    assert done.wait(5), "background model lanes never ran"


def test_default_waits_for_models(monkeypatch):
    hits, _ = _stub(monkeypatch, delay=0.05)
    res = m.NouGenMsgBus.live_ping(target="all", text="hi")
    assert res["ollama"] == {"status": "delivered"} and res["openrouter"] == {"status": "delivered"}


def test_emit_fleet_background_makes_models_async(monkeypatch):
    _stub(monkeypatch)
    monkeypatch.setattr(m, "get_current_node", lambda: "phoebus")
    monkeypatch.setattr(m.NouGenMsgBus, "emit_node", classmethod(lambda cls, node, target, text, origin=None: {node: "ok"}))
    t0 = time.monotonic()
    res = m.NouGenMsgBus.emit_fleet("hi", target="all", background=True)
    assert time.monotonic() - t0 < 0.3
    assert res["phoebus"]["ollama"] == {"queued": True, "via": "model"}
