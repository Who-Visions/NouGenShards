"""relay_live: first run initialises the cursor without dumping the backlog, a
new leg is rendered and sent once, own legs are skipped, and the cursor
advances. Adaptive cadence holds the active interval inside the window and
backs off to the idle ceiling; the wake file cuts a sleep short. Hermetic:
fake registry dir, fetch disabled, pinger mocked, fake clock."""
import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("relay_live", HERE / "tools" / "relay_live.py")


def setup(monkeypatch, tmp_path):
    repo = tmp_path / "NouGenRelay"; (repo / ".handoffs").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(repo))
    monkeypatch.setenv("NOUGEN_RELAY_LIVE_CURSOR", str(tmp_path / "cursor.json"))
    monkeypatch.setenv("NOUGEN_RELAY_LIVE_WAKE", str(tmp_path / "wake"))
    monkeypatch.setenv("NOUGEN_RELAY_LIVE_FETCH", "0")
    monkeypatch.delenv("NOUGEN_RELAY_LIVE_SELF", raising=False)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    sent = []
    monkeypatch.setattr(mod.AgentPinger, "ping_claude", staticmethod(lambda text: (sent.append(text) or {"delivered": [{"session_id": "s"}], "registered": 1, "inbox_file": "x"})))
    return mod, repo, sent


def leg(repo, leg_id, machine, agent, goal, created_utc=""):
    (repo / ".handoffs" / f"{leg_id}.json").write_text(json.dumps({"id": leg_id, "machine": machine, "agent": agent, "goal": goal, "status": "open", "created_utc": created_utc}), encoding="utf-8")


def test_backlog_skipped_then_new_leg_sent_once(monkeypatch, tmp_path):
    mod, repo, sent = setup(monkeypatch, tmp_path)
    leg(repo, "20260901T000000Z__ccr__claude-cli", "ccr", "claude-cli", "old todo")
    first = mod.one_pass(quiet=True)
    assert first["new"] == 0 and "backlog skipped" in first["note"] and sent == []
    leg(repo, "20260903T010000Z__chatgpt-app__g-whoentertains", "chatgpt-app", "g-whoentertains", "Build the thing", "2026-09-03T01:00:00.000Z")
    leg(repo, "20260903T010100Z__blade1tb__claude-cli", "blade1tb", "claude-cli", "my own answer leg")
    second = mod.one_pass(quiet=True)
    assert second["new"] == 2 and len(sent) == 1 and second["skipped_self"] == ["20260903T010100Z__blade1tb__claude-cli"]
    assert sent[0].startswith("NouGenRelay leg 20260903T010000Z__chatgpt-app__g-whoentertains from chatgpt-app/g-whoentertains (open): Build the thing")
    assert "not permission" in sent[0]
    assert second["sent"][0]["create_to_visible_s"] > 0, "latency evidence recorded from created_utc"
    third = mod.one_pass(quiet=True)
    assert third["new"] == 0 and len(sent) == 1, "cursor advanced, nothing resent"


def test_dry_run_sends_nothing(monkeypatch, tmp_path):
    mod, repo, sent = setup(monkeypatch, tmp_path)
    mod.one_pass(quiet=True)
    leg(repo, "20260903T020000Z__phoebus__claude-cli", "phoebus", "claude-cli", "dry")
    out = mod.one_pass(dry=True, quiet=True)
    assert out["sent"][0]["dry"] is True and sent == []
    assert mod.one_pass(dry=True, quiet=True)["new"] == 1, "dry run does not advance the cursor"


def test_created_epoch_falls_back_to_id_prefix(monkeypatch, tmp_path):
    mod, _, _ = setup(monkeypatch, tmp_path)
    a = mod.created_epoch({"id": "20260903T010000Z__x__y", "created_utc": "2026-09-03T01:00:00.000Z"})
    b = mod.created_epoch({"id": "20260903T010000Z__x__y", "created_utc": ""})
    import calendar, time as _t
    assert a == b == float(calendar.timegm(_t.strptime("2026-09-03T01:00:00", "%Y-%m-%dT%H:%M:%S"))), "UTC, not local, no DST drift"
    assert mod.created_epoch({"id": "garbage", "created_utc": "nope"}) is None


def test_next_interval_holds_active_then_backs_off(monkeypatch, tmp_path):
    mod, _, _ = setup(monkeypatch, tmp_path)
    cfg = dict(active=3.0, window=600.0, idle_max=60.0)
    assert mod.next_interval(60.0, 1, 1000.0, 0.0, **cfg) == 3.0, "new leg snaps to active"
    assert mod.next_interval(3.0, 0, 1000.0, 900.0, **cfg) == 3.0, "inside the window stays active"
    seq, prev = [], 3.0
    for _ in range(6):
        prev = mod.next_interval(prev, 0, 5000.0, 0.0, **cfg)
        seq.append(prev)
    assert seq == [6.0, 12.0, 24.0, 48.0, 60.0, 60.0], "doubles then caps at idle ceiling"


