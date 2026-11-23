"""A forwarded message with no sender machine is labelled from the TCP peer when it is a known fleet node."""
import json

import pytest

from nougen_shards import nougenmsg as bus

Bus = bus.NouGenMsgBus


@pytest.fixture(autouse=True)
def _hosts(tmp_path, monkeypatch):
    path = tmp_path / "fleet_hosts.json"
    path.write_text(json.dumps({"nodes": {"alpha": {"ip": "192.0.2.10", "host_patterns": ["alpha"]},
                                          "beta": {"host_patterns": ["beta"]}}}), encoding="utf-8")
    monkeypatch.setenv("NOUGEN_FLEET_HOSTS_FILE", str(path))
    monkeypatch.delenv("NOUGEN_NODE_BETA_IP", raising=False)
    bus.PEER.addr = ""
    yield
    bus.PEER.addr = ""


def test_known_lan_address_resolves_to_its_node():
    assert bus.node_for_peer("192.0.2.10") == "alpha"


def test_env_address_resolves_without_a_file_entry(monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE_BETA_IP", "192.0.2.20")
    assert bus.node_for_peer("192.0.2.20") == "beta"


@pytest.mark.parametrize("addr", ["127.0.0.1", "::1", "0.0.0.0", "", "not-an-ip", "192.0.2.99"])
def test_loopback_blank_and_unlisted_stay_unknown(addr):
    assert bus.node_for_peer(addr) is None


def test_forwarded_message_without_a_claim_takes_the_peer_node():
    bus.PEER.addr = "192.0.2.10"
    assert Bus._origin_envelope({"original_sender": "claude-app"}, forwarded=True)["machine"] == "alpha"


def test_a_claimed_machine_is_never_overridden_by_the_peer():
    bus.PEER.addr = "192.0.2.10"
    assert Bus._origin_envelope({"machine": "gamma"}, forwarded=True)["machine"] == "gamma"


def test_tunnel_loopback_stays_unknown_not_the_receiving_box():
    bus.PEER.addr = "127.0.0.1"
    assert Bus._origin_envelope({}, forwarded=True)["machine"] == "unknown"


def test_a_peer_address_inside_the_message_body_is_ignored():
    bus.PEER.addr = ""
    env = Bus._origin_envelope({"peer_addr": "192.0.2.10"}, forwarded=True)
    assert env["machine"] == "unknown"
