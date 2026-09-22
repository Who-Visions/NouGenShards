"""A node-name target ('@blade') must reach that node's agent lanes.

Before the fix live_ping matched no family branch for a node name, so the
addressed node returned {} and the caller still reported "delivered".
"""
import nougen_shards.nougenmsg as m


def _stub_pingers(monkeypatch, calls):
    for name in ("ping_claude", "ping_codex"):
        monkeypatch.setattr(m.AgentPinger, name,
                            staticmethod(lambda *a, _n=name, **k: calls.append(_n) or "ok"))
    monkeypatch.setattr(m.AgentPinger, "ping_antigravity",
                        staticmethod(lambda *a, **k: calls.append("ping_antigravity") or "ok"))
    for name in ("ping_ollama", "ping_openrouter"):
        monkeypatch.setattr(m.AgentPinger, name,
                            staticmethod(lambda *a, _n=name, **k: calls.append(_n) or "ok"))


def test_own_node_target_pings_local_agent_lanes(monkeypatch):
    calls = []
    _stub_pingers(monkeypatch, calls)
    monkeypatch.setattr(m, "get_current_node", lambda: "blade")
    res = m.NouGenMsgBus.live_ping(target="blade", text="hi")
    assert set(res) == {"claude_pipes", "antigravity", "codex"}
    assert "ping_ollama" not in calls and "ping_openrouter" not in calls


def test_other_node_target_is_skipped_not_empty(monkeypatch):
    calls = []
    _stub_pingers(monkeypatch, calls)
    monkeypatch.setattr(m, "get_current_node", lambda: "phoebus")
    res = m.NouGenMsgBus.live_ping(target="blade", text="hi")
    assert res == {"skipped": "addressed to blade, not this node"}
    assert calls == []


def test_fleet_nodes_env_override(monkeypatch):
    calls = []
    _stub_pingers(monkeypatch, calls)
    monkeypatch.setenv("NOUGEN_FLEET_NODES", "blade,newbox")
    monkeypatch.setattr(m, "get_current_node", lambda: "newbox")
    res = m.NouGenMsgBus.live_ping(target="newbox", text="hi")
    assert "claude_pipes" in res


def test_coach_alias_targets_physical_machine(monkeypatch):
    calls = []
    _stub_pingers(monkeypatch, calls)
    monkeypatch.setattr(m, "get_current_node", lambda: "whoart")
    res = m.NouGenMsgBus.live_ping(target="hyperion", text="hi")
    assert set(res) == {"claude_pipes", "antigravity", "codex"}


def test_parse_destination_normalizes_coach_alias():
    assert m.NouGenMsgBus.parse_destination("@hyperion:codex") == ("whoart", "codex")
    assert m.NouGenMsgBus.parse_destination("@apollo") == ("blade", "all")


def test_origin_envelope_carries_coach_and_machine(monkeypatch):
    monkeypatch.setattr(m, "get_current_node", lambda: "whoart")
    envelope = m.NouGenMsgBus._origin_envelope()
    assert envelope["machine"] == "whoart"
    assert envelope["coach"] == "hyperion"
