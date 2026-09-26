import os
from unittest.mock import patch
from nougen_shards.session_probe import (
    configured_fleet_peers,
    _fleet_pulse,
    run_hi,
)


def test_clean_stranger_install_has_zero_fleet_peers_by_default(monkeypatch):
    monkeypatch.delenv("NOUGEN_FLEET_PEERS", raising=False)
    peers = configured_fleet_peers()
    assert peers == [], "Fresh install must default to zero peers"
    
    pulse = _fleet_pulse()
    assert pulse == {}, "Fleet pulse must be empty when no peers are configured"


def test_configured_fleet_peers_override(monkeypatch):
    monkeypatch.setenv("NOUGEN_FLEET_PEERS", "worker1.local, worker2.local")
    peers = configured_fleet_peers()
    assert peers == ["worker1.local", "worker2.local"]


def test_clean_stranger_install_does_not_inherit_foreign_maintainer_handoffs(monkeypatch):
    # Stranger install identity
    stranger_identity = {
        "host": "stranger-laptop",
        "machine_id": "stranger-12345",
        "platform": "windows",
    }
    
    # Mock handoff feed containing maintainer handoffs from blade1tb / phoebus
    foreign_feed = [
        {
            "id": "20260926T160000Z__blade1tb__antigravity",
            "machine": "blade1tb",
            "goal": "Maintainer internal architecture sprint",
            "live_status": "in_progress",
        },
        {
            "id": "20260926T170000Z__phoebus__claude-cli",
            "machine": "phoebus",
            "goal": "Maintainer deployment test",
            "live_status": "in_progress",
        }
    ]
    
    monkeypatch.delenv("NOUGEN_HANDOFF_DIR", raising=False)
    monkeypatch.delenv("NOUGEN_FLEET_PEERS", raising=False)
    
    with patch("nougen_shards.machine.machine_identity", return_value=stranger_identity), \
         patch("nougen_shards.handoff.handoff_feed", return_value=foreign_feed), \
         patch("nougen_shards.session_probe.read_relay", return_value={"armed": False, "count": 0, "legs": []}):
        
        report = run_hi(fleet=True, isolate_clean=True)
        
        # Invariants for clean stranger:
        assert report.open_handoffs == 0, "Clean install must not count foreign maintainer handoffs as active"
        assert report.latest_goal is None, "Clean install must not present foreign maintainer goal as user goal"
        assert report.fleet_pulse == {}, "Clean install must have empty fleet pulse"
