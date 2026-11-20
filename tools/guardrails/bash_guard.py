#!/usr/bin/env python3
"""PreToolUse guard for shell commands. Exit 2 blocks the call.

Covers the actions that cannot be taken back once a lane gets them wrong:
pushing to a protected branch, force pushing, recursive deletes that leave
the worktree, and printing secret files through the shell. Anything that can
be undone stays a prompt rule; these are deny rules.

The permission deny list in .claude/settings.json is a prefix match, so it
misses `cd x && git push origin main`. This hook reads the whole command.

Config (env, all optional):
  NOUGEN_PROTECTED_BRANCHES  comma list, default "main,master"
  NOUGEN_BASH_GUARD          "off" disables the hook
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

_DEFAULT_PROTECTED = "main,master"
_SPLIT = re.compile(r"\|\||&&|[;|\n]")
_SECRET_FILE = re.compile(
    r"(^|[\\/\s'\"=])(\.env(\.[\w.-]+)?|[\w.-]+\.pem|id_(rsa|dsa|ecdsa|ed25519)[\w.-]*"
    r"|agent_secrets\.db)($|[\s'\"])|(^|[\\/~\s'\"])\.ssh[\\/]",
    re.IGNORECASE,
)
_READERS = {"cat", "type", "less", "more", "head", "tail", "bat", "strings",
            "get-content", "gc", "xxd", "base64", "cp", "copy", "scp", "curl"}


def protected_branches() -> set[str]:
    raw = os.environ.get("NOUGEN_PROTECTED_BRANCHES") or _DEFAULT_PROTECTED
    return {b.strip() for b in raw.split(",") if b.strip()}


def _git(cwd: str, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                             text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _norm(path: str, cwd: str) -> str | None:
    """Absolute, normalised path, or None when it cannot be resolved safely."""
    if not path or any(c in path for c in "$`*?"):
        return None
    if path.startswith("~"):
        path = os.path.expanduser(path)
    m = re.match(r"^/([a-zA-Z])/(.*)$", path)  # Git Bash drive form
    if m and os.name == "nt":
        path = f"{m.group(1)}:/{m.group(2)}"
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.normcase(os.path.realpath(path))


def _check_push(tok: list[str], cwd: str, branch: str | None) -> str | None:
    args = tok[tok.index("push") + 1:]
    prot = protected_branches()
    for a in args:
        if a == "--force" or (re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", a) is not None):
            return "force push is blocked (history on the remote cannot be restored)"
        if a.startswith("+") and len(a) > 1:
            return "force push by +refspec is blocked"
        if a == "--mirror":
            return "git push --mirror is blocked"
    refs = [a for a in args if not a.startswith("-")][1:]  # drop the remote
    if refs:
        for r in refs:
            dest = r.split(":")[-1]
            dest = dest[len("refs/heads/"):] if dest.startswith("refs/heads/") else dest
            if dest in prot:
                return f"push to protected branch '{dest}' is blocked; open a PR"
    else:
        cur = branch if branch is not None else _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
        if cur in prot:
            return f"push from protected branch '{cur}' is blocked; open a PR"
        if "--all" in args:
            return "git push --all is blocked (it includes protected branches)"
    return None


def _check_rm(tok: list[str], cwd: str, root: str) -> str | None:
    flags = "".join(a.lstrip("-") for a in tok[1:] if a.startswith("-") and not a.startswith("--"))
    longs = {a for a in tok[1:] if a.startswith("--")}
    recursive = "r" in flags.lower() or "--recursive" in longs
    if not recursive:
        return None
    root_n = os.path.normcase(os.path.realpath(root))
    for target in (a for a in tok[1:] if not a.startswith("-")):
        full = _norm(target, cwd)
        if full is None:
            return f"recursive delete of '{target}' cannot be resolved; refused"
        if full == root_n or not full.startswith(root_n + os.sep):
            return f"recursive delete outside the worktree is blocked: {target}"
    return None


def check(command: str, cwd: str, root: str | None = None,
          branch: str | None = None) -> str | None:
    """Return the reason the command is refused, or None when it may run."""
    root = root or _git(cwd, "rev-parse", "--show-toplevel") or cwd
    for seg in _SPLIT.split(command):
        tok = _tokens(seg.strip())
        if not tok:
            continue
        while tok and ("=" in tok[0] and not tok[0].startswith("-")):
            tok = tok[1:]  # leading VAR=value
        if not tok:
            continue
        head = os.path.basename(tok[0]).lower()
        head = head[:-4] if head.endswith(".exe") else head
        if head == "git" and "push" in tok:
            why = _check_push(tok, cwd, branch)
            if why:
                return why
        if head in ("rm", "rmdir", "remove-item", "del", "rd"):
            if head in ("remove-item", "del", "rd", "rmdir"):
                rec = any(a.lower() in ("-recurse", "-r", "/s") for a in tok[1:])
                tok2 = ["rm", "-r" if rec else "", *[a for a in tok[1:]
                        if not a.startswith(("-", "/"))]]
                tok2 = [t for t in tok2 if t]
            else:
                tok2 = tok
            why = _check_rm(tok2, cwd, root)
            if why:
                return why
        if head in _READERS and _SECRET_FILE.search(" " + " ".join(tok[1:]) + " "):
            return "reading or copying a secret file through the shell is blocked"
    return None


def main() -> int:
    if (os.environ.get("NOUGEN_BASH_GUARD") or "").lower() == "off":
        return 0
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    command = (event.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str) or not command.strip():
        return 0
    cwd = event.get("cwd") or os.getcwd()
    why = check(command, cwd)
    if why:
        sys.stderr.write(f"[guardrails] BLOCKED: {why}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
