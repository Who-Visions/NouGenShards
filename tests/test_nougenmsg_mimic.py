"""Unit tests for Claude Code cross-session messaging parity in NouGenMsgBus."""
import json
import time

from nougen_shards.nougenmsg import NouGenMsgBus


def test_list_agents_structured_returns_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(NouGenMsgBus, "list_peers", classmethod(lambda cls: {
        "current_node": "whoart",
        "claude_active_pipes": [r"\\.\pipe\LOCAL\cc-msg-test1"],
        "antigravity_active_pipes": [r"\\.\pipe\LOCAL\agy-msg-antigravity"],
        "codex_pipe": {"status": "listening"},
        "antigravity_inbox_unread": 0,
        "codex_inbox_unread": 0,
        "nodes_reachable": ["whoart", "blade", "phoebus"]
    }))
    agents = NouGenMsgBus.list_agents_structured()
    assert len(agents) >= 4
    names = [a["name"] for a in agents]
    assert any("claude" in n for n in names)
    assert any("antigravity" in n for n in names)
    assert any("blade" in n for n in names)
    assert any("phoebus" in n for n in names)

    for a in agents:
        assert "kind" in a
        assert "node" in a
        assert "capabilities" in a


def test_inbound_policy_lifecycle(tmp_path, monkeypatch):
    cfg_path = tmp_path / "messaging_config.json"
    monkeypatch.setattr(NouGenMsgBus, "_config_path", staticmethod(lambda: str(cfg_path)))

    # Default
    policy = NouGenMsgBus.get_inbound_policy()
    assert policy["crossSessionInbound"] == "accept"
    assert policy["isolatePeerMachines"] is False

    # Set hold
    updated = NouGenMsgBus.set_inbound_policy("hold", isolate_peer_machines=True, dialog_expiry_seconds=120)
    assert updated["crossSessionInbound"] == "hold"
    assert updated["isolatePeerMachines"] is True
    assert updated["dialogExpirySeconds"] == 120

    # Persistence check
    persisted = NouGenMsgBus.get_inbound_policy()
    assert persisted["crossSessionInbound"] == "hold"
    assert persisted["isolatePeerMachines"] is True


def test_idle_subscription_and_one_shot_emit(tmp_path, monkeypatch):
    subs_path = tmp_path / "idle_subscriptions.json"
    monkeypatch.setattr(NouGenMsgBus, "_idle_subs_path", staticmethod(lambda: str(subs_path)))
    monkeypatch.setattr(NouGenMsgBus, "live_ping", classmethod(lambda cls, target, text, origin: {"delivered": True, "target": target}))

    # 1. Subscribe
    sub = NouGenMsgBus.subscribe_idle(subscriber_session="sess-alpha", target="db-migration")
    assert sub["target"] == "db-migration"
    assert len(NouGenMsgBus.list_idle_subscriptions()) == 1

    # 2. Emit matching
    dispatched = NouGenMsgBus.emit_idle("db-migration", status_summary="tables created")
    assert len(dispatched) == 1
    assert dispatched[0]["subscription"]["subscriber_session"] == "sess-alpha"

    # 3. Verify one-shot drain
    assert len(NouGenMsgBus.list_idle_subscriptions()) == 0


def test_idle_subscription_expiration(tmp_path, monkeypatch):
    subs_path = tmp_path / "idle_subscriptions.json"
    monkeypatch.setattr(NouGenMsgBus, "_idle_subs_path", staticmethod(lambda: str(subs_path)))

    # Store expired subscription
    expired_record = {
        "id": "expired-1",
        "subscriber_session": "sess-old",
        "target": "worker",
        "expires_at": time.time() - 100,
        "expires_utc": "2026-01-01T00:00:00Z"
    }
    subs_path.write_text(json.dumps([expired_record]), encoding="utf-8")

    # Listing cleans expired entries
    active = NouGenMsgBus.list_idle_subscriptions()
    assert len(active) == 0