def test_wait_returns_early_on_wake_file(monkeypatch, tmp_path):
    mod, _, _ = setup(monkeypatch, tmp_path)
    wake = tmp_path / "wake"
    t = {"now": 0.0}
    calls = {"n": 0}

    def sleep(s):
        t["now"] += s
        calls["n"] += 1
        if calls["n"] == 3:
            wake.write_text("x", encoding="utf-8")

    assert mod.wait(60.0, wake, 0.5, clock=lambda: t["now"], sleep=sleep) == "wake"
    assert t["now"] < 2.0, "woke within a few slices, not the full interval"
    t["now"] = 0.0
    assert mod.wait(2.0, wake, 0.5, clock=lambda: t["now"], sleep=lambda s: t.__setitem__("now", t["now"] + s)) == "timeout"


def test_legs_on_registry_branch_are_delivered_before_working_tree_sync(monkeypatch, tmp_path):
    """A leg committed to origin/main by the connector is seen and rendered from
    the fetched ref even though nothing has copied it into .handoffs/ yet."""
    import subprocess
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(origin)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    (work / ".handoffs").mkdir()
    (work / ".handoffs" / "seed.txt").write_text("seed", encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "seed"], check=True, env={**dict(__import__("os").environ), **env})
    subprocess.run(["git", "-C", str(work), "push", "-q", "-u", "origin", "main"], check=True)
    blade = tmp_path / "NouGenRelay"
    subprocess.run(["git", "clone", "-q", str(origin), str(blade)], check=True)
    subprocess.run(["git", "-C", str(blade), "remote", "set-head", "origin", "main"], check=True)
    # mirror production: blade's checkout is a code branch with its own upstream, not the registry branch
    subprocess.run(["git", "-C", str(blade), "checkout", "-q", "-b", "pi-remix"], check=True)
    subprocess.run(["git", "-C", str(blade), "push", "-q", "-u", "origin", "pi-remix"], check=True)
    mod, _, sent = setup(monkeypatch, tmp_path)
    monkeypatch.setenv("NOUGEN_RELAY_LIVE_FETCH", "1")
    assert mod.registry_branch(blade) == "main"
    assert mod.one_pass(quiet=True)["new"] == 0
    # curly quotes, arrow and a check mark: bytes the Windows console codepage cannot decode
    # (this exact shape sank every pass for 18 minutes on 2026-09-03)
    leg(work, "20260903T030000Z__chatgpt-app__g-whoentertains", "chatgpt-app", "g-whoentertains", "Committed upstream only: “Jarvis Who?” → fleet ✓", "2026-09-03T03:00:00.000Z")
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "leg"], check=True, env={**dict(__import__("os").environ), **env})
    subprocess.run(["git", "-C", str(work), "push", "-q"], check=True)
    out = mod.one_pass(quiet=True)
    assert out["fetch"].startswith("ok") and out["new"] == 1 and len(sent) == 1
    assert "Committed upstream only: “Jarvis Who?” → fleet ✓" in sent[0], "non-cp1252 body decoded as UTF-8"
    assert not (blade / ".handoffs" / "20260903T030000Z__chatgpt-app__g-whoentertains.json").exists(), "read-only: nothing copied into the working tree"


def test_unreadable_leg_is_delivered_by_id_and_never_sinks_the_pass(monkeypatch, tmp_path):
    mod, repo, sent = setup(monkeypatch, tmp_path)
    mod.one_pass(quiet=True)
    leg(repo, "20260903T040000Z__chatgpt-app__g-whoentertains", "chatgpt-app", "g-whoentertains", "fine leg")
    (repo / ".handoffs" / "20260903T040100Z__phoebus__claude-cli.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(mod, "leg_summary", lambda r, i: (_ for _ in ()).throw(TypeError("boom")) if "040100Z" in i else {"id": i, "machine": "chatgpt-app", "agent": "g-whoentertains", "goal": "fine leg", "status": "open", "created_utc": ""})
    out = mod.one_pass(quiet=True)
    assert out["new"] == 2 and len(sent) == 2
    assert any("body unreadable: TypeError" in s and "040100Z" in s for s in sent)
    assert mod.one_pass(quiet=True)["new"] == 0, "cursor advanced past the bad leg too"


def test_wake_flag_touches_file(monkeypatch, tmp_path, capsys):
    mod, _, _ = setup(monkeypatch, tmp_path)
    assert mod.main(["--wake"]) == 0
    assert (tmp_path / "wake").exists() and "woke" in capsys.readouterr().out
