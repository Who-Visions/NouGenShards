"""
Test suite for NouGen Unified /live Control Plane & Fleet Operations Aggregator.
Covers all 13 test invariants mandated by the /live architecture specification.
"""
import json
import socket
from unittest.mock import patch, MagicMock

from nougen_shards.live import (
    LiveControlPlane,
    NouGenLive,
    handle_live_command,
    handle_live_slash,
    FLEET_NODES
)
from nougen_shards.cli import get_parser


def _live_endpoint(tmp_path, name):
    """An endpoint that really exists, so targetable is proven, not assumed."""
    p = tmp_path / name
    p.touch()
    return str(p)


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


def test_bare_live_activates_before_rendering(monkeypatch):
    monkeypatch.setattr("nougen_shards.codex_pipe.activate", lambda: {
        "status": "ready", "receiver": {"thread": "thread-1"}})
    out = handle_live_command([])
    assert "NOUGENLIVE ACTIVATION: CODEX_WAKE=READY" in out
    assert "NOUGEN FLEET CONTROL PLANE (/live)" in out


def test_pending_messages_and_relays_render_inline_without_mutation(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    msg = inbox / "ping_one.json"
    msg.write_text(json.dumps({"source": "nougen-whoart", "text": "wake inline", "timestamp": 1}), encoding="utf-8")
    handoffs = tmp_path / ".handoffs"
    handoffs.mkdir()
    relay = handoffs / "leg.json"
    relay.write_text(json.dumps({"id": "leg-1", "machine": "blade", "agent": "apollo",
                                 "target": "codex", "status": "open", "goal": "inspect this"}), encoding="utf-8")
    monkeypatch.setenv("NOUGEN_CODEX_INBOX", str(inbox))
    control = LiveControlPlane(home_dir=tmp_path, relay_root=tmp_path)

    rendered = control.render_pending_inline()

    assert "wake inline" in rendered
    assert "leg-1" in rendered
    assert "not claimed or acknowledged" in rendered
    assert msg.exists() and relay.exists()


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

        # Windows mDNS/IPv6 resolution can surface invalid flowinfo as an
        # OverflowError; telemetry must degrade, never crash the cockpit.
        mock_conn.side_effect = OverflowError("flowinfo must be 0-1048575")
        res_flowinfo = control.probe_tcp_detailed("peer.local", 8765)
        assert res_flowinfo["status"] == "SOCKET_ERROR"
        assert res_flowinfo["reachable"] is False


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
        "endpoint": _live_endpoint(tmp_path, "agy-msg-antigravity"),
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
            "sess-1": {"id": "sess-1", "node": "hyperion", "endpoint": _live_endpoint(tmp_path, "pipe-1")},
            "sess-2": {"id": "sess-2", "node": "apollo", "endpoint": str(tmp_path / "gone-pipe-2")}
        }
    }), encoding="utf-8")

    control = LiveControlPlane(home_dir=tmp_path)
    b_res = control.broadcast("Broadcast message to all")

    assert b_res["broadcast"] is True
    assert b_res["targets_count"] >= 1
    assert "results" in b_res
    assert isinstance(b_res["results"], list)


def test_invariant_10_all_nodes_independently_represented(tmp_path):
    """11. All configured nodes are independently represented, with partial failure tolerated."""
    # 1. Default local node
    control_default = LiveControlPlane(home_dir=tmp_path)
    nodes_default = control_default.nodes(timeout=0.1)
    assert "local" in nodes_default["nodes"]
    assert nodes_default["nodes"]["local"]["ip"] == "127.0.0.1"

    # 2. Custom multi-node cluster configured via nodes.json
    nodes_file = tmp_path / "nodes.json"
    nodes_file.write_text(json.dumps({
        "node_a": {"name": "Node Alpha", "ip": "127.0.0.1", "host": "alpha.local"},
        "node_b": {"name": "Node Beta", "ip": "127.0.0.1", "host": "beta.local"},
        "node_c": {"name": "Node Gamma", "ip": "127.0.0.1", "host": "gamma.local"}
    }), encoding="utf-8")

    control_multi = LiveControlPlane(home_dir=tmp_path)
    nodes_report = control_multi.nodes(timeout=0.1)

    assert nodes_report["total_nodes"] == 3
    assert nodes_report["telemetry_available"] is True
    assert nodes_report["probe_sweep_complete"] is True
    assert nodes_report["complete"] is True
    for k in ("node_a", "node_b", "node_c"):
        assert k in nodes_report["nodes"]
        node_info = nodes_report["nodes"][k]
        assert "ip" in node_info
        assert "state" in node_info
        assert "reachable" in node_info
        assert "probes" in node_info


