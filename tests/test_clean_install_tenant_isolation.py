"""Clean-room tenant isolation regression tests."""

from __future__ import annotations

from nougen_shards import session_probe


def test_fleet_pulse_is_empty_without_enrollment(monkeypatch):
    monkeypatch.setattr(session_probe.nougenmsg, "_known_fleet_hosts", lambda: {})
    monkeypatch.setattr(session_probe.nougenmsg, "get_current_node", lambda: "standalone")

    called = []

    def forbidden_run(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("clean install must not probe inherited peers")

    monkeypatch.setattr(session_probe.subprocess, "run", forbidden_run)

    assert session_probe._fleet_pulse() == {}
    assert called == []


def test_hi_clean_install_does_not_read_inherited_handoffs_or_relay(monkeypatch):
    monkeypatch.setattr(session_probe, "_fleet_enrolled", lambda: False)
    monkeypatch.setattr(
        session_probe.machine,
        "machine_identity",
        lambda: {"host": "new-user-host", "machine_id": "new-user-id"},
    )
    monkeypatch.setattr(session_probe, "_check_port", lambda port: False)
    monkeypatch.setattr(session_probe, "usage_snapshot", lambda: {})

    def forbidden(*args, **kwargs):
        raise AssertionError("clean install must not read inherited fleet state")

    monkeypatch.setattr(session_probe.handoff, "handoff_feed", forbidden)
    monkeypatch.setattr(session_probe, "read_relay", forbidden)
    monkeypatch.setattr(session_probe, "_fleet_pulse", forbidden)

    report = session_probe.run_hi(fleet=True)

    assert report.identity["host"] == "new-user-host"
    assert report.open_handoffs == 0
    assert report.latest_goal is None
    assert report.fleet_pulse == {}
    assert report.relay_armed is False
    assert report.relay_open_count == 0
    assert report.relay_legs == []
    assert report.next_play is None


def test_hi_enrolled_install_uses_only_configured_peer_names(monkeypatch):
    monkeypatch.setattr(session_probe, "_fleet_enrolled", lambda: True)
    monkeypatch.setattr(
        session_probe.machine,
        "machine_identity",
        lambda: {"host": "node-a", "machine_id": "id-a"},
    )
    monkeypatch.setattr(session_probe.handoff, "handoff_feed", lambda limit=25: [])
    monkeypatch.setattr(session_probe, "_check_port", lambda port: False)
    monkeypatch.setattr(session_probe, "usage_snapshot", lambda: {})
    monkeypatch.setattr(session_probe, "_fleet_pulse", lambda: {"node-b": True})
    monkeypatch.setattr(
        session_probe,
        "read_relay",
        lambda: {"armed": True, "count": 0, "legs": []},
    )

    report = session_probe.run_hi(fleet=True)

    assert report.fleet_pulse == {"node-b": True}
    assert report.latest_goal is None


def test_federation_and_local_vault_default_machine_not_hardcoded(monkeypatch):
    """Default machine in federation and local_vault must derive dynamically, not hardcode blade1tb."""
    from unittest.mock import patch
    from nougen_shards import federation
    from nougen_shards.connectors import local_vault

    monkeypatch.delenv("NOUGEN_MACHINE_ID", raising=False)
    with patch("nougen_shards.machine.machine_id", return_value="custom-test-node"):
        assert federation.machine.machine_id() == "custom-test-node"
        assert local_vault.machine.machine_id() == "custom-test-node"

