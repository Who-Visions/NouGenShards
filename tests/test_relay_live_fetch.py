"""relay_live fetch: SSH stall limits and one retry on a hung fetch."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "tools" / "relay_live.py"


@pytest.fixture
def rl(monkeypatch):
    spec = importlib.util.spec_from_file_location("relay_live_under_test", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    monkeypatch.setenv("NOUGEN_RELAY_LIVE_FETCH", "1")
    return mod


def test_ssh_env_adds_limits_to_configured_command(rl, monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_RELAY_LIVE_SSH_CONNECT_S", "7")
    real_run = subprocess.run

    def fake_run(cmd, **kw):
        if cmd[-2:] == ["--get", "core.sshCommand"]:
            return subprocess.CompletedProcess(cmd, 0, "ssh -q -o BatchMode=yes\n", "")
        return real_run(cmd, **kw)

    monkeypatch.setattr(rl.subprocess, "run", fake_run)
    cmd = rl._ssh_env(tmp_path)["GIT_SSH_COMMAND"]
    assert cmd.startswith("ssh -q -o BatchMode=yes ")
    assert "ConnectTimeout=7" in cmd and "ServerAliveInterval=" in cmd


def test_ssh_env_respects_explicit_override(rl, monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_SSH_COMMAND", "plink")
    assert rl._ssh_env(tmp_path) is None


def test_fetch_retries_once_after_timeout(rl, monkeypatch, tmp_path):
    calls = []

    def fake_git(repo, *args, timeout):
        calls.append(args[0])
        if args[0] == "fetch" and calls.count("fetch") == 1:
            raise subprocess.TimeoutExpired("git fetch", timeout)
        if args[0] == "rev-parse":
            return subprocess.CompletedProcess(args, 0, "abc abc", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(rl, "_git", fake_git)
    assert rl.fetch(tmp_path) == "ok(unchanged)"
    assert calls.count("fetch") == 2


def test_fetch_reports_timeout_when_retries_exhausted(rl, monkeypatch, tmp_path):
    def always_hang(repo, *args, timeout):
        raise subprocess.TimeoutExpired("git fetch", timeout)

    monkeypatch.setattr(rl, "_git", always_hang)
    assert rl.fetch(tmp_path) == "git error TimeoutExpired"
