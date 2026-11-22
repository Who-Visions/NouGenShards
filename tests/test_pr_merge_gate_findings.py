"""Review findings on the merge gate: flag values, effective cwd, and thread pagination."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "hooks"))
hook = importlib.import_module("pr_merge_gate_hook")
gate = importlib.import_module("pr_merge_gate")


def test_flag_values_are_never_the_pr_number():
    info = hook.parse_merge_args(["--body", "123", "7", "--repo", "o/r", "--squash"])
    assert info["pr"] == "7" and info["repo"] == "o/r"


def test_short_flag_values_are_consumed_too():
    assert hook.parse_merge_args(["-t", "title", "-b", "9", "8"])["pr"] == "8"
    assert hook.parse_merge_args(["--match-head-commit", "abc", "5"])["pr"] == "5"


def test_gate_is_asked_about_the_real_pr(monkeypatch):
    seen = []
    monkeypatch.setattr(hook, "run_gate", lambda repo, pr: (seen.append((repo, pr)) or (1, "BLOCKED")))
    cmd = "gh pr merge --body 123 7 --repo o/r --squash"
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "."}
    assert hook.decide(payload) == "BLOCKED" and seen == [("o/r", 7)]


def test_cd_moves_the_effective_directory():
    segs = hook.merge_segments_cwd("cd /other/repo && gh pr merge 7 --squash", "/start")
    assert segs == [(["7", "--squash"], "/other/repo")]


def test_relative_cd_joins_the_base_directory():
    segs = hook.merge_segments_cwd("cd sub && gh pr merge 7", "/start")
    assert segs[0][1].replace("\\", "/") == "/start/sub"


def test_target_resolves_in_the_effective_directory(monkeypatch):
    dirs = []

    def fake_resolve(info, cwd):
        dirs.append(cwd)
        return "o/r", 7

    monkeypatch.setattr(hook, "resolve_target", fake_resolve)
    monkeypatch.setattr(hook, "run_gate", lambda repo, pr: (0, "CLEAR"))
    payload = {"tool_name": "Bash", "tool_input": {"command": "cd /other && gh pr merge 7"}, "cwd": "/start"}
    assert hook.decide(payload) is None and dirs == ["/other"]


def _page(nodes, nxt=None):
    return json.dumps({"data": {"repository": {"pullRequest": {"reviewThreads": {
        "pageInfo": {"hasNextPage": nxt is not None, "endCursor": nxt}, "nodes": nodes}}}}})


def test_unresolved_thread_on_a_later_page_is_counted(monkeypatch):
    pages = [_page([{"isResolved": True}] * 100, "c1"), _page([{"isResolved": False}])]
    calls = []

    def fake_gh(*args):
        calls.append(args)
        return pages[len(calls) - 1]

    monkeypatch.setattr(gate, "gh", fake_gh)
    assert gate.threads_unresolved("o/r", 5) == 1
    assert len(calls) == 2 and any("after=c1" in a for a in calls[1])
