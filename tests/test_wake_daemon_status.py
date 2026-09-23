"""wake_daemon settings resolve from env, and app.py's status tool only reads what exists."""
import ast
from pathlib import Path

import pytest

from nougen_shards import wake_daemon

APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def test_env_override_honored(monkeypatch):
    monkeypatch.setenv(wake_daemon.ENV_TIMEOUT_S, "123.4")
    monkeypatch.setenv(wake_daemon.ENV_POLL_INTERVAL_S, "1.2")
    assert wake_daemon.resolve_timeout_s() == 123.4
    assert wake_daemon.resolve_poll_interval_s() == 1.2


@pytest.mark.parametrize("raw", [None, "", "  ", "abc", "-10", "0"])
def test_unusable_env_falls_back(monkeypatch, raw):
    for name in (wake_daemon.ENV_TIMEOUT_S, wake_daemon.ENV_POLL_INTERVAL_S):
        if raw is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, raw)
    assert wake_daemon.resolve_timeout_s() == wake_daemon._FALLBACK_TIMEOUT_S
    assert wake_daemon.resolve_poll_interval_s() == wake_daemon._FALLBACK_POLL_INTERVAL_S


def test_status_reports_resolved_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(wake_daemon, "watch_dirs", lambda: [tmp_path])
    monkeypatch.setenv(wake_daemon.ENV_TIMEOUT_S, "42")
    monkeypatch.delenv(wake_daemon.ENV_POLL_INTERVAL_S, raising=False)
    assert wake_daemon.status() == {
        "poll_interval_s": wake_daemon._FALLBACK_POLL_INTERVAL_S,
        "timeout_s": 42.0,
        "watch_dirs": [str(tmp_path)],
        "status": "armed",
    }


def test_zero_timeout_returns_without_sleeping(monkeypatch, tmp_path):
    monkeypatch.setattr(wake_daemon, "watch_dirs", lambda: [tmp_path])

    def no_sleep(_seconds):
        pytest.fail("time.sleep called with a zero timeout")

    monkeypatch.setattr(wake_daemon.time, "sleep", no_sleep)
    assert wake_daemon.run_wake_loop(timeout_s=0) == 0


def test_loop_uses_env_settings_when_args_omitted(monkeypatch, tmp_path):
    # Fake clock: each sleep advances it, so the loop ends on the env timeout
    # with no dependence on real wall-clock speed.
    monkeypatch.setattr(wake_daemon, "watch_dirs", lambda: [tmp_path])
    monkeypatch.setenv(wake_daemon.ENV_TIMEOUT_S, "0.05")
    monkeypatch.setenv(wake_daemon.ENV_POLL_INTERVAL_S, "0.01")
    clock = [1000.0]
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(wake_daemon.time, "time", lambda: clock[0])
    monkeypatch.setattr(wake_daemon.time, "sleep", fake_sleep)
    assert wake_daemon.run_wake_loop(verbose=False) == 0
    assert sleeps and set(sleeps) == {0.01}
    assert 5 <= len(sleeps) <= 6


def test_app_reads_only_existing_wake_daemon_attributes():
    tree = ast.parse(APP_PY.read_text(encoding="utf-8"))
    used = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "wake_daemon"
    }
    assert used, "app.py no longer references wake_daemon; drop this guard"
    missing = sorted(a for a in used if not hasattr(wake_daemon, a))
    assert not missing, f"app.py reads undefined wake_daemon attributes: {missing}"
