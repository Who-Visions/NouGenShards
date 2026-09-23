import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nougen_loop", ROOT / "tools" / "nougen_loop.py")
loop = importlib.util.module_from_spec(spec)
sys.modules["nougen_loop"] = loop
spec.loader.exec_module(loop)

NOUGEN_STAGES = ["recall", "shard", "dream", "handoff"]


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "demo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "loop@example.invalid")
    _git(r, "config", "user.name", "loop test")
    (r / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(r, "add", "app.py")
    _git(r, "commit", "-q", "-m", "init")
    monkeypatch.setenv("NOUGEN_LOOP_TEST_CMD", f"{sys.executable} -c pass")
    monkeypatch.setenv("NOUGEN_LOOP_DEFAULT_BRANCH", "main")
    monkeypatch.setattr(loop, "LEDGER", tmp_path / "ledger.jsonl")
    return r


def _run(repo, *extra):
    args = loop.parse_args(["--goal", "add greeting", "--repo", str(repo),
                            "--skip", *NOUGEN_STAGES, "--no-pr", *extra])
    lp = loop.Loop(args)
    rc = lp.run()
    return rc, {r.stage: r for r in lp.results}


def test_dry_run_plans_writes_and_changes_nothing(repo):
    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
    head = _git(repo, "rev-parse", "HEAD").stdout
    rc, res = _run(repo, "--paths", "app.py")
    assert rc == 0
    assert res["build"].status == "ok"
    assert res["commit"].status == "planned"
    assert _git(repo, "rev-parse", "HEAD").stdout == head
    assert _git(repo, "branch", "--show-current").stdout.strip() == "main"


def test_apply_commits_only_given_paths_on_a_new_branch(repo):
    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (repo / "stray.txt").write_text("do not commit\n", encoding="utf-8")
    rc, res = _run(repo, "--paths", "app.py", "--message", "feat: greet", "--apply")
    assert rc == 0, res
    assert res["commit"].status == "ok"
    branch = _git(repo, "branch", "--show-current").stdout.strip()
    assert branch.startswith("loop/add-greeting-")
    files = _git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert files == ["app.py"]
    assert "stray.txt" in _git(repo, "status", "--short").stdout


def test_harden_blocks_secret_before_commit(repo):
    fake = "ghp_" + "A" * 36
    (repo / "app.py").write_text(f"TOKEN = '{fake}'\n", encoding="utf-8")
    rc, res = _run(repo, "--paths", "app.py", "--apply")
    assert rc == 1
    assert res["harden"].status == "failed"
    assert res["harden"].evidence["findings"][0]["line"] == 1
    assert res["commit"].status == "skipped" and res["commit"].reason == "not reached"


def test_failing_build_stops_the_loop(repo, monkeypatch):
    monkeypatch.setenv("NOUGEN_LOOP_TEST_CMD", f"{sys.executable} -c raise SystemExit(3)")
    monkeypatch.setenv("NOUGEN_LOOP_BUILD_ATTEMPTS", "1")
    rc, res = _run(repo, "--paths", "app.py", "--apply")
    assert rc == 1
    assert res["build"].status == "failed"
    assert res["commit"].reason == "not reached"


def test_pr_refuses_default_branch(repo, monkeypatch):
    monkeypatch.setattr(loop.shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
    args = loop.parse_args(["--goal", "x", "--repo", str(repo), "--apply", "--skip", *NOUGEN_STAGES, "build", "harden", "commit"])
    lp = loop.Loop(args)
    res = lp.st_pr()
    assert res.status == "failed" and "default branch" in res.reason


def test_no_paths_never_stages_everything(repo):
    (repo / "app.py").write_text("changed\n", encoding="utf-8")
    rc, res = _run(repo, "--apply")
    assert res["commit"].status == "skipped"
    assert "git add -A" in res["commit"].reason
    assert _git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_evolve_records_delta_between_runs(repo, tmp_path):
    _run(repo, "--paths", "app.py")
    (repo / "app.py").write_text("SECRET = 'ghp_" + "B" * 36 + "'\n", encoding="utf-8")
    _run(repo, "--paths", "app.py", "--keep-going")
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    second = json.loads(lines[1])
    assert second["stages"]["harden"] == "failed"


def test_refuses_to_commit_on_someone_elses_branch(repo):
    _git(repo, "checkout", "-q", "-b", "fix/another-agents-work")
    (repo / "app.py").write_text("print('mine')\n", encoding="utf-8")
    rc, res = _run(repo, "--paths", "app.py")
    assert rc == 1
    assert res["commit"].status == "failed"
    assert "fix/another-agents-work" in res["commit"].reason
    rc, res = _run(repo, "--paths", "app.py", "--on-current-branch")
    assert res["commit"].status == "planned"


def test_missing_test_program_fails_cleanly(repo, monkeypatch):
    monkeypatch.setenv("NOUGEN_LOOP_TEST_CMD", "no-such-program-xyz --run")
    monkeypatch.setenv("NOUGEN_LOOP_BUILD_ATTEMPTS", "1")
    rc, res = _run(repo, "--paths", "app.py")
    assert rc == 1
    assert res["build"].status == "failed"
    assert "program not found" in res["build"].evidence["tail"]


def test_relative_test_program_resolves_against_repo(repo, monkeypatch):
    runner = repo / "bin" / "check.py"
    runner.parent.mkdir()
    runner.write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setenv("NOUGEN_LOOP_TEST_CMD", f"{sys.executable} bin/check.py")
    rc, res = _run(repo, "--paths", "app.py")
    assert res["build"].status == "ok"


def test_missing_nougen_cli_degrades_to_skipped(repo, monkeypatch):
    monkeypatch.setattr(loop, "nougen_cli", lambda: None)
    args = loop.parse_args(["--goal", "x", "--repo", str(repo)])
    lp = loop.Loop(args)
    for stage in NOUGEN_STAGES:
        assert getattr(lp, f"st_{stage}")().status == "skipped"
