"""BlockTracker: a pull that stays blocked must escalate, not just log one line a cycle."""
import importlib.util
import json
from pathlib import Path


def load_watcher():
    path = Path(__file__).parents[1] / "tools" / "relay_watch_node.py"
    spec = importlib.util.spec_from_file_location("relay_watch_node_guard_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tracker(tmp_path, alert=600, repeat=1800):
    w = load_watcher()
    return w.BlockTracker(alert_secs=alert, repeat_secs=repeat, state_path=tmp_path / "blocked.json"), w


BLOCKED = "error: Your local changes to the following files would be overwritten by merge:"


def test_quiet_until_the_threshold_then_one_alert(tmp_path):
    t, _ = tracker(tmp_path)
    assert t.update(BLOCKED, dirty=2, now=1000) is None            # first blocked cycle starts the clock
    assert t.update(BLOCKED, dirty=2, now=1599) is None            # 599 s: still quiet
    msg = t.update(BLOCKED, dirty=2, now=1600)                     # 600 s
    assert msg and "ALERT" in msg and "10 min" in msg and "uncommitted legs: 2" in msg and BLOCKED in msg
    assert "-X ours" in msg and "do NOT rebase" in msg


def test_state_file_is_written_while_blocked(tmp_path):
    t, _ = tracker(tmp_path)
    t.update(BLOCKED, dirty=3, now=0)
    t.update(BLOCKED, dirty=3, now=700)
    state = json.loads((tmp_path / "blocked.json").read_text())
    assert state["status"] == BLOCKED and state["dirty_legs"] == 3 and state["minutes"] == 11
    assert state["blocked_since_utc"].startswith("1970-01-01T00:00:00")


def test_repeats_only_after_the_repeat_window(tmp_path):
    t, _ = tracker(tmp_path, alert=600, repeat=1800)
    t.update(BLOCKED, dirty=1, now=0)
    assert t.update(BLOCKED, dirty=1, now=600)                      # first alert
    assert t.update(BLOCKED, dirty=1, now=1200) is None             # 10 min later: suppressed
    assert t.update(BLOCKED, dirty=1, now=2399) is None
    assert t.update(BLOCKED, dirty=1, now=2400)                     # 30 min after the first: repeats


def test_recovery_reports_clears_state_and_resets_the_clock(tmp_path):
    t, _ = tracker(tmp_path)
    t.update(BLOCKED, dirty=1, now=0)
    t.update(BLOCKED, dirty=1, now=900)
    assert (tmp_path / "blocked.json").exists()
    msg = t.update("ok", now=1200)
    assert msg and "RECOVERED" in msg and "20 min" in msg
    assert not (tmp_path / "blocked.json").exists()
    assert t.update(BLOCKED, dirty=0, now=1300) is None             # a new block starts a fresh clock


def test_a_short_blip_never_alerts_or_reports_recovery(tmp_path):
    t, _ = tracker(tmp_path)
    assert t.update(BLOCKED, dirty=1, now=0) is None
    assert t.update("ok", now=60) is None                           # recovered before any alert: silent
    assert not (tmp_path / "blocked.json").exists()


def test_unknown_dirty_count_is_reported_honestly(tmp_path):
    t, _ = tracker(tmp_path)
    t.update(BLOCKED, dirty=-1, now=0)
    assert "uncommitted legs: unknown" in t.update(BLOCKED, dirty=-1, now=600)


def test_unwritable_state_path_does_not_break_the_alert(tmp_path):
    w = load_watcher()
    blocker = tmp_path / "file"
    blocker.write_text("x")                                         # a file where a directory is needed
    t = w.BlockTracker(alert_secs=1, repeat_secs=1, state_path=blocker / "sub" / "s.json")
    t.update(BLOCKED, dirty=1, now=0)
    assert "ALERT" in t.update(BLOCKED, dirty=1, now=5)


def test_main_loop_prints_the_alert(tmp_path, monkeypatch, capsys):
    w = load_watcher()
    monkeypatch.setattr(w, "relay_dir", lambda: tmp_path)
    monkeypatch.setattr(w, "registry_parity_ok", lambda: (True, "test"))
    monkeypatch.setattr(w, "acquire_lock", lambda interval: True)
    monkeypatch.setattr(w, "release_lock", lambda: None)
    monkeypatch.setattr(w, "load_seen", lambda: {"x"})
    monkeypatch.setattr(w, "save_seen", lambda seen: None)
    monkeypatch.setattr(w, "legs", lambda root: {})
    monkeypatch.setattr(w, "heartbeat", lambda: None)
    monkeypatch.setattr(w, "pull", lambda root: BLOCKED)
    monkeypatch.setattr(w, "dirty_legs", lambda root: 2)
    monkeypatch.setenv("NOUGEN_RELAY_WATCH_ONCE", "1")
    monkeypatch.setenv("NOUGEN_RELAY_BLOCK_ALERT_SECS", "0")   # alert on the first blocked cycle
    monkeypatch.setenv("NOUGEN_RELAY_BLOCKED_STATE", str(tmp_path / "blocked.json"))
    assert w.main() == 0
    out = capsys.readouterr().out
    assert "ALERT: pull blocked" in out and "uncommitted legs: 2" in out
