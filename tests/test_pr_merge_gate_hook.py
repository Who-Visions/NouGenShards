"""pr_merge_gate_hook: parse merge commands, deny on a blocked or unreadable gate."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "hooks"))
hook = importlib.import_module("pr_merge_gate_hook")


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "."}


def test_plain_command_is_ignored():
    assert hook.decide(bash("git status && echo gh pr view 5")) is None


def test_merge_segments_found_in_chains():
    segs = hook.merge_segments("cd x && gh pr merge 7 --repo a/b --squash; echo done")
    assert segs == [["7", "--repo", "a/b", "--squash"]]


def test_admin_is_always_denied():
    reason = hook.decide(bash("gh pr merge 7 --repo a/b --admin"))
    assert reason and "--admin" in reason


def test_blocked_gate_denies(monkeypatch):
    monkeypatch.setattr(hook, "run_gate", lambda repo, pr: (1, f"merge gate: {repo}#{pr} BLOCKED: x"))
    reason = hook.decide(bash("gh pr merge 7 --repo a/b --squash"))
    assert reason and "a/b#7" in reason and "BLOCKED" in reason


def test_unreadable_gate_denies(monkeypatch):
    monkeypatch.setattr(hook, "run_gate", lambda repo, pr: (2, "merge gate: UNREADABLE"))
    assert hook.decide(bash("gh pr merge 7 --repo a/b")) is not None


def test_clear_gate_allows(monkeypatch):
    monkeypatch.setattr(hook, "run_gate", lambda repo, pr: (0, "CLEAR"))
    assert hook.decide(bash("gh pr merge https://github.com/a/b/pull/9 --squash")) is None


def test_url_target_resolves_without_gh():
    assert hook.resolve_target({"repo": None, "pr": "https://github.com/o/r/pull/12"}, None) == ("o/r", 12)


def test_unresolvable_pr_denies(monkeypatch):
    def boom(info, cwd):
        raise RuntimeError("no pr")
    monkeypatch.setattr(hook, "resolve_target", boom)
    reason = hook.decide(bash("gh pr merge"))
    assert reason and "could not resolve" in reason


def test_mcp_merge_is_gated(monkeypatch):
    seen = []
    monkeypatch.setattr(hook, "run_gate", lambda repo, pr: (seen.append((repo, pr)) or (1, "BLOCKED")))
    payload = {"tool_name": "mcp__github__merge_pull_request", "tool_input": {"owner": "o", "repo": "r", "pullNumber": 4}}
    assert hook.decide(payload) == "BLOCKED" and seen == [("o/r", 4)]


def test_mcp_merge_missing_fields_denies():
    payload = {"tool_name": "mcp__github__merge_pull_request", "tool_input": {"owner": "o"}}
    assert hook.decide(payload) and "could not resolve" in hook.decide(payload)


def test_non_json_stdin_never_wedges(monkeypatch):
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert hook.main() == 0


def test_api_put_merge_is_gated(monkeypatch):
    seen = []
    monkeypatch.setattr(hook, "run_gate", lambda repo, pr: (seen.append((repo, pr)) or (1, "BLOCKED")))
    cmd = "gh api -X PUT repos/o/r/pulls/33/merge -f merge_method=squash"
    assert hook.decide(bash(cmd)) == "BLOCKED" and seen == [("o/r", 33)]


def test_api_read_of_pulls_is_not_a_merge():
    assert hook.decide(bash("gh api repos/o/r/pulls/33")) is None


def test_merge_hidden_in_quotes_is_denied():
    reason = hook.decide(bash("bash -c 'gh pr merge 5 --repo o/r'"))
    assert reason and "hidden" in reason
