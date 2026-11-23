#!/usr/bin/env python3
"""Verification gate: run the checks, exit 2 when any fails.

Usable three ways: as a Stop hook (`--hook`, runs the fast profile only when
the tree has changes, blocks once per stop), from a shell before a push, and
from CI. Exit 2 rather than 1 because the harness treats 1 as "noted" and
marks the turn complete; 2 hands the failure back to the lane.

Checks resolve in this order, so nothing here is fixed in code:
  1. NOUGEN_VERIFY_CMDS  (commands separated by ";;")
  2. tools/guardrails/verify.json  {"fast": [[...]], "full": [[...]]}
  3. a logged fallback: byte-compile the changed Python files

In a command, the word "python" is replaced by the running interpreter.
A check whose program is not installed is skipped and reported, not failed.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_CONFIG = os.path.join(_HERE, "verify.json")
_TAIL = int(os.environ.get("NOUGEN_VERIFY_TAIL_LINES") or 25)
_TIMEOUT = int(os.environ.get("NOUGEN_VERIFY_TIMEOUT_S") or 900)


def changed_files() -> list[str]:
    try:
        out = subprocess.run(["git", "-C", _REPO, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [ln[3:].split(" -> ")[-1].strip().strip('"') for ln in out.splitlines() if ln[3:]]


def commands(profile: str) -> tuple[list[list[str]], str]:
    env = os.environ.get("NOUGEN_VERIFY_CMDS")
    if env:
        return [shlex.split(c) for c in env.split(";;") if c.strip()], "NOUGEN_VERIFY_CMDS"
    if os.path.isfile(_CONFIG):
        with open(_CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
        if cfg.get(profile):
            return [list(c) for c in cfg[profile]], f"verify.json:{profile}"
    py = [f for f in changed_files() if f.endswith(".py") and os.path.isfile(os.path.join(_REPO, f))]
    return ([["python", "-m", "py_compile", *py]] if py else []), "fallback (py_compile on changed files)"


def run(cmds: list[list[str]]) -> list[tuple[str, int, str]]:
    failures = []
    for cmd in cmds:
        cmd = [sys.executable if c == "python" else c for c in cmd]
        label = " ".join(cmd[1:] if cmd[0] == sys.executable else cmd)
        if cmd[0] != sys.executable and shutil.which(cmd[0]) is None:
            sys.stderr.write(f"[guardrails] verify: skipped, not installed: {cmd[0]}\n")
            continue
        try:
            proc = subprocess.run(cmd, cwd=_REPO, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=_TIMEOUT)
            code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = 124, f"timed out after {_TIMEOUT}s"
        except OSError as exc:
            code, out = 127, str(exc)
        if code != 0:
            failures.append((label, code, "\n".join(out.splitlines()[-_TAIL:])))
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", default=os.environ.get("NOUGEN_VERIFY_PROFILE") or "fast")
    ap.add_argument("--hook", action="store_true", help="Stop-hook mode: read the event on stdin")
    args = ap.parse_args()
    if (os.environ.get("NOUGEN_VERIFY") or "").lower() == "off":
        return 0
    if args.hook:
        try:
            event = json.load(sys.stdin)
        except (ValueError, OSError):
            event = {}
        if event.get("stop_hook_active") or not changed_files():
            return 0
    cmds, source = commands(args.profile)
    failures = run(cmds)
    if not failures:
        if not args.hook:
            print(f"[guardrails] verify ok: {len(cmds)} check(s) from {source}")
        return 0
    sys.stderr.write(f"[guardrails] VERIFY FAILED ({source}): {len(failures)} of {len(cmds)}\n")
    for label, code, tail in failures:
        sys.stderr.write(f"--- {label} (exit {code})\n{tail}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
