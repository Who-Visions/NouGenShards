"""relay_live fetch: SSH stall limits and one retry on a hung fetch."""
import importlib.util
import os
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


def test_git_timeout_kills_child_tree_before_raising(rl, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh")

    class HangingGit:
        pid = 4321
        returncode = None

        def communicate(self, timeout):
            if not calls:
                calls.append(("communicate", timeout))
                raise subprocess.TimeoutExpired("git fetch", timeout)
            calls.append(("drained", timeout))
            return "", ""

        def kill(self):
            calls.append(("kill", self.pid))

    monkeypatch.setattr(rl.subprocess, "Popen", lambda *a, **kw: HangingGit())
    monkeypatch.setattr(rl.os, "name", "nt")
    monkeypatch.setattr(rl.shutil, "which", lambda name: r"C:\Windows\System32\taskkill.exe")
    monkeypatch.setattr(rl.subprocess, "run", lambda cmd, **kw: calls.append(("tree-kill", cmd)))

    with pytest.raises(subprocess.TimeoutExpired):
        rl._git(tmp_path, "fetch", timeout=2)

    assert calls[0] == ("communicate", 2)
    assert calls[1][0] == "tree-kill"
    assert calls[1][1][-4:] == ["/PID", "4321", "/T", "/F"]
    assert calls[2][0] == "drained"


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.strip()


def _diverged_repos(tmp_path, *, remote_path=".handoffs/hourly.md", conflict=False):
    origin = tmp_path / "origin.git"
    local = tmp_path / "local"
    writer = tmp_path / "writer"
    _git(tmp_path, "init", "--bare", str(origin))
    local.mkdir()
    _git(local, "init")
    _git(local, "config", "user.name", "Relay Test")
    _git(local, "config", "user.email", "relay-test@example.invalid")
    (local / ".handoffs").mkdir()
    (local / ".handoffs" / "base.md").write_text("base\n", encoding="utf-8")
    if conflict:
        (local / ".handoffs" / "shared.md").write_text("base shared\n", encoding="utf-8")
    _git(local, "add", ".")
    _git(local, "commit", "-m", "base")
    _git(local, "branch", "-M", "main")
    _git(local, "remote", "add", "origin", str(origin))
    _git(local, "push", "-u", "origin", "main")

    _git(tmp_path, "clone", "--branch", "main", str(origin), str(writer))
    _git(writer, "config", "user.name", "Phoebus Test")
    _git(writer, "config", "user.email", "phoebus-test@example.invalid")
    remote_file = writer / remote_path
    remote_file.parent.mkdir(parents=True, exist_ok=True)
    remote_file.write_text("remote\n", encoding="utf-8")
    _git(writer, "add", ".")
    _git(writer, "commit", "-m", "hourly publisher update")
    _git(writer, "push", "origin", "main")

    if conflict:
        (local / remote_path).write_text("local\n", encoding="utf-8")
    else:
        (local / ".handoffs" / "local-completion.md").write_text("local completion\n", encoding="utf-8")
    _git(local, "add", ".")
    _git(local, "commit", "-m", "local completion")
    return origin, local, writer


def test_fetch_merges_only_additive_handoff_divergence_and_preserves_untracked(rl, tmp_path):
    _origin, local, writer = _diverged_repos(tmp_path)
    untracked = local / "src" / "nougenrelay" / "candidate.ts"
    untracked.parent.mkdir(parents=True)
    untracked.write_text("preserve me\n", encoding="utf-8")
    local_commit = _git(local, "rev-parse", "HEAD")
    remote_commit = _git(writer, "rev-parse", "HEAD")

    assert rl.fetch(local) == "ok(updated,merged-additive-handoffs)"
    assert (local / ".handoffs" / "local-completion.md").read_text(encoding="utf-8") == "local completion\n"
    assert (local / ".handoffs" / "hourly.md").read_text(encoding="utf-8") == "remote\n"
    assert untracked.read_text(encoding="utf-8") == "preserve me\n"
    assert _git(local, "merge-base", "--is-ancestor", local_commit, "HEAD") == ""
    assert _git(local, "merge-base", "--is-ancestor", remote_commit, "HEAD") == ""


def test_fetch_defers_same_path_handoff_conflict_without_mutation(rl, tmp_path):
    _origin, local, _writer = _diverged_repos(
        tmp_path, remote_path=".handoffs/shared.md", conflict=True
    )
    before = _git(local, "rev-parse", "HEAD")
    assert rl.fetch(local) == "skipped(diverged,non-additive-handoff-change)"
    assert _git(local, "rev-parse", "HEAD") == before
    assert (local / ".handoffs" / "shared.md").read_text(encoding="utf-8") == "local\n"
    assert not (local / ".git" / "MERGE_HEAD").exists()


def test_fetch_defers_non_handoff_upstream_change(rl, tmp_path):
    _origin, local, _writer = _diverged_repos(tmp_path, remote_path="src/feature.py")
    before = _git(local, "rev-parse", "HEAD")
    assert rl.fetch(local) == "skipped(diverged,non-additive-handoff-change)"
    assert _git(local, "rev-parse", "HEAD") == before


def test_fetch_defers_untracked_path_collision(rl, tmp_path):
    _origin, local, _writer = _diverged_repos(tmp_path)
    incoming = local / ".handoffs" / "hourly.md"
    incoming.write_text("untracked local file\n", encoding="utf-8")
    before = _git(local, "rev-parse", "HEAD")
    assert rl.fetch(local) == "skipped(diverged,untracked-path-collision)"
    assert _git(local, "rev-parse", "HEAD") == before
    assert incoming.read_text(encoding="utf-8") == "untracked local file\n"


def test_fetch_defers_when_tracked_worktree_is_dirty(rl, tmp_path):
    _origin, local, _writer = _diverged_repos(tmp_path)
    path = local / ".handoffs" / "base.md"
    path.write_text("operator edit\n", encoding="utf-8")
    before = _git(local, "rev-parse", "HEAD")
    assert rl.fetch(local) == "skipped(diverged,tracked-worktree-dirty)"
    assert _git(local, "rev-parse", "HEAD") == before
    assert path.read_text(encoding="utf-8") == "operator edit\n"


def test_fetch_skips_existing_merge_state(rl, tmp_path):
    _origin, local, _writer = _diverged_repos(
        tmp_path, remote_path=".handoffs/shared.md", conflict=True
    )
    _git(local, "fetch", "origin")
    result = subprocess.run(
        ["git", "-C", str(local), "merge", "--no-commit", "--no-ff", "origin/main"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode != 0
    assert (local / ".git" / "MERGE_HEAD").exists()
    assert rl.fetch(local) == "skipped(merge-in-progress; preserving checkout)"
    assert (local / ".git" / "MERGE_HEAD").exists()
