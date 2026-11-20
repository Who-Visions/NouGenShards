"""Sender identity is resolved at run time, never trusted from the caller."""
import pytest

from nougen_shards import machine, nougenmsg


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for fn in (machine.hostname, machine.host_label, machine.machine_id):
        fn.cache_clear()
    for var in ("NOUGEN_NODE", "NOUGEN_MACHINE", "NOUGEN_MACHINE_ID", "NOUGEN_FLEET_NODE"):
        monkeypatch.delenv(var, raising=False)
    yield
    for fn in (machine.hostname, machine.host_label, machine.machine_id):
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
    assert machine.sender_identity()["node_source"] == "runtime:current_machine_id"
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
    assert env["conflicts"] == [{"field": "machine", "claimed": "nodeb",
                                 "transport_observed": "nodea"}]


def test_caller_label_kept_but_display_shows_real_machine(monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE", "nodea")
    env = nougenmsg.NouGenMsgBus._origin_envelope({"original_sender": "nodeb-codex"})
    assert env["machine"] == "nodea"
    assert nougenmsg.display_sender(env).startswith("nodea/nodeb-codex")


def test_forwarded_envelope_keeps_origin(monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE", "relayhop")
    env = nougenmsg.NouGenMsgBus._origin_envelope({
        "machine": "nodeorigin", "machine_id": "bbbbbbbbbbbb",
        "original_sender": "nodeorigin-claude", "relay_path": ["nodeorigin"]}, forwarded=True)
    assert env["machine"] == "nodeorigin"
    assert env["original_sender"] == "nodeorigin-claude"
    assert env["conflicts"] == []


def test_display_uses_sender_not_bridge():
    origin = {"machine": "nodeorigin", "machine_id": "cccccccccccc",
              "original_sender": "nodeorigin-claude"}
    assert nougenmsg.display_sender(dict(origin, origin_trust="stamped")) == "nodeorigin-claude [cccccccccccc]"
    assert nougenmsg.display_sender(dict(origin, origin_trust="forwarded-unverified")).endswith("(asserted)")
    assert nougenmsg.display_sender(origin).endswith("(asserted)")
    assert "unstamped" in nougenmsg.display_sender({})


@pytest.mark.parametrize("supplied,expect", [
    ({"machine": "nodeb", "relay_path": ["nodeb"]}, "nodeb"),
    ({"machine": "nodeb", "relay_path": ["nodec"]}, "nodeb"),
    ({"machine": "nodeb", "relay_path": ["nodeb", "nodea"]}, "nodeb"),
    ({"relay_path": ["nodeb"]}, "nodeb"),
    ({}, "unknown"),
])
def test_received_message_is_never_labelled_as_this_box(monkeypatch, supplied, expect):
    """A forwarded envelope keeps the sender's claim, marked unverified, and
    never takes the receiver's name (the "blade-claude" on WhoArt's message)."""
    monkeypatch.setenv("NOUGEN_NODE", "nodea")
    monkeypatch.setattr(nougenmsg, "get_current_node", lambda: "nodea")
    env = nougenmsg.NouGenMsgBus._origin_envelope(dict(supplied), forwarded=True)
    assert env["machine"] == expect
    assert env["origin_trust"] == "forwarded-unverified"
    assert nougenmsg.display_sender(env).endswith("(asserted)")


def test_local_caller_with_plausible_relay_path_stays_local(monkeypatch):
    """Reviewer's case: a local send that types a well-formed relay_path and
    machine is still re-stamped, because it did not arrive over a hop."""
    monkeypatch.setenv("NOUGEN_NODE", "nodea")
    monkeypatch.setattr(nougenmsg, "get_current_node", lambda: "nodea")
    for path in (["x"], ["nodeb"]):
        env = nougenmsg.NouGenMsgBus._origin_envelope(
            {"machine": "nodeb", "machine_id": "dddddddddddd", "relay_path": path})
        assert env["machine"] == "nodea"
        assert env["machine_id"] != "dddddddddddd"
        assert env["origin_trust"] == "stamped"
        assert env["conflicts"] == [{"field": "machine", "claimed": "nodeb",
                                     "transport_observed": "nodea"}]


def test_node_receiver_marks_peer_traffic_forwarded():
    src = (__import__("pathlib").Path(__file__).resolve().parents[1] / "tools" / "nougenmsg_node.py").read_text(encoding="utf-8")
    assert src.count("forwarded=True") >= 2
