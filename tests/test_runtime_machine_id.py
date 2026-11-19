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
        # Two devices, two OS machine ids.
        monkeypatch.setattr(fleet_nodes, "_stable_seed", lambda n=n: "os:machine-" + n)
        ids.add(m.current_machine_id())
    assert len(ids) == 2


def test_unwritable_home_still_answers_and_agrees_with_itself(box, monkeypatch):
    _host(monkeypatch, "localhost")
    monkeypatch.setenv("NOUGEN_ROOT", str(box / "root" / "machine_id"))  # a file, so mkdir fails
    (box / "root").mkdir()
    (box / "root" / "machine_id").write_text("x")
    monkeypatch.setattr(fleet_nodes, "_stable_seed", lambda: "os:fixed-machine")
    first = m.current_machine_id()
    assert re.fullmatch(r"device-[0-9a-f]{8}", first)
    assert m.current_machine_id() == first


def test_unwritable_home_and_no_stable_seed_is_still_stable_not_random(box, monkeypatch):
    """No machine id, no real MAC, no writable home: the id must not change per call/process."""
    _host(monkeypatch, "localhost")
    monkeypatch.setenv("NOUGEN_ROOT", str(box / "root" / "machine_id"))
    (box / "root").mkdir()
    (box / "root" / "machine_id").write_text("x")
    monkeypatch.setattr(fleet_nodes, "_stable_seed", lambda: "")
    monkeypatch.setattr(uuid, "uuid4", lambda: pytest.fail("a random id must never be used here"))
    first = m.current_machine_id()
    assert re.fullmatch(r"device-[0-9a-f]{8}", first)
    assert all(m.current_machine_id() == first for _ in range(5))


def test_concurrent_first_callers_all_get_the_one_persisted_id(box, monkeypatch):
    """No stable seed means a random id; racing first callers must still agree on one."""
    import threading
    _host(monkeypatch, "localhost")
    monkeypatch.setattr(fleet_nodes, "_stable_seed", lambda: "")
    n = 12
    barrier = threading.Barrier(n)
    out = []

    def go():
        barrier.wait()
        out.append(m.current_machine_id())

    threads = [threading.Thread(target=go) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    stored = (box / "root" / "machine_id").read_text().strip()
    assert len(out) == n and set(out) == {stored}


def test_a_random_mac_is_not_treated_as_an_identity(monkeypatch):
    """uuid.getnode() sets the multicast bit when it invents a value; that is no seed."""
    monkeypatch.setattr(fleet_nodes, "_OS_ID_FILES", ())
    monkeypatch.setattr(fleet_nodes, "_windows_machine_guid", lambda: "")
    monkeypatch.setattr(uuid, "getnode", lambda: 0x010000000001 | (1 << 40))
    assert fleet_nodes._stable_seed() == ""
    monkeypatch.setattr(uuid, "getnode", lambda: 0x021122334455)
    assert fleet_nodes._stable_seed() == "mac:021122334455"


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


def test_failed_write_returns_the_stable_fallback_and_leaves_no_file(box, monkeypatch):
    """A full disk must not escape as an error or leave an empty id file behind."""
    import errno
    from pathlib import Path
    _host(monkeypatch, "localhost")
    monkeypatch.setattr(fleet_nodes, "_stable_seed", lambda: "")

    def boom(self, *a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(Path, "write_text", boom)
    first = m.current_machine_id()
    assert re.fullmatch(r"device-[0-9a-f]{8}", first)
    assert m.current_machine_id() == first
    root = box / "root"
    assert not (root / "machine_id").exists()
    assert not list(root.glob("machine_id*")), "no temp file may be left behind"


def test_empty_id_file_from_a_crashed_run_is_repaired(box, monkeypatch):
    _host(monkeypatch, "localhost")
    monkeypatch.setattr(fleet_nodes, "_stable_seed", lambda: "os:fixed")
    (box / "root").mkdir()
    (box / "root" / "machine_id").write_text("")
    got = m.current_machine_id()
    assert (box / "root" / "machine_id").read_text().strip() == got
    assert m.current_machine_id() == got


def test_concurrent_first_processes_agree_on_one_id(tmp_path):
    """Real processes, not threads: no seed, a cold root, all started together."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    src = str(Path(fleet_nodes.__file__).resolve().parents[1])
    code = ("import sys,time;sys.path.insert(0,sys.argv[1]);"
            "from nougen_shards import fleet_nodes as f;f._stable_seed=lambda:'';"
            "t=float(sys.argv[2]);time.sleep(max(0,t-time.time()));print(f.device_id())")
    import time
    go = time.time() + 2.5
    env = {**os.environ, "NOUGEN_ROOT": str(tmp_path / "root")}
    procs = [subprocess.Popen([sys.executable, "-c", code, src, str(go)], env=env,
                              stdout=subprocess.PIPE, text=True) for _ in range(6)]
    outs = {p.communicate(timeout=60)[0].strip() for p in procs}
    stored = (tmp_path / "root" / "machine_id").read_text().strip()
    assert outs == {stored}
