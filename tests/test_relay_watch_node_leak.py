import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_watcher():
    path = Path(__file__).parents[1] / "tools" / "relay_watch_node.py"
    spec = importlib.util.spec_from_file_location("relay_watch_node_leak_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def w(monkeypatch, tmp_path):
    mod = load_watcher()
    cursor_path = tmp_path / "cursor.json"
    inbox_path = tmp_path / "inbox"
    reg_dir = tmp_path / "reg" / ".handoffs"
    reg_dir.mkdir(parents=True)

    monkeypatch.setattr(mod, "CURSOR", cursor_path)
    monkeypatch.setattr(mod, "INBOX", inbox_path)
    monkeypatch.setenv("NOUGEN_NODE_NAME", "phoebus")
    monkeypatch.setenv("NOUGEN_RELAY_WATCH_LANES", "claude-app")
    monkeypatch.setenv("NOUGEN_RELAY_WATCH_MAX_AGE_HOURS", "24")

    def put(leg_id, **record):
        (reg_dir / (leg_id + ".json")).write_text(json.dumps(record), encoding="utf-8")

    return SimpleNamespace(mod=mod, root=reg_dir.parent, put=put, cursor=cursor_path,
                           now=time.time())


def test_second_pass_announces_nothing_new(w):
    mod = w.mod
    now = w.now
    recent = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now - 60))
    for i in range(3):
        w.put(f"{recent}__a__{i}", status="open", goal="do it", machine="m", agent="a")

    seen = mod.Seen()
    counts1 = mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=lambda *a: None)
    assert counts1["announced"] == 3
    counts2 = mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=lambda *a: None)
    assert counts2["announced"] == 0
    assert counts2["new"] == 0


def test_restart_announces_nothing_old(w):
    mod = w.mod
    now = w.now
    recent = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now - 60))

    for i in range(5000):
        w.put(f"20260915T055143Z__x__{i}", status="closed", goal="done")
    for i in range(50):
        w.put(f"usage_2026-07-{i:02d}__x__y", status="closed", goal="done")
    w.put(f"{recent}__a__z", status="open", goal="do it", machine="m", agent="a")

    seen = mod.Seen()
    mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=lambda *a: None)

    seen2 = mod.load_seen()
    counts = mod.run_pass(w.root, seen2, "phoebus", {"claude-app"}, now=now, announcer=lambda *a: None)
    assert counts["announced"] == 0

    all_ids = list(seen2)
    assert len(all_ids) == 5051  # old sorted()[-4000:] cap evicted the newest legs
    assert f"{recent}__a__z" in all_ids
    assert "usage_2026-07-00__x__y" in all_ids


def test_closed_acked_sealed_complete_not_announced(w):
    mod = w.mod
    now = w.now
    recent = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now - 60))

    for status in ("closed", "acked", "sealed", "complete"):
        w.put(f"{recent}__a__{status}", status=status, goal="-> @phoebus do it", machine="m", agent="a")

    seen = mod.Seen()
    counts = mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=lambda *a: None)
    assert counts["announced"] == 0
    assert counts["closed"] == 4


def test_lines_per_pass_bounded(w, capsys):
    mod = w.mod
    now = w.now
    recent = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now - 60))

    for i in range(500):
        w.put(f"{recent}__a__{i}", status="open", goal="do it", machine="m", agent="a")

    seen = mod.Seen()
    mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=lambda *a: None)
    out = capsys.readouterr().out
    assert len(out.splitlines()) <= mod.MAX_NEW_LINES + 1

    for i in range(3000):
        w.put(f"20260915T055143Z__x__{i}", status="closed", goal="done")
    mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=lambda *a: None)
    out2 = capsys.readouterr().out
    assert len(out2.splitlines()) == 1  # 3000 closed legs: one count line, no SKIP lines
    assert out2.startswith("[relay_watch] pass:")