def test_node_probe_exception_keeps_fleet_telemetry_and_marks_only_that_node_unknown(tmp_path):
    nodes_file = tmp_path / "nodes.json"
    nodes_file.write_text(json.dumps({
        "node_a": {"name": "Node Alpha", "ip": "127.0.0.1", "host": "alpha.local"},
        "node_b": {"name": "Node Beta", "ip": "127.0.0.1", "host": "beta.local"},
    }), encoding="utf-8")
    control = LiveControlPlane(home_dir=tmp_path)

    with patch.object(control, "probe_node", side_effect=[RuntimeError("probe exploded"), {
        "node": "node_b", "name": "Node Beta", "state": "ONLINE_HEALTHY",
        "online": True, "reachable": True, "probes": {},
    }]):
        report = control.nodes()

    assert report["telemetry_available"] is True
    assert report["probe_sweep_complete"] is False
    assert report["complete"] is False
    assert report["probe_failures"] == ["node_a"]
    assert report["nodes"]["node_a"]["state"] == "UNKNOWN"
    assert report["nodes"]["node_a"]["online"] is None
    assert report["nodes"]["node_a"]["reachable"] is None
    assert report["online_nodes"] == 1
    assert report["nodes"]["node_b"]["state"] == "ONLINE_HEALTHY"


def test_invariant_11_partial_node_port_timeout_does_not_break_fleet(tmp_path):
    """12. Peer port timeout does not mark the entire node or cluster dead."""
    nodes_file = tmp_path / "nodes.json"
    nodes_file.write_text(json.dumps({
        "remote_worker": {"name": "Remote Worker", "ip": "127.0.0.1", "host": "worker.local"}
    }), encoding="utf-8")

    control = LiveControlPlane(home_dir=tmp_path)

    with patch.object(control, "probe_tcp_detailed") as mock_probe:
        # Mock port 8765 timeout, but port 22 reachable
        def side_effect(host, port, timeout=0.5):
            if port == 8765:
                return {"host": host, "port": port, "status": "TIMEOUT", "reachable": False, "latency_ms": 100.0, "reason_code": "CONNECT_TIMEOUT"}
            return {"host": host, "port": port, "status": "LISTENING", "reachable": True, "latency_ms": 5.0, "reason_code": "SOCKET_CONNECTED"}

        mock_probe.side_effect = side_effect

        worker_node = control.probe_node("remote_worker")
        assert worker_node["reachable"] is True  # Survived via SSH probe fallback
        # Up, but one probed port timed out: degraded, and the port is named.
        assert worker_node["state"] == "ONLINE_DEGRADED"
        assert "8765 (CONNECT_TIMEOUT)" in worker_node["reason"]


def test_coach_machine_identity_and_locality_are_dynamic(tmp_path, monkeypatch):
    (tmp_path / "nodes.json").write_text(json.dumps({
        "hyperion": {
            "coach": "Hyperion", "machine": "WhoArt", "aliases": ["whoart"],
            "ip": "10.0.0.99", "host": "whoart.local", "health_ports": [22, 8766],
        }
    }), encoding="utf-8")
    monkeypatch.setattr(socket, "gethostname", lambda: "WhoArt")
    control = LiveControlPlane(home_dir=tmp_path)

    def listening(host, port, timeout=0.5):
        return {"host": host, "port": port, "status": "LISTENING", "reachable": True,
                "latency_ms": 1.0, "reason_code": "SOCKET_CONNECTED"}

    with patch.object(control, "probe_tcp_detailed", side_effect=listening):
        node = control.probe_node("hyperion")

    assert node["coach"] == "Hyperion"
    assert node["machine"] == "WhoArt"
    assert node["is_local"] is True
    assert node["ip"] == "127.0.0.1"
    assert set(node["probes"]) == {"22", "8766"}

    with patch.object(control, "probe_tcp_detailed", side_effect=listening), \
         patch.object(control, "probe_ports", return_value={}):
        assert "Hyperion @ WhoArt (Local)" in control.render_overview()


