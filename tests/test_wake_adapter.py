"""Tests for the optional wake layer.

Waking STARTS an agent where delivery only reaches a live one, so most of
these assert what must NOT happen. The important property is negative: a node
without adapters behaves exactly as it did before this layer existed.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))


def _purge_wake_modules():
    """Drop the wake package under EVERY import shape it can hold.

    It can be cached as "wake" or as "tools.wake" depending on what is on
    sys.path, and clearing only one leaves a module whose adapters were
    discovered under different conditions. That is how these tests passed on a
    machine where the runtime IS installed: the fixture missed the cached copy.
    """
    for name in [m for m in sys.modules
                 if m == "wake" or m.startswith(("wake.", "tools.wake"))]:
        del sys.modules[name]


@pytest.fixture()
def wake(monkeypatch):
    """The wake package with no adapter importable: the default everywhere."""
    monkeypatch.setenv("NOUGEN_WAKE_ANTIGRAVITY_BIN", "")
    monkeypatch.setattr("shutil.which", lambda *a, **k: None)
    _purge_wake_modules()
    return importlib.import_module("wake")


def test_no_adapters_is_a_valid_state(wake):
    """A node where nothing imports must not raise; it simply cannot wake."""
    assert wake.available() == []
    assert wake.enabled() is False


def test_unavailable_is_reported_not_silent(wake):
    """A silent no-op is indistinguishable from a broken scheme."""
    out = wake.wake("antigravity", "please start")
    assert out["attempted"] is False
    assert out["wake"] == "unavailable"
    assert out["detail"], "must say WHY nothing was available"


def test_status_explains_each_absence(wake):
    """Diagnosable without guessing which runtime is missing."""
    status = wake.status()
    assert status["available"] == []
    assert set(status["unavailable"]) == {"antigravity"}
    assert all(isinstance(v, str) and v for v in status["unavailable"].values())


def test_availability_cannot_be_switched_on_by_configuration(wake, monkeypatch):
    """Detection, never configuration: no env var conjures a missing adapter."""
    for var in ("NOUGEN_WAKE", "NOUGEN_WAKE_ENABLED", "NOUGEN_WAKE_FORCE"):
        monkeypatch.setenv(var, "1")
    assert wake.enabled() is False
    assert wake.wake("all", "x")["attempted"] is False


def test_disable_switch_works_even_where_adapters_exist(wake, monkeypatch):
    """The only switch that exists turns waking OFF, never on."""
    monkeypatch.setattr(wake, "_ADAPTERS", [object()])
    assert wake.enabled() is True
    monkeypatch.setenv("NOUGEN_WAKE_DISABLED", "1")
    assert wake.enabled() is False


class _FakeAdapter:
    name = "antigravity"
    aliases = ("agy",)

    def __init__(self, idle=True, raises=False):
        self._idle, self._raises, self.calls = idle, raises, []

    def is_idle(self):
        return self._idle

    def wake(self, text, event):
        if self._raises:
            raise RuntimeError("adapter exploded")
        self.calls.append(text)
        return {"woken": True, "leg_id": event.get("leg_id")}


def test_busy_agent_is_not_interrupted(wake, monkeypatch):
    """A missed wake is retried next poll; an interrupted turn is not recoverable."""
    adapter = _FakeAdapter(idle=False)
    monkeypatch.setattr(wake, "_ADAPTERS", [adapter])
    out = wake.wake("antigravity", "hello")
    assert out["results"]["antigravity"]["woken"] is False
    assert adapter.calls == []


def test_adapter_exception_never_escapes(wake, monkeypatch):
    """A failing adapter degrades to a report, never a 500 on the receiver."""
    monkeypatch.setattr(wake, "_ADAPTERS", [_FakeAdapter(raises=True)])
    out = wake.wake("antigravity", "hello")
    assert out["results"]["antigravity"]["woken"] is False
    assert "error" in out["results"]["antigravity"]


def test_target_must_match_an_adapter(wake, monkeypatch):
    monkeypatch.setattr(wake, "_ADAPTERS", [_FakeAdapter()])
    assert wake.wake("nonexistent", "x")["attempted"] is False
    assert wake.wake("agy", "x")["attempted"] is True       # alias
    assert wake.wake("all", "x")["attempted"] is True


@pytest.fixture()
def node(monkeypatch):
    """The receiver module, with the wake layer absent (the default node)."""
    _purge_wake_modules()
    for name in [m for m in sys.modules if m.startswith("nougenmsg_node")]:
        del sys.modules[name]
    monkeypatch.setattr("shutil.which", lambda *a, **k: None)
    return importlib.import_module("nougenmsg_node")


APPROVED = {"attempted": True, "kaedra_approved": True, "reason_code": "ok"}
OWNER = {"attempted": True, "origin": "user_verified", "kaedra_approved": None}
DENIED = {"attempted": True, "kaedra_approved": False, "reason_code": "injection_detected"}


def test_denied_message_never_wakes(node, monkeypatch):
    """Waking must not be a route around a judgment delivery had to satisfy."""
    monkeypatch.setattr(node, "_wake_enabled", lambda: True)
    monkeypatch.setattr(node, "_wake_dispatch", lambda *a, **k: {"attempted": True})
    out = node._maybe_wake({"text": "x", "wake_target": "agy"}, DENIED)
    assert out["attempted"] is False
    assert out["wake"] == "not approved"


def test_approved_but_no_target_does_not_wake(node, monkeypatch):
    """An ordinary approved status ping must never start an agent."""
    monkeypatch.setattr(node, "_wake_enabled", lambda: True)
    monkeypatch.setattr(node, "_wake_dispatch", lambda *a, **k: {"attempted": True})
    assert node._maybe_wake({"text": "all good"}, APPROVED)["wake"] == "no target"


@pytest.mark.parametrize("verdict", [APPROVED, OWNER])
def test_approved_with_target_dispatches(node, monkeypatch, verdict):
    seen = {}
    monkeypatch.setattr(node, "_wake_enabled", lambda: True)
    monkeypatch.setattr(node, "_wake_dispatch",
                        lambda t, text, msg: seen.update(target=t, text=text) or {"ok": True})
    node._maybe_wake({"text": "go", "wake_target": "agy"}, verdict)
    assert seen == {"target": "agy", "text": "go"}


def test_node_without_adapters_reports_unavailable(node):
    """THE REGRESSION CONTROL: a node with no adapters is unchanged in behaviour
    and says so explicitly rather than silently skipping."""
    out = node._maybe_wake({"text": "go", "wake_target": "agy"}, APPROVED)
    assert out["attempted"] is False
    assert out["wake"] == "unavailable"
    assert "available" in out and out["available"] == []
