"""ping_claude must survive wrong-shape entries in the nested "sessions" map.

A non-object entry (string, list, number) used to raise AttributeError at
``(entry or {}).get("token")`` before the Claude inbox fallback was written,
so the message was lost. Port of nougenmsg elev/cc-registry-shape (T48).
"""
import json

import pytest

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import AgentPinger


@pytest.fixture
def env(tmp_path, monkeypatch):
    reg = tmp_path / "cc_sessions.json"
    inbox = tmp_path / "inbox"
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: False)
    monkeypatch.setattr(nougenmsg, "_ping_seen_before", lambda *a, **k: False)
    monkeypatch.setattr(nougenmsg, "_ping_mark_delivered", lambda *a, **k: None)
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(reg)))
    monkeypatch.setattr(AgentPinger, "_claude_inbox_dir", staticmethod(lambda: str(inbox)))
    monkeypatch.setattr(AgentPinger, "_discover_claude_endpoints", staticmethod(lambda: []))
    return reg, inbox


@pytest.mark.parametrize("bad", ["a-string", ["list"], 7, True],
                         ids=lambda v: type(v).__name__)
def test_non_object_nested_entry_is_skipped(env, bad):
    reg, inbox = env
    reg.write_text(json.dumps({"sessions": {"sock-bad": bad}}), encoding="utf-8")
    out = AgentPinger.ping_claude("hello")
    assert out["delivered"] == []
    assert out["registered"] == 0
    assert out["inbox_file"] and (inbox / out["inbox_file"].split("\\")[-1].split("/")[-1]).exists()


@pytest.mark.parametrize("bad", ["a-string", ["list"], 7],
                         ids=lambda v: type(v).__name__)
def test_targeted_ping_with_non_object_entry_reports_not_found(env, monkeypatch, bad):
    reg, _ = env
    reg.write_text(json.dumps({"sessions": {"sock-bad": bad}}), encoding="utf-8")
    monkeypatch.setattr(AgentPinger, "_discover_claude_endpoints", staticmethod(lambda: ["sock-bad"]))
    out = AgentPinger.ping_claude("hello", target_session="sock-bad")
    assert out["error"] == "target_session_not_found"
    assert out["registered"] == 0
