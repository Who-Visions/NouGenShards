"""Pre-commit lane guard - blocks the two moves that destroy teammates' work.

Installed as .git/hooks/pre-commit (source of truth here; the hook shells to
this file). Runs for EVERY agent and human committing in this tree, whatever
provider they ride - enforcement lives in git, not in any one model's memory.

Blocks, in order:
  1. CLAIM CONFLICT - a staged file falls inside another agent's active lane
     claim (tools/lane_claim.py, fleet-visible via relay_claim_list). The fix
     is coordination, not force: talk to the claim holder or wait for TTL.
  2. SWEEP COMMIT - more staged files than NOUGEN_COMMIT_SWEEP_MAX (fallback
     15) usually means `git add -A` in a shared tree, the exact move that
     swept a teammate's in-flight keymaker work into a stranger's commit on
     2026-08-28. Stage explicit paths instead.

Override (deliberate, logged, for the GM or a coordinated batch):
  NOUGEN_LANE_GUARD_OK=1 git commit ...
Identity: set NOUGEN_AGENT so conflicts name you correctly.
Env-first everywhere (Rule 0.2); a guard that cannot run warns and allows in
warn-only mode (NOUGEN_LANE_GUARD_ENFORCE=0) but ENFORCES by default - a
safety hook that defaults to off is decoration.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ENFORCE = os.environ.get("NOUGEN_LANE_GUARD_ENFORCE", "1") != "0"
SWEEP_MAX = int(os.environ.get("NOUGEN_COMMIT_SWEEP_MAX", 15))


def main() -> int:
    if os.environ.get("NOUGEN_LANE_GUARD_OK") == "1":
        print("[lane-guard] override acknowledged (NOUGEN_LANE_GUARD_OK=1) - allowed")
        return 0
    try:
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.split()
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"[lane-guard] could not read staged files ({type(exc).__name__}) - allowing")
        return 0
    if not staged:
        return 0

    problems = []
    try:
        import lane_claim
        me_agent = os.environ.get("NOUGEN_AGENT", "unknown-agent")
        me_machine = lane_claim.MACHINE
        for path, claim in lane_claim.conflicts_for(staged, me_agent, me_machine):
            problems.append(
                f"CLAIM CONFLICT: '{path}' is inside {claim['machine']}/{claim['agent']}'s "
                f"active lane ({claim.get('goal','')}). Coordinate with them or wait for the "
                f"claim TTL - do not commit over a teammate's in-flight work.")
    except Exception as exc:  # guard must never crash a commit unreadably
        print(f"[lane-guard] claim check unavailable ({type(exc).__name__}) - skipping that layer")

    if len(staged) > SWEEP_MAX:
        problems.append(
            f"SWEEP COMMIT: {len(staged)} files staged (max {SWEEP_MAX}). In a shared tree "
            f"this is how `git add -A` swallows a teammate's uncommitted work. Stage explicit "
            f"paths, or set NOUGEN_COMMIT_SWEEP_MAX / NOUGEN_LANE_GUARD_OK=1 for a deliberate batch.")

    if not problems:
        return 0
    print("[lane-guard] COMMIT " + ("BLOCKED" if ENFORCE else "WARNING (warn-only)"))
    for p in problems:
        print("[lane-guard]   " + p)
    return 1 if ENFORCE else 0


if __name__ == "__main__":
    sys.exit(main())
