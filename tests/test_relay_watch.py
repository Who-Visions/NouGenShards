"""relay_watch: git timeouts resolve from env, and a failed git log never
blanks the last good leg cache that session hooks read."""
import importlib
import json
from types import SimpleNamespace

import pytest

from nougen_shards import relay_watch

LOG = (
    "c2|2026-09-15T10:00:00+00:00|leg two\n"
    ".handoffs/20260915T100000Z__b.json\n"
    "README.md\n"
    "\n"
    "c1|2026-09-15T09:00:00+00:00|leg one\n"
    ".handoffs/20260915T090000Z__a.json\n"
)


@pytest.fixture
def repo(monkeypatch, tmp_path):
    monkeypatch.setattr(relay_watch, "REPO", tmp_path)
    monkeypatch.setattr(relay_watch, "CACHE", tmp_path / "state" / "cache.json")
    return tmp_path


def fake_git(responses):
    calls = []

    def _fake(*args, timeout=None):
        calls.append((args, timeout))
        return responses.get(args[0], "")

    _fake.calls = calls
    return _fake


def read_cache():
    return json.loads(relay_watch.CACHE.read_text(encoding="utf-8"))


def test_parses_log_newest_first_and_skips_non_leg_paths(repo, monkeypatch):
    monkeypatch.setattr(relay_watch, "_git", fake_git({"log": LOG}))
    relay_watch.refresh_cache()
    legs = read_cache()["legs"]
    assert [l["leg_id"] for l in legs] == ["20260915T100000Z__b", "20260915T090000Z__a"]
    assert legs[0]["commit"] == "c2"
    assert legs[0]["created_at"] == "2026-09-15T10:00:00+00:00"
    assert legs[1]["path"] == ".handoffs/20260915T090000Z__a.json"


def test_max_legs_caps_the_cache(repo, monkeypatch):
    monkeypatch.setattr(relay_watch, "MAX_LEGS", 1)
    monkeypatch.setattr(relay_watch, "_git", fake_git({"log": LOG}))
    relay_watch.refresh_cache()
    assert len(read_cache()["legs"]) == 1


def test_failed_log_keeps_last_good_cache(repo, monkeypatch):
    relay_watch.CACHE.parent.mkdir(parents=True)
    relay_watch.CACHE.write_text('{"legs": [{"leg_id": "keep"}]}', encoding="utf-8")
    before = relay_watch.CACHE.read_bytes()
    monkeypatch.setattr(relay_watch, "_git", fake_git({"log": None}))
    relay_watch.refresh_cache()
    assert relay_watch.CACHE.read_bytes() == before


def test_quiet_window_still_writes_empty_legs(repo, monkeypatch):
    monkeypatch.setattr(relay_watch, "_git", fake_git({"log": ""}))
    relay_watch.refresh_cache()
    assert read_cache()["legs"] == []


def test_fetch_failure_still_indexes_local_origin(repo, monkeypatch):
    git = fake_git({"fetch": None, "log": LOG})
    monkeypatch.setattr(relay_watch, "_git", git)
    relay_watch.refresh_cache()
    assert len(read_cache()["legs"]) == 2
    assert git.calls[0] == (("fetch", "origin", "main", "--quiet"), relay_watch.FETCH_TIMEOUT_S)


def test_write_is_atomic_and_leaves_no_temp_file(repo, monkeypatch):
    monkeypatch.setattr(relay_watch, "_git", fake_git({"log": LOG}))
    relay_watch.refresh_cache()
    assert sorted(p.name for p in relay_watch.CACHE.parent.iterdir()) == ["cache.json"]


def test_get_new_legs_since(repo):
    relay_watch.CACHE.parent.mkdir(parents=True)
    legs = [{"leg_id": f"l{i}"} for i in range(1, 5)]
    relay_watch.CACHE.write_text(json.dumps({"legs": legs}), encoding="utf-8")
    assert [l["leg_id"] for l in relay_watch.get_new_legs_since()] == ["l1", "l2", "l3"]
    assert [l["leg_id"] for l in relay_watch.get_new_legs_since("l3")] == ["l1", "l2"]
    relay_watch.CACHE.write_text("not json", encoding="utf-8")
    assert relay_watch.get_new_legs_since() == []
    relay_watch.CACHE.unlink()
    assert relay_watch.get_new_legs_since() == []


def test_git_returns_none_on_nonzero_exit_and_on_exception(repo, monkeypatch):
    seen = []

    def run(cmd, **kw):
        seen.append(kw)
        return SimpleNamespace(returncode=len(seen) - 1, stdout="out")  # 0, then 1

    monkeypatch.setattr(relay_watch.subprocess, "run", run)
    assert relay_watch._git("status") == "out"
    assert seen[0]["timeout"] == relay_watch.GIT_TIMEOUT_S
    assert relay_watch._git("status", timeout=3) is None
    assert seen[1]["timeout"] == 3

    def boom(cmd, **kw):
        raise OSError("git missing")

    monkeypatch.setattr(relay_watch.subprocess, "run", boom)
    assert relay_watch._git("status") is None


def test_timeouts_resolve_from_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_RELAY_GIT_TIMEOUT_S", "7")
    monkeypatch.setenv("NOUGEN_RELAY_FETCH_TIMEOUT_S", "3")
    try:
        importlib.reload(relay_watch)
        assert relay_watch.GIT_TIMEOUT_S == 7.0
        assert relay_watch.FETCH_TIMEOUT_S == 3.0
    finally:
        monkeypatch.undo()
        importlib.reload(relay_watch)
