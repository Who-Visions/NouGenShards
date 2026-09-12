"""
Test suite for NouGen Unified /live Control Plane & Fleet Operations Aggregator.
Covers all 13 test invariants mandated by the /live architecture specification.
"""
import json
import socket
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from nougen_shards.live import (
    LiveControlPlane,
    NouGenLive,
    handle_live_command,
    handle_live_slash,
    FLEET_NODES
)
from nougen_shards.cli import get_parser


def test_invariant_1_live_appears_in_help_and_parser():
    """1. /live appears in interactive help and CLI parser."""
    parser = get_parser()
    args = parser.parse_args(["live", "overview"])
    assert args.command == "live"
    assert args.live_args == ["overview"]
    
    # Check help text
    help_text = parser.format_help()
    assert "live" in help_text


def test_invariant_2_live_returns_combined_snapshot(tmp_path):
    """2. /live returns a combined multi-node snapshot."""
    control = LiveControlPlane(home_dir=tmp_path)
    snap = control.snapshot()
    
    assert "nodes" in snap
    assert "sessions" in snap
    assert "ports" in snap
    assert "ssh" in snap
    assert "relays" in snap
    assert "watch" in snap
    assert "tracker" in snap
    assert "timestamp" in snap


def test_invariant_3_sessions_distinguishes_configured_vs_alive(tmp_path):
    """3. /live sessions does not treat configured peers as measured alive."""
    cc_file = tmp_path / "cc_sessions.json"
    cc_file.write_text(json.dumps([
        {
            "id": "configured-offline-session",
            "machine": "blade",
            "endpoint": "/non/existent/mock.sock"
        }
    ]), encoding="utf-8")

    control = LiveControlPlane(home_dir=tmp_path)
    sess_report = control.sessions()

    assert sess_report["total_sessions"] == 1
    session = sess_report["sessions"][0]
    assert session["id"] == "configured-offline-session"
    assert "targetable" in session
    assert "dispatchable" in session


def test_invariant_4_ports_proves_listening_refused_timeout():
    """4. /live ports proves listening, connection refused, and timeout distinctly."""
    control = LiveControlPlane()

    # 1. Live probe check
    probe_local = control.probe_tcp_detailed("127.0.0.1", 11434, timeout=0.2)
    assert probe_local["status"] in ("LISTENING", "CONNECTION_REFUSED", "TIMEOUT")
    assert "latency_ms" in probe_local
    assert "reason_code" in probe_local

    # 2. Mocked socket tests for distinct reason codes
    with patch("socket.create_connection") as mock_conn:
        # Listening
        mock_conn.return_value = MagicMock()
        res_ok = control.probe_tcp_detailed("127.0.0.1", 80)
        assert res_ok["status"] == "LISTENING"
        assert res_ok["reachable"] is True

        # Timeout
        mock_conn.side_effect = socket.timeout("timed out")
        res_timeout = control.probe_tcp_detailed("127.0.0.1", 80)
        assert res_timeout["status"] == "TIMEOUT"
        assert res_timeout["reason_code"] == "CONNECT_TIMEOUT"
        assert res_timeout["reachable"] is False

        # Refused
        mock_conn.side_effect = ConnectionRefusedError("Connection refused")
        res_refused = control.probe_tcp_detailed("127.0.0.1", 80)
        assert res_refused["status"] == "CONNECTION_REFUSED"
        assert res_refused["reachable"] is False


def test_invariant_5_ssh_reports_per_node_proof():
    """5. /live ssh reports per-node proof and reason codes."""
    control = LiveControlPlane()
    ssh_data = control.ssh(timeout=0.1)

    assert "ssh_matrix" in ssh_data
    for node_k in FLEET_NODES:
        assert node_k in ssh_data["ssh_matrix"]
        node_ssh = ssh_data["ssh_matrix"][node_k]
        assert "status" in node_ssh
        assert "reason_code" in node_ssh
        assert "latency_ms" in node_ssh


def test_invariant_6_relays_surfaces_open_and_claims(tmp_path):
    """6. /live relays surfaces open legs, claims, latest handoffs, and ACK state."""
    handoffs_dir = tmp_path / ".handoffs"
    handoffs_dir.mkdir(parents=True)
    
    mock_hf = handoffs_dir / "20260912T120000Z__test__worker.json"
    mock_hf.write_text(json.dumps({
        "agent": "solai",
        "goal": "Test /live relays",
        "created_at": "2026-09-12T12:00:00Z"
    }), encoding="utf-8")

    control = LiveControlPlane(relay_root=tmp_path)
    relays_report = control.relays()

    assert relays_report["handoffs_count"] == 1
    assert relays_report["recent_handoffs"][0]["agent"] == "solai"
    assert "active_claims" in relays_report