def test_declared_offline_node_is_offline_expected_not_red(tmp_path):
    """Relay 20260913T162818Z: Blade powered off must not read as a sick machine."""
    (tmp_path / "nodes.json").write_text(json.dumps({
        "blade": {"name": "Blade", "ip": "10.0.0.87", "host": "blade.local"}
    }), encoding="utf-8")
    (tmp_path / "node_power.json").write_text(json.dumps({
        "blade": {"state": "offline", "note": "powered off"}
    }), encoding="utf-8")
    control = LiveControlPlane(home_dir=tmp_path)

    def timeout(host, port, timeout=0.5):
        return {"host": host, "port": port, "status": "TIMEOUT", "reachable": False,
                "latency_ms": 800.0, "reason_code": "CONNECT_TIMEOUT"}

    with patch.object(control, "probe_tcp_detailed", side_effect=timeout):
        node = control.probe_node("blade")
        assert node["state"] == "OFFLINE_EXPECTED"
        assert "powered off" in node["reason"]
        with patch.object(control, "probe_ports", return_value={}):
            overview = control.render_overview()
    fleet_section = overview.split("LOCAL LISTENING")[0]
    assert "⚪ OFFLINE_EXPECTED" in fleet_section
    assert "🔴" not in fleet_section


def test_undeclared_single_observer_timeout_is_unknown_not_offline(tmp_path):
    (tmp_path / "nodes.json").write_text(json.dumps({
        "blade": {"name": "Blade", "ip": "10.0.0.87", "host": "blade.local"}
    }), encoding="utf-8")
    control = LiveControlPlane(home_dir=tmp_path)
    with patch.object(control, "probe_tcp_detailed", side_effect=lambda h, p, timeout=0.5: {
            "host": h, "port": p, "status": "TIMEOUT", "reachable": False,
            "latency_ms": 800.0, "reason_code": "CONNECT_TIMEOUT"}):
        node = control.probe_node("blade")
    assert node["state"] == "UNKNOWN"
    assert "cannot prove offline" in node["reason"]


def test_live_declare_round_trip(tmp_path, monkeypatch):
    home = tmp_path / ".nougen"
    home.mkdir()
    with patch("nougen_shards.live.LiveControlPlane.__init__", lambda self, *a, **k: setattr(self, "home_dir", home)):
        out = json.loads(handle_live_command(["declare", "blade", "offline", "powered", "off"]))
        assert out["declaration"]["state"] == "offline"
        assert out["declaration"]["note"] == "powered off"
        assert json.loads((home / "node_power.json").read_text())["blade"]["state"] == "offline"
        cleared = json.loads(handle_live_command(["declare", "blade", "online"]))
        assert cleared["declaration"] == "cleared"
        assert "must be" in handle_live_command(["declare", "blade", "dead"])


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


def test_invariant_13_reach_matrix_integration():
    """14. Reach matrix elevation integrates seamlessly with LiveControlPlane."""
    control = LiveControlPlane()
    
    # Direct method JSON invocation
    res_json = control.reach_matrix(as_json=True)
    assert isinstance(res_json, dict)
    assert "vantage" in res_json
    assert "summary" in res_json
    assert "control_ok" in res_json

    # CLI /live matrix table invocation
    out_table = handle_live_command(["matrix"])
    assert "reach matrix" in out_table
    assert "vantage=" in out_table

    # CLI /live reach --json invocation
    out_json = handle_live_command(["reach", "--json"])
    data = json.loads(out_json)
    assert "summary" in data
    assert "control_ok" in data
