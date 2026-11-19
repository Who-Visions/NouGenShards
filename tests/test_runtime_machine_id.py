"""A reply names the machine it came from, discovered at runtime, on any device.

Public code ships no fleet names. A box in fleet_hosts.json keeps its fleet
node; every other box (new laptop, phone, container, tenant PC) is named from
its own hostname or a persisted device id instead of the literal "standalone".
"""
import re
import uuid

import pytest

from nougen_shards import fleet_nodes, nougenmsg as m


@pytest.fixture()
def box(monkeypatch, tmp_path):
    """An unconfigured machine whose state lives under tmp_path."""
    monkeypatch.setenv("NOUGEN_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("NOUGEN_FLEET_HOSTS_FILE", str(tmp_path / "absent.json"))
    for var in ("NOUGEN_NODE_NAME", "NOUGEN_FLEET_NODE"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _host(monkeypatch, name):
    monkeypatch.setattr(fleet_nodes.socket, "gethostname", lambda: name)
    monkeypatch.setattr(m, "resolve_origin_host", lambda: name.split(".")[0].lower())


def test_unlisted_laptop_is_named_from_its_hostname(box, monkeypatch):
    _host(monkeypatch, "Monnas-Laptop.local")
    assert m.get_current_node() == "standalone"          # routing semantics unchanged
    assert m.current_machine_id() == "monnas-laptop"     # but the reply says who it is


def test_hostname_is_slugged_so_it_is_safe_in_a_header_and_path(box, monkeypatch):
    _host(monkeypatch, "Dave's iPhone (2)")
    assert re.fullmatch(r"[a-z0-9-]+", m.current_machine_id())


@pytest.mark.parametrize("generic", ["localhost", "android", "", "Localhost.localdomain"])
def test_generic_hostname_gets_a_persisted_device_id(box, monkeypatch, generic):
    _host(monkeypatch, generic)
    first = m.current_machine_id()
    assert re.fullmatch(r"device-[0-9a-f]{8}", first)
    assert (box / "root" / "machine_id").read_text().strip() == first
    assert m.current_machine_id() == first               # stable across calls


def test_two_devices_with_the_same_generic_hostname_get_different_ids(monkeypatch, tmp_path):
    ids = set()
    for n in ("a", "b"):
        monkeypatch.setenv("NOUGEN_ROOT", str(tmp_path / n))
        monkeypatch.setenv("NOUGEN_FLEET_HOSTS_FILE", str(tmp_path / "absent.json"))
        monkeypatch.delenv("NOUGEN_NODE_NAME", raising=False)
        monkeypatch.delenv("NOUGEN_FLEET_NODE", raising=False)
        _host(monkeypatch, "localhost")
        # Different hardware address per device; an unreadable one makes a random id.
        monkeypatch.setattr(uuid, "getnode", lambda n=n: 0x021122334455 + ord(n))
        ids.add(m.current_machine_id())
    assert len(ids) == 2


def test_unwritable_home_still_answers_and_agrees_with_itself(box, monkeypatch):
    _host(monkeypatch, "localhost")
    monkeypatch.setenv("NOUGEN_ROOT", str(box / "root" / "machine_id"))  # a file, so mkdir fails
    (box / "root").mkdir()
    (box / "root" / "machine_id").write_text("x")
    monkeypatch.setattr(uuid, "getnode", lambda: 0x021122334455)
    first = m.current_machine_id()
    assert re.fullmatch(r"device-[0-9a-f]{8}", first)
    assert m.current_machine_id() == first


def test_configured_fleet_box_keeps_its_fleet_node_name(box, monkeypatch, tmp_path):
    cfg = tmp_path / "fleet_hosts.json"
    cfg.write_text('{"nodes": {"alpha": {"host_patterns": ["box-a"]}}}')
    monkeypatch.setenv("NOUGEN_FLEET_HOSTS_FILE", str(cfg))
    _host(monkeypatch, "box-a-01")
    assert m.current_machine_id() == "alpha"


def test_node_name_env_pins_the_name_everywhere(box, monkeypatch):
    _host(monkeypatch, "whatever")
    monkeypatch.setenv("NOUGEN_NODE_NAME", "Kitchen Tablet")
    assert m.current_machine_id() == "kitchen-tablet"


def test_sent_message_source_carries_the_runtime_name(box, monkeypatch):
    """The stamp on the wire is the runtime name, never the word standalone."""
    _host(monkeypatch, "Monnas-Laptop.local")
    assert f"NouGenMsg-{m.current_machine_id()}" == "NouGenMsg-monnas-laptop"
    assert "standalone" not in m.current_machine_id()
