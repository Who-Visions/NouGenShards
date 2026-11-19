"""Sender identity is resolved at run time, never trusted from the caller."""
import pytest

from nougen_shards import machine, nougenmsg


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for fn in (machine.hostname, machine.host_label, machine.machine_id, machine.sender_identity):
        fn.cache_clear()
    for var in ("NOUGEN_NODE", "NOUGEN_MACHINE", "NOUGEN_MACHINE_ID", "NOUGEN_FLEET_NODE"):
        monkeypatch.delenv(var, raising=False)
    yield
    for fn in (machine.hostname, machine.host_label, machine.machine_id, machine.sender_identity):
        fn.cache_clear()


@pytest.mark.parametrize("system,host", [
    ("Windows", "TESTBOX-WIN"), ("Darwin", "testbox-mac.local"), ("Linux", "testbox-linux.lan"),
])
def test_probe_path_per_os(monkeypatch, system, host):
    monkeypatch.setattr(machine.socket, "gethostname", lambda: host)
    monkeypatch.setattr(machine.platform, "system", lambda: system)
    monkeypatch.setattr(machine, "_fleet_node", lambda: None)
    ident = machine.sender_identity()
    assert ident["node"] == host.split(".")[0].lower()
    assert ident["node_source"] == "probe:hostname"
    assert len(ident["machine_id"]) == 12


def test_env_beats_config_beats_probe(monkeypatch):
    monkeypatch.setattr(machine.socket, "gethostname", lambda: "probehost")
    monkeypatch.setattr(machine, "_fleet_node", lambda: "nodecfg")
    assert machine.sender_identity()["node_source"] == "config:fleet_hosts"
    machine.sender_identity.cache_clear()
    monkeypatch.setenv("NOUGEN_NODE", "NodeEnv")
    ident = machine.sender_identity()
    assert (ident["node"], ident["node_source"]) == ("nodeenv", "env:NOUGEN_NODE")


def test_stamp_wins_over_wrong_asserted_node(monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE", "nodea")
    monkeypatch.setenv("NOUGEN_MACHINE_ID", "aaaaaaaaaaaa")
    env = nougenmsg.NouGenMsgBus._origin_envelope({"node": "nodeb", "lane": "claude"})
    assert env["machine"] == "nodea"
    assert env["machine_id"] == "aaaaaaaaaaaa"
    assert env["original_sender"].startswith("nodea-")
    assert any(c.get("claimed") == "nodeb" for c in env["conflicts"])


def test_forwarded_envelope_keeps_origin(monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE", "relayhop")
    env = nougenmsg.NouGenMsgBus._origin_envelope({
        "machine": "nodeorigin", "machine_id": "bbbbbbbbbbbb",
        "original_sender": "nodeorigin-claude", "relay_path": ["nodeorigin"]})
    assert env["machine"] == "nodeorigin"
    assert env["original_sender"] == "nodeorigin-claude"
    assert env["conflicts"] == []


def test_display_uses_sender_not_bridge():
    label = nougenmsg.display_sender({"machine": "nodeorigin", "machine_id": "cccccccccccc",
                                      "original_sender": "nodeorigin-claude"})
    assert label == "nodeorigin-claude [cccccccccccc]"
    assert "unstamped" in nougenmsg.display_sender({})
