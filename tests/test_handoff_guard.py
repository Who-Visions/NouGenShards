"""handoff_guard: the SessionEnd auto-stub is written synchronously and the
slow index rebuild is spawned detached (the hook used to block on it for ~25 s
and get cancelled at the 20 s hook timeout); a fresh handoff skips the stub;
sessionstart sweeps stale .start markers. Hermetic: tmp handoff dir, git and
spawn mocked, stdin fed with the hook event."""
import importlib.util
import io
import json
import os
import pathlib
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
SRC = HERE / "tools" / "handoff_guard.py"


def load(monkeypatch, tmp_path, agent="claude-cli"):
    hd = tmp_path / ".handoffs"
    hd.mkdir()
    monkeypatch.setenv("NOUGEN_REPO", str(tmp_path))
    monkeypatch.setenv("NOUGEN_HANDOFF_DIR", str(hd))
    monkeypatch.setenv("NOUGEN_AGENT", agent)
    monkeypatch.setenv("NOUGEN_SESSION_MARKER_MAX_AGE_H", "1")
    spec = importlib.util.spec_from_file_location("handoff_guard", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    spawned = []
    monkeypatch.setattr(mod, "_spawn_detached", lambda cmd, cwd, env: spawned.append((cmd, str(cwd))) or None)
    monkeypatch.setattr(mod, "_git", lambda *a: "main" if a[0] == "branch" else " M x.py")
    return mod, hd, spawned


def run(monkeypatch, mod, mode, sid):
    monkeypatch.setattr("sys.argv", ["handoff_guard.py", "--mode", mode])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": sid})))
    t0 = time.time()
    mod.main()
    return time.time() - t0


def test_sessionend_writes_stub_then_spawns_rebuild_without_blocking(monkeypatch, tmp_path):
    mod, hd, spawned = load(monkeypatch, tmp_path)
    run(monkeypatch, mod, "sessionstart", "s1")
    marker = hd / ".sessions" / "s1.start"
    assert marker.exists()
    elapsed = run(monkeypatch, mod, "sessionend", "s1")
    stubs = list(hd.glob("claude cli handoffs/handoff_*_claude-cli_auto.md"))
    assert len(stubs) == 1, "stub written synchronously"
    body = stubs[0].read_text(encoding="utf-8")
    assert "s1" in body and " M x.py" in body
    assert not marker.exists(), "marker cleaned"
    assert len(spawned) == 1 and spawned[0][0][1:] == ["-m", "nougen_shards.cli", "handoff", "rebuild-db"]
    assert elapsed < 2, "hook must return well inside its timeout"


def test_sessionend_skips_stub_when_handoff_is_fresh(monkeypatch, tmp_path):
    mod, hd, spawned = load(monkeypatch, tmp_path)
    run(monkeypatch, mod, "sessionstart", "s2")
    time.sleep(0.05)
    (hd / "handoff_20260903_010000_claude-cli_main.md").write_text("# real handoff", encoding="utf-8")
    run(monkeypatch, mod, "sessionend", "s2")
    assert not list(hd.glob("**/handoff_*_auto.md")) and spawned == []
    assert not (hd / ".sessions" / "s2.start").exists()


def test_sessionstart_sweeps_stale_markers(monkeypatch, tmp_path):
    mod, hd, _ = load(monkeypatch, tmp_path)
    sess = hd / ".sessions"
    sess.mkdir()
    old = sess / "dead.start"
    old.write_text("1", encoding="utf-8")
    two_hours_ago = time.time() - 7200
    os.utime(old, (two_hours_ago, two_hours_ago))
    fresh = sess / "alive.start"
    fresh.write_text("1", encoding="utf-8")
    run(monkeypatch, mod, "sessionstart", "s3")
    assert not old.exists() and fresh.exists() and (sess / "s3.start").exists()


def test_spawn_detached_returns_immediately(tmp_path):
    spec = importlib.util.spec_from_file_location("handoff_guard_real", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import sys
    t0 = time.time()
    p = mod._spawn_detached([sys.executable, "-c", "import time; time.sleep(3)"], tmp_path, dict(os.environ))
    assert time.time() - t0 < 1.5 and p.poll() is None
    p.kill()
