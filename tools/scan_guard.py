"""PreToolUse hook: block broad filesystem scans of the Watchtower/NouGen roots.

GM rule (2026-07-11, memory: no-deep-dives-recall-first): never tree-scan the
1M+ file roots. Vault recall -> ask Dave -> narrow delegated inspection.
Blocks: recursive grep/rg/find/ls -R aimed at the Watchtower or NouGen ROOT
(deeper subdirectory scans stay allowed), and Grep/Glob tool calls whose path
is one of those roots. Fails open on any parse error (a guard must never wedge
the session).
"""
import sys
import json
import re

# Root paths in Windows and Git Bash forms; NOT followed by a deeper segment.
ROOT = r"(?:[A-Za-z]:[\\/]+Users[\\/]+super[\\/]+Watchtower|/[a-z]/Users/super/Watchtower)"
ROOT_ARG = re.compile(ROOT + r"(?:[\\/]+NouGen)?[\\/]*(?=[\"'\s]|$)", re.IGNORECASE)
# Recursive scanners: grep -r/-R, rg (recursive by default), find, ls -R.
RECURSIVE = re.compile(
    r"(?:\bgrep\b[^|;&\n]*\s-[a-zA-Z]*[rR]|\brg\b|\bfind\s|\bls\s+[^|;&\n]*-[a-zA-Z]*R)"
)

REASON = (
    "Blocked: broad scan of the Watchtower/NouGen roots (1M+ files). "
    "GM standing rule: vault recall (nougen-shards / nougen-fleet-registry) first, "
    "ask Dave second, narrow delegated inspection third. Scoped subdirectory "
    "searches (e.g. NouGenShards-push-main/tools) are still allowed."
)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    deny = False

    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        if ROOT_ARG.search(cmd) and RECURSIVE.search(cmd):
            deny = True
    elif tool in ("Grep", "Glob"):
        path = ti.get("path", "") or ""
        if path and ROOT_ARG.fullmatch(path.strip()):
            deny = True

    if deny:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": REASON,
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