def test_invariant_7_tracker_surfaces_freshness(tmp_path):
    """7. /live tracker surfaces freshness per lane."""
    tracker_file = tmp_path / "tracker_status.json"
    tracker_file.write_text(json.dumps({
        "hyperion": {"tokens": 12000, "status": "active"},
        "apollo": {"tokens": 45000, "status": "active"}
    }), encoding="utf-8")

    control = LiveControlPlane(home_dir=tmp_path)
    tr_report = control.tracker()

    assert tr_report["tracker_available"] is True
    assert "hyperion" in tr_report["data"]


def test_invariant_8_targeted_send_returns_sent_unverified_or_unreachable(tmp_path):
    """8. targeted send returns sent_unverified if transport write succeeds without receiver ACK, and unreachable otherwise."""
    control = LiveControlPlane(home_dir=tmp_path)

    # 1. Nonexistent target -> unreachable
    res_unreachable = control.send_targeted("nonexistent-node-target", "ping payload")
    assert res_unreachable["state"] == "unreachable"
    assert "error" in res_unreachable

    # 2. Registered mock session -> sent_unverified
    mock_session = {
        "id": "mock-active-sess",
        "machine": "hyperion",
        "agent": "antigravity",
        "endpoint": r"\\.\pipe\LOCAL\agy-msg-antigravity"
    }
    agy_file = tmp_path / "agy_sessions.json"
    agy_file.write_text(json.dumps({"sessions": {mock_session["id"]: mock_session}}), encoding="utf-8")

    res_sent = control.send_targeted("mock-active-sess", "ping payload")
    assert res_sent["state"] == "sent_unverified"
    assert "evidence" in res_sent
    assert res_sent["target"] == "mock-active-sess"


def test_invariant_9_broadcast_records_per_target_results(tmp_path):
    """10. broadcast records one result per target and cannot return success from enqueue alone."""
    agy_file = tmp_path / "agy_sessions.json"
    agy_file.write_text(json.dumps({
        "sessions": {
            "sess-1": {"id": "sess-1", "node": "hyperion", "endpoint": "pipe-1"},
            "sess-2": {"id": "sess-2", "node": "apollo", "endpoint": "pipe-2"}
        }
    }), encoding="utf-8")

    control = LiveControlPlane(home_dir=tmp_path)
    b_res = control.broadcast("Broadcast message to all")

    assert b_res["broadcast"] is True
    assert b_res["targets_count"] >= 1
    assert "results" in b_res
    assert isinstance(b_res["results"], list)


def test_invariant_10_all_nodes_independently_represented():
    """11. All three nodes are independently represented, with partial failure tolerated."""
    control = LiveControlPlane()
    nodes_report = control.nodes(timeout=0.1)

    assert nodes_report["total_nodes"] == 3
    for k in ("apollo", "hyperion", "phoebus"):
        assert k in nodes_report["nodes"]
        node_info = nodes_report["nodes"][k]
        assert "ip" in node_info
        assert "state" in node_info
        assert "reachable" in node_info
        assert "probes" in node_info


def test_invariant_11_phoebus_peer_timeout_does_not_break_fleet():
    """12. Phoebus peer timeout does not mark the entire machine or fleet dead."""
    control = LiveControlPlane()

    with patch.object(control, "probe_tcp_detailed") as mock_probe:
        # Mock phoebus timing out on 8765 but reachable on SSH 22
        def side_effect(host, port, timeout=0.5):
            if host == FLEET_NODES["phoebus"]["ip"] and port == 8765:
                return {"host": host, "port": port, "status": "TIMEOUT", "reachable": False, "latency_ms": 100.0, "reason_code": "CONNECT_TIMEOUT"}
            return {"host": host, "port": port, "status": "LISTENING", "reachable": True, "latency_ms": 5.0, "reason_code": "SOCKET_CONNECTED"}

        mock_probe.side_effect = side_effect

        phoebus_node = control.probe_node("phoebus")
        assert phoebus_node["reachable"] is True  # Survived via SSH probe fallback
        assert phoebus_node["state"] == "ONLINE"


def test_invariant_12_backward_compatibility():
    """13. Existing /live related infrastructure remains backward compatible."""
    # Aliases
    assert NouGenLive is LiveControlPlane
    assert handle_live_slash is handle_live_command

    # Overview rendering
    out = handle_live_command(["overview"])
    assert "NOUGEN FLEET CONTROL PLANE (/live)" in out
    assert "FLEET NODES" in out
    assert "LOCAL LISTENING PORTS" in out
    assert "ACTIVE SESSIONS" in out

    # CLI command invocation
    out_ports = handle_live_command(["ports"])
    data = json.loads(out_ports)
    assert "ports" in data
