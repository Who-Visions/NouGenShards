#!/usr/bin/env python3
"""PreToolUse hook: run pr_merge_gate before any PR merge.

Reads the Claude Code PreToolUse JSON on stdin. For a Bash call containing
`gh pr merge`, or a GitHub MCP merge_pull_request call, it resolves the repo
and PR number at run time, runs the gate, and denies the call unless the gate
reads CLEAR. Gate exit 1 (blocked) or 2 (state unreadable) both deny: an
unreadable state is never a green light. `--admin` is always denied.

Nothing machine-, lane- or account-specific is baked in. Repo and PR come from
the command, its URL, or the working directory's own gh context. Checks known to
be red for a non-code reason (for example billing on a private repo) are named
in NOUGEN_MERGE_GATE_ALLOW_RED, a comma separated list.

Install (any node): point a PreToolUse hook at this file, matcher
"Bash|mcp__.*merge_pull_request.*". See tools/hooks/README_merge_gate.md.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

_SEPARATORS = {"&&", "||", ";", "|", "&", "\n"}
_PR_URL = re.compile(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)")
_API_MERGE = re.compile(r"repos/([^/\s]+/[^/\s]+)/pulls/(\d+)/merge")
_RAW_MERGE = re.compile(r"\bgh(?:\.exe)?\s+pr\s+merge\b")


def _tokens(command: str) -> list:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return command.split()


def merge_segments_cwd(command: str, base_cwd: Optional[str] = None) -> list:
    """Return (args after the merge subcommand, effective cwd) for each merge in a command line.

    A `cd <dir>` earlier in the chain moves the directory the merge really runs in.
    """
    out: list = []
    seg: list = []
    cwd = base_cwd
    for tok in _tokens(command) + [";"]:
        if tok in _SEPARATORS or tok.strip() == "":
            if len(seg) >= 2 and seg[0] in ("cd", "pushd", "Set-Location", "sl"):
                target = seg[1]
                cwd = target if os.path.isabs(target) or not cwd else os.path.join(cwd, target)
            for i in range(len(seg) - 2):
                if os.path.basename(seg[i]).lower() in ("gh", "gh.exe") and seg[i + 1] == "pr" and seg[i + 2] == "merge":
                    out.append((seg[i + 3:], cwd))
                    break
            seg = []
        else:
            seg.append(tok)
    return out


def merge_segments(command: str) -> list:
    """Return the argument lists (after the merge subcommand) for each merge in a command line."""
    return [args for args, _cwd in merge_segments_cwd(command)]


def api_merge_targets(command: str) -> list:
    """`gh api -X PUT repos/<o>/<r>/pulls/<n>/merge` merges a PR without `gh pr merge`."""
    if not re.search(r"\bgh(?:\.exe)?\s+api\b", command):
        return []
    return [(m.group(1), int(m.group(2))) for m in _API_MERGE.finditer(command)]


# Merge flags that consume the next token as their value; that token is never the PR number.
_VALUE_FLAGS = {"-b", "--body", "-F", "--body-file", "-t", "--subject", "-A", "--author-email",
                "--match-head-commit"}


def parse_merge_args(args: list) -> dict:
    info = {"repo": None, "pr": None, "admin": False}
    skip = False
    for i, tok in enumerate(args):
        if skip:
            skip = False
            continue
        if tok == "--admin":
            info["admin"] = True
        elif tok in ("--repo", "-R") and i + 1 < len(args):
            info["repo"] = args[i + 1]
            skip = True
        elif tok.startswith("--repo="):
            info["repo"] = tok.split("=", 1)[1]
        elif tok in _VALUE_FLAGS:
            skip = True
        elif tok.startswith("-"):
            continue
        elif info["pr"] is None:
            info["pr"] = tok
    return info


def _gh_json(args: list, cwd: Optional[str]) -> dict:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=30, cwd=cwd or None)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"gh exited {out.returncode}")
    return json.loads(out.stdout)


def resolve_target(info: dict, cwd: Optional[str]) -> tuple:
    """Resolve (repo, pr_number) from explicit args, a PR URL, or the cwd's gh context."""
    repo, pr = info.get("repo"), info.get("pr")
    if pr:
        m = _PR_URL.search(pr)
        if m:
            return m.group(1), int(m.group(2))
        if pr.isdigit():
            if not repo:
                repo = _gh_json(["repo", "view", "--json", "nameWithOwner"], cwd)["nameWithOwner"]
            return repo, int(pr)
    # a branch name, or nothing: let gh say which PR that is
    view = ["pr", "view"] + ([pr] if pr else []) + (["--repo", repo] if repo else []) + ["--json", "number,url"]
    data = _gh_json(view, cwd)
    m = _PR_URL.search(data.get("url", ""))
    if not m:
        raise RuntimeError("could not resolve the PR from gh")
    return m.group(1), int(data["number"])


def mcp_target(tool_input: dict) -> tuple:
    owner = tool_input.get("owner")
    repo = tool_input.get("repo")
    num = tool_input.get("pullNumber", tool_input.get("pull_number", tool_input.get("number")))
    if not (owner and repo and num):
        raise RuntimeError("merge_pull_request call without owner/repo/pullNumber")
    return f"{owner}/{repo}", int(num)


def run_gate(repo: str, pr: int) -> tuple:
    import pr_merge_gate  # sibling module

    allow = {n.strip() for n in os.environ.get("NOUGEN_MERGE_GATE_ALLOW_RED", "").split(",") if n.strip()}
    try:
        blocks, notes = pr_merge_gate.evaluate(repo, pr, allow)
    except Exception as exc:  # fail closed
        return 2, f"merge gate: UNREADABLE for {repo}#{pr}: {exc}"
    if blocks:
        return 1, f"merge gate: {repo}#{pr} BLOCKED: " + "; ".join(blocks)
    return 0, f"merge gate: {repo}#{pr} CLEAR" + ("".join(f" (note: {n})" for n in notes))


def decide(payload: dict) -> Optional[str]:
    """Return a denial reason, or None to allow."""
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd")
    targets: list = []
    try:
        if tool == "Bash" or tool == "PowerShell":
            for args, seg_cwd in merge_segments_cwd(str(tool_input.get("command", "")), cwd):
                info = parse_merge_args(args)
                if info["admin"]:
                    return "merge denied: --admin bypasses the gate and branch protection"
                targets.append(resolve_target(info, seg_cwd))
            targets.extend(api_merge_targets(str(tool_input.get("command", ""))))
            if not targets and _RAW_MERGE.search(str(tool_input.get("command", ""))):
                return "merge gate: a `gh pr merge` is hidden inside a quoted string; run it directly so the gate can read it"
        elif re.search(r"merge_pull_request", tool):
            targets.append(mcp_target(tool_input))
    except Exception as exc:  # cannot tell which PR this merges: never a green light
        return f"merge gate: could not resolve the PR being merged ({exc})"
    for repo, pr in targets:
        code, text = run_gate(repo, pr)
        if code != 0:
            return text
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # not a hook call we understand; never wedge unrelated tools
    reason = decide(payload)
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
