"""Tests for truthful fleet pulse and expected-offline semantics (legs 20260926T205311Z & 20260926T205019Z)."""

import io
from unittest.mock import MagicMock, patch

from nougen_shards import cli, session_probe


def test_expected_offline_node_marked_resting_without_ssh(monkeypatch):
    monkeypatch.setattr(session_probe.nougenmsg, "_known_fleet_hosts", lambda: {"whoart.local", "blade1tb"})
    monkeypatch.setattr(session_probe.nougenmsg, "get_current_node", lambda: "phoebus")
    monkeypatch.setattr(session_probe, "_expected_offline_nodes", lambda: {"whoart", "whoart.local"})

    ssh_calls = []

    def mock_run(cmd, **kwargs):
        ssh_calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(session_probe.subprocess, "run", mock_run)

    pulse = session_probe._fleet_pulse()
    assert pulse["whoart.local"] == "resting"
    assert pulse["blade1tb"] is True

    # Confirm SSH was never called for whoart.local
    for call in ssh_calls:
        assert "whoart.local" not in call


def test_route_unreachable_distinguished_from_node_failure(monkeypatch):
    monkeypatch.setattr(session_probe.nougenmsg, "_known_fleet_hosts", lambda: {"remote.node"})
    monkeypatch.setattr(session_probe.nougenmsg, "get_current_node", lambda: "phoebus")
    monkeypatch.setattr(session_probe, "_expected_offline_nodes", lambda: set())

    def mock_run(cmd, **kwargs):
        return MagicMock(returncode=255)

    monkeypatch.setattr(session_probe.subprocess, "run", mock_run)

    pulse = session_probe._fleet_pulse()
    assert pulse["remote.node"] == "route_unreachable"


def test_cmd_hi_truthful_pulse_output(monkeypatch):
    report = session_probe.HiReport(
        identity={"host": "phoebus", "machine_id": "test"},
        local_time="2026-09-26 18:00 EDT",
        fleet_pulse={
            "blade": True,
            "whoart": "resting",
            "remote": "route_unreachable",
        },
    )
    monkeypatch.setattr(session_probe, "run_hi", lambda fleet=True: report)

    out = io.StringIO()
    with patch("sys.stdout", out):
        cli.cmd_hi(MagicMock(no_fleet=False, json=False))

    output = out.getvalue()
    assert "blade:up" in output
    assert "whoart:resting (expected offline)" in output
    assert "remote:route unreachable" in output