def test_new_open_leg_addressed_here_announced_once(w):
    mod = w.mod
    now = w.now
    recent = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now - 60))

    announced = []
    def ann(leg_id, path):
        announced.append(leg_id)

    w.put(f"{recent}__a__1", status="open", goal="[-> @phoebus] do it", machine="m", agent="a")
    w.put(f"{recent}__a__2", status="open", goal="[-> @blade] x", machine="m", agent="a")
    w.put(f"{recent}__a__3", status="open", goal="-> @all broadcast", machine="m", agent="a")
    w.put(f"{recent}__a__4", status="open", goal="do it", target="claude-app", machine="m", agent="a")
    w.put(f"{recent}__a__5", status="open", goal="mention @db7 only", machine="m", agent="a")

    seen = mod.Seen()
    for _ in range(3):
        mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=ann)
    seen2 = mod.load_seen()
    mod.run_pass(w.root, seen2, "phoebus", {"claude-app"}, now=now, announcer=ann)

    assert announced.count(f"{recent}__a__1") == 1
    assert announced.count(f"{recent}__a__2") == 0
    assert announced.count(f"{recent}__a__3") == 1
    assert announced.count(f"{recent}__a__4") == 1
    assert announced.count(f"{recent}__a__5") == 1


def test_stale_open_leg_not_announced(w):
    mod = w.mod
    now = w.now
    old_id = "20260915T055143Z__x__y"
    w.put(old_id, status="open", goal="-> @phoebus do it", machine="m", agent="a",
          created_utc="2026-09-15T05:51:43Z")

    seen = mod.Seen()
    counts = mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=lambda *a: None)
    assert counts["stale"] == 1
    assert counts["announced"] == 0


def test_announcer_runtime_error_counted(w):
    mod = w.mod
    now = w.now
    recent = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now - 60))
    w.put(f"{recent}__a__err", status="open", goal="-> @phoebus do it", machine="m", agent="a")

    def bad_ann(*a):
        raise RuntimeError("boom")

    seen = mod.Seen()
    counts1 = mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=bad_ann)
    assert counts1["errors"] == 1
    assert counts1["announced"] == 1
    assert f"{recent}__a__err" in seen

    counts2 = mod.run_pass(w.root, seen, "phoebus", {"claude-app"}, now=now, announcer=bad_ann)
    assert counts2["new"] == 0
    assert counts2["errors"] == 0


def test_cap_log_rotates(w, tmp_path):
    mod = w.mod
    log_path = tmp_path / "log.txt"
    with open(log_path, "w") as f:
        f.write("x" * 2000)
        f.flush()
        rotated = mod.cap_log(f, max_bytes=1000)
    assert rotated is True
    assert log_path.stat().st_size == 0
    if sys.platform in ("darwin", "linux"):
        backup = tmp_path / "log.txt.1"
        assert backup.exists()
        assert backup.stat().st_size == 2000
    with open(log_path, "a") as f:
        f.write("y" * 500)
        f.flush()
        rotated2 = mod.cap_log(f, max_bytes=1000)
    assert rotated2 is False
    assert log_path.stat().st_size == 500


def test_malicious_names_sanitized(w):
    mod = w.mod
    rec = {"target": "../../etc; rm -rf /"}
    addrs = mod.addresses(rec)
    for name in addrs:
        assert "/" not in name
        assert ";" not in name
        assert " " not in name


def test_version1_cursor_is_migrated_silently(w):
    mod = w.mod
    recent = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(w.now - 60))
    for i in range(30):
        w.put(f"{recent}__a__{i}", status="open", goal="-> @phoebus x", machine="m", agent="a")
    w.cursor.write_text(json.dumps({"seen": [f"{recent}__a__0"]}), encoding="utf-8")
    seen = mod.prime_cursor(w.root)
    counts = mod.run_pass(w.root, seen, "phoebus", set(), now=w.now, announcer=lambda *a: None)
    assert counts["new"] == 0 and len(seen) == 30
    assert mod.cursor_version() == mod.CURSOR_VERSION
    w.put(f"{recent}__b__new", status="open", goal="-> @phoebus x", machine="m", agent="a")
    again = mod.prime_cursor(w.root)  # restart on a v2 cursor: no re-prime
    assert mod.run_pass(w.root, again, "phoebus", set(), now=w.now,
                        announcer=lambda *a: None)["announced"] == 1
