"""Hermetic regression tests for clean install isolation.

Ensures that a fresh clean install of NouGen on an arbitrary user's computer:
1. Defaults to zero fleet peers (no maintainer-specific host literals).
2. Inherits zero operational history or maintainer handoff goals unless explicitly configured.
3. Preserves multi-tenant product boundaries.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from nougen_shards import session_probe, machine


def test_clean_install_defaults_to_zero_fleet_peers(monkeypatch):
    monkeypatch.delenv("NOUGEN_FLEET_PEERS", raising=False)
    peers = session_probe.configured_fleet_peers()
    assert peers == []

    pulse = session_probe._fleet_pulse()
    assert pulse == {}
    assert "blade1tb" not in pulse
    assert "whoart" not in pulse


def test_explicit_fleet_peers_honored(monkeypatch):
    monkeypatch.setenv("NOUGEN_FLEET_PEERS", "node-alpha, node-beta")
    peers = session_probe.configured_fleet_peers()
    assert peers == ["node-alpha", "node-beta"]


def test_fresh_stranger_install_isolates_maintainer_handoff_goals(monkeypatch, tmp_path):
    monkeypatch.delenv("NOUGEN_FLEET_PEERS", raising=False)
    monkeypatch.delenv("NOUGEN_HANDOFF_DIR", raising=False)

    # Mock machine identity to simulate a fresh external stranger's machine
    stranger_identity = {
        "host": "stranger-laptop",
        "machine_id": "stranger-uuid-9999",
        "os": "Windows",
        "arch": "AMD64"
    }

    # Foreign maintainer handoff feed items
    foreign_feed = [
        {
            "id": "20260926T120000Z_blade1tb_main",
            "timestamp": "2026-09-26T12:00:00Z",
            "agent": "gemini",
            "machine": "blade1tb",
            "branch": "main",
            "goal": "Internal Maintainer Fleet Maintenance Objective",
            "status": "open",
            "live_status": "open",
        },
        {
            "id": "20260926T130000Z_whoart_main",
            "timestamp": "2026-09-26T13:00:00Z",
            "agent": "claude",
            "machine": "whoart",
            "branch": "main",
            "goal": "Internal Maintainer Art Pipeline Objective",
            "status": "open",
            "live_status": "open",
        }
    ]

    with patch("nougen_shards.machine.machine_identity", return_value=stranger_identity):
        with patch("nougen_shards.handoff.handoff_feed", return_value=foreign_feed):
            with patch("nougen_shards.session_probe.read_relay", return_value={"armed": False, "count": 0, "legs": []}):
                report = session_probe.run_hi(fleet=True, isolate_clean=True)

                # The stranger must see clean slate
                assert report.open_handoffs == 0
                assert report.latest_goal is None
                assert report.fleet_pulse == {}
                assert report.identity["host"] == "stranger-laptop"


def test_explicit_handoff_dir_allows_shared_handoff_access(monkeypatch, tmp_path):
    monkeypatch.delenv("NOUGEN_FLEET_PEERS", raising=False)
    monkeypatch.setenv("NOUGEN_HANDOFF_DIR", str(tmp_path))

    stranger_identity = {
        "host": "stranger-laptop",
        "machine_id": "stranger-uuid-9999",
        "os": "Windows",
        "arch": "AMD64"
    }

    shared_feed = [
        {
            "id": "20260926T140000Z_custom",
            "timestamp": "2026-09-26T14:00:00Z",
            "agent": "gemini",
            "machine": "custom-node",
            "goal": "Explicitly Shared Project Objective",
            "status": "open",
            "live_status": "open",
        }
    ]

    with patch("nougen_shards.machine.machine_identity", return_value=stranger_identity):
        with patch("nougen_shards.handoff.handoff_feed", return_value=shared_feed):
            with patch("nougen_shards.session_probe.read_relay", return_value={"armed": False, "count": 0, "legs": []}):
                report = session_probe.run_hi(fleet=True, isolate_clean=True)

                # Explicit NOUGEN_HANDOFF_DIR was set -> shared feed is preserved
                assert report.open_handoffs == 1
                assert report.latest_goal == "Explicitly Shared Project Objective"
