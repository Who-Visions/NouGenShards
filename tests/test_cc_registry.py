"""cc_sessions.json survives concurrent writers and a corrupt file (the Phoebus
registered=0 outage: two documents back to back, "Extra data")."""
import importlib.util
import json
import threading
from pathlib import Path

from nougen_shards import cc_registry

ROOT = Path(__file__).resolve().parents[1]


def test_corrupt_registry_is_salvaged_not_emptied(tmp_path):
    p = tmp_path / "cc.json"
    a = {"sessions": {"/tmp/a.sock": {"token": "ta", "socket": "/tmp/a.sock"}}}
    b = {"sid-b": {"token": "tb", "socket": "/tmp/b.sock"}}
    p.write_text(json.dumps(a) + json.dumps(b) + "}garbage")
    data, corrupt = cc_registry.read(str(p))
    assert corrupt is True
    assert "/tmp/a.sock" in data["sessions"] and "sid-b" in data


def test_concurrent_writers_keep_every_session(tmp_path):
    p = str(tmp_path / "cc.json")

    def add(i):
        cc_registry.update(p, lambda d: d.setdefault("sessions", {}).__setitem__(f"/tmp/{i}.sock", {"token": str(i)}))

    threads = [threading.Thread(target=add, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    data, corrupt = cc_registry.read(p)
    assert not corrupt and len(data["sessions"]) == 24


def test_register_hook_repairs_a_corrupt_file_and_keeps_old_entries(tmp_path, monkeypatch):
    p = tmp_path / "cc.json"
    p.write_text(json.dumps({"sessions": {"/tmp/old.sock": {"token": "o"}}}) + json.dumps({"x": 1}))
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(p))
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/tmp/new.sock")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "n")
    spec = importlib.util.spec_from_file_location("reg_hook", ROOT / "tools" / "nougenmsg_register_hook.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    hook.register({"session_id": "s1"})
    data = json.loads(p.read_text())
    assert set(data["sessions"]) == {"/tmp/old.sock", "/tmp/new.sock"}
