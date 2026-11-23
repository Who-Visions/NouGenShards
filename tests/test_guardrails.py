"""Guardrails: deny rules, shell guard, staged secret scan, exit-2 gates."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "tools" / "guardrails"
sys.path.insert(0, str(GUARD))

import bash_guard  # noqa: E402
import secret_scan  # noqa: E402
import stop_receipt  # noqa: E402


def _run(script: str, stdin: str = "", env: dict | None = None, args=()):
    return subprocess.run(
        [sys.executable, str(GUARD / script), *args], input=stdin, capture_output=True,
        text=True, env={**os.environ, **(env or {})}, cwd=str(REPO), timeout=120)


# --- committed deny rules -------------------------------------------------

def test_settings_carry_the_irreversible_deny_rules():
    cfg = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = cfg["permissions"]["deny"]
    for rule in ("Read(./.env)", "Read(**/*.pem)", "Read(~/.ssh/**)",
                 "Read(**/id_rsa*)", "Bash(git push --force:*)",
                 "Bash(git push origin main:*)"):
        assert rule in deny
    hooks = json.dumps(cfg["hooks"])
    for script in ("bash_guard.py", "stop_receipt.py", "verify.py"):
        assert script in hooks


def test_settings_file_is_not_gitignored():
    out = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", ".claude/settings.json"])
    assert out.returncode == 1


# --- shell guard ----------------------------------------------------------

ROOT = str(REPO)


@pytest.mark.parametrize("cmd", [
    "git push origin main",
    "git push origin HEAD:main",
    "git push origin feature:refs/heads/master",
    "cd sub && git push --force origin lane/x",
    "git push -f origin lane/x",
    "git push origin +lane/x",
    "git push --mirror",
    "rm -rf /",
    "rm -rf ..",
    "rm -rf ~/work",
    "rm -fr $HOME/x",
    "rm -rf .",
    "cat .env",
    "cat ~/.ssh/id_ed25519",
    "head -5 config/server.pem",
])
def test_guard_blocks(cmd):
    assert bash_guard.check(cmd, ROOT, root=ROOT, branch="lane/x")


@pytest.mark.parametrize("cmd", [
    "git push origin lane/x",
    "git push -u origin lane/x",
    "git push --force-with-lease origin lane/x",
    "git status && git log --oneline -3",
    "rm -rf build",
    "rm -rf ./tests/__pycache__",
    "rm notes.txt",
    "cat README.md",
    "python -m pytest tests -q",
])
def test_guard_allows(cmd):
    assert bash_guard.check(cmd, ROOT, root=ROOT, branch="lane/x") is None


def test_bare_push_on_protected_branch_is_blocked():
    assert bash_guard.check("git push", ROOT, root=ROOT, branch="main")
    assert bash_guard.check("git push", ROOT, root=ROOT, branch="lane/x") is None


def test_protected_branches_come_from_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_PROTECTED_BRANCHES", "release")
    assert bash_guard.check("git push origin release", ROOT, root=ROOT, branch="x")
    assert bash_guard.check("git push origin main", ROOT, root=ROOT, branch="x") is None


def test_guard_hook_exits_2():
    event = json.dumps({"tool_name": "Bash", "cwd": ROOT,
                        "tool_input": {"command": "git push --force origin main"}})
    proc = _run("bash_guard.py", event)
    assert proc.returncode == 2
    assert "BLOCKED" in proc.stderr
    ok = _run("bash_guard.py", json.dumps({"cwd": ROOT, "tool_input": {"command": "git status"}}))
    assert ok.returncode == 0


# --- staged secret scan ---------------------------------------------------

def _diff(path: str, *added: str) -> str:
    body = "".join(f"+{ln}\n" for ln in added)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(added)} @@\n{body}"


# Built at run time so this file never holds a credential-shaped literal.
FAKE_KEY = "gh" + "p_" + "A1b2" * 10


def test_scan_reports_path_and_line():
    hits = secret_scan.scan(_diff("app/config.py", "x = 1", f'TOKEN = "{FAKE_KEY}"'), globs=[])
    assert [(p, n) for p, n, _ in hits] == [("app/config.py", 2)]


def test_scan_ignores_removed_and_clean_lines():
    diff = _diff("a.py", "x = 1").replace("+x = 1", f"-TOKEN = '{FAKE_KEY}'\n+x = 1")
    assert secret_scan.scan(diff, globs=[]) == []


def test_scan_honours_allow_globs():
    assert secret_scan.scan(_diff("tests/fixtures/k.txt", FAKE_KEY), globs=["tests/fixtures/*"]) == []


def test_fallback_detector_catches_a_key(monkeypatch):
    monkeypatch.setitem(sys.modules, "nougen_shards.credential_patterns", None)
    detect, redact, source = secret_scan.load_detector()
    assert source == "built-in fallback"
    assert detect(FAKE_KEY) and FAKE_KEY not in redact(f"k={FAKE_KEY}")


def test_scan_blocks_a_real_commit(tmp_path):
    def git(*a):
        return subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True)
    git("init", "-q")
    (tmp_path / "leak.py").write_text(f'TOKEN = "{FAKE_KEY}"\n', encoding="utf-8")
    git("add", "leak.py")
    proc = subprocess.run([sys.executable, str(GUARD / "secret_scan.py")], cwd=str(tmp_path),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert "leak.py:1" in proc.stderr
    assert FAKE_KEY not in proc.stderr


# --- stop hook: no receipt, no done ---------------------------------------

def _transcript(tmp_path, *assistant_blocks, tool_output: str = ""):
    rows = [{"type": "user", "message": {"content": "fix the bug"}}]
    rows.append({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}]}})
    rows.append({"type": "user", "message": {"content": [
        {"type": "tool_result", "content": tool_output}]}})
    for text in assistant_blocks:
        rows.append({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return str(path)


def test_done_without_receipt_exits_2(tmp_path):
    event = json.dumps({"transcript_path": _transcript(tmp_path, "All fixed and done.")})
    proc = _run("stop_receipt.py", event)
    assert proc.returncode == 2
    assert "NO RECEIPT" in proc.stderr


@pytest.mark.parametrize("text,tool_output", [
    ("Fixed in commit 3f9a1c2.", ""),
    ("Done, see https://example.test/org/repo/pull/12.", ""),
    ("The fix is done.", "===== 41 passed in 2.10s ====="),
    ("Done. Captured as shard 1234.", ""),
])
def test_done_with_receipt_passes(tmp_path, text, tool_output):
    event = json.dumps({"transcript_path": _transcript(tmp_path, text, tool_output=tool_output)})
    assert _run("stop_receipt.py", event).returncode == 0


def test_honest_not_done_passes(tmp_path):
    event = json.dumps({"transcript_path": _transcript(tmp_path, "This is not done; the test still fails.")})
    assert _run("stop_receipt.py", event).returncode == 0


def test_second_stop_is_not_blocked_again(tmp_path):
    event = json.dumps({"stop_hook_active": True,
                        "transcript_path": _transcript(tmp_path, "All done.")})
    assert _run("stop_receipt.py", event).returncode == 0


def test_chat_turn_without_tools_is_left_alone():
    assert stop_receipt.verdict("Yes, that is done.", "Yes, that is done.", used_tool=False) is None


def test_stop_hook_fails_open_on_garbage():
    assert _run("stop_receipt.py", "not json").returncode == 0


# --- verify gate ----------------------------------------------------------

def test_verify_exits_2_on_a_failing_check():
    proc = _run("verify.py", env={"NOUGEN_VERIFY_CMDS": 'python -c "import sys; sys.exit(3)"'})
    assert proc.returncode == 2
    assert "VERIFY FAILED" in proc.stderr and "exit 3" in proc.stderr


def test_verify_passes_and_skips_missing_tools():
    proc = _run("verify.py", env={
        "NOUGEN_VERIFY_CMDS": 'python -c "print(1)" ;; no-such-linter-xyz --check'})
    assert proc.returncode == 0
    assert "not installed: no-such-linter-xyz" in proc.stderr


# Review threads on PR 1110 (Codex P1s): cd must move the guard's idea of the
# working directory, and value-taking push options must not shift the refspec.
@pytest.mark.parametrize("cmd", [
    "cd /tmp && rm -rf important",
    "cd / ; rm -rf etc",
    "pushd /tmp && rm -rf important",
    "(cd /tmp && rm -rf important)",
    "cd $SOMEWHERE && rm -rf build",
    "git push --repo=origin HEAD:main",
    "git push --repo origin HEAD:main",
    "git push -o ci.skip origin HEAD:main",
    "git push --push-option=x origin main",
])
def test_guard_blocks_review_cases(cmd):
    assert bash_guard.check(cmd, ROOT, root=ROOT, branch="lane/x")


@pytest.mark.parametrize("cmd", [
    "cd tools && rm -rf __pycache__",
    "git push --repo=origin HEAD:lane/x",
    "git push -o ci.skip origin lane/x",
])
def test_guard_allows_review_cases(cmd):
    assert bash_guard.check(cmd, ROOT, root=ROOT, branch="lane/x") is None


def test_bare_push_after_unresolvable_cd_is_refused():
    assert bash_guard.check("cd $X && git push", ROOT, root=ROOT, branch="lane/x")


# Second review round on PR 1110 (aiwithdav3 P2s): HEAD resolves to the current
# branch, and only the real git subcommand decides whether it is a push.
def test_push_of_head_resolves_to_the_current_branch():
    assert bash_guard.check("git push origin HEAD", ROOT, root=ROOT, branch="main")
    assert bash_guard.check("git push origin @", ROOT, root=ROOT, branch="main")
    assert bash_guard.check("git push origin HEAD", ROOT, root=ROOT, branch="lane/x") is None


@pytest.mark.parametrize("cmd", [
    "git commit -m push",
    "git checkout -b push",
    "git log --grep push",
])
def test_push_as_an_argument_is_not_a_push(cmd):
    assert bash_guard.check(cmd, ROOT, root=ROOT, branch="main") is None


def test_global_options_before_push_are_skipped():
    assert bash_guard.check("git -c core.x=1 push origin main", ROOT, root=ROOT, branch="lane/x")
    assert bash_guard.check("git --no-pager push origin HEAD:main", ROOT, root=ROOT, branch="lane/x")


# Third review round on PR 1110: aiwithdav3's headless review (at 14a4204c)
# claimed these three were allowed. They are blocked; pinned so it stays that way.
def test_force_after_cd_is_still_blocked():
    assert bash_guard.check("cd tools && git push --force origin lane/x", ROOT, root=ROOT, branch="lane/x")


def test_recursive_delete_of_the_worktree_root_is_blocked():
    assert bash_guard.check("rm -rf .", ROOT, root=ROOT, branch="lane/x")


@pytest.mark.parametrize("dest", ["refs/heads/master", "refs/heads/main"])
def test_src_to_full_protected_ref_is_blocked(dest):
    assert bash_guard.check(f"git push origin feature:{dest}", ROOT, root=ROOT, branch="lane/x")
