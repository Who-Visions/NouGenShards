"""Lane claims - the fleet's "I am working here" signal, enforced by pre-commit.

Dave built the relay so parallel agents share the field without stepping on
each other; 2026-08-28 an agent (claude-cli) swept another agent's in-flight
keymaker work into its own commit with `git add -A`, then nearly reverted it.
This module is the self-awareness layer that makes that mechanically hard:

  claim   - declare the file scope you are editing (glob), fleet-visible via
            relay_claim_list (same JSON schema the fleet worker reads).
  release - mark your claim released.
  status  - list active claims (what pre-commit consults).

Usage (from the repo root, any agent, any provider):
  python tools/lane_claim.py claim  "src/nougen_shards/keymaker.py" -g "vertex token work"
  python tools/lane_claim.py status
  python tools/lane_claim.py release

Identity comes from NOUGEN_AGENT (the cross-provider contract already in
CLAUDE.md/AGENTS.md); machine from COMPUTERNAME. Claims expire by TTL
(NOUGEN_CLAIM_TTL_HOURS, fallback 8) so a crashed agent never wedges the repo.
Every environment-shaped value resolves env-first (Rule 0.2).
"""
from __future__ import annotations

import argparse
import sys

from nougen_shards.lane_claim import (
    AGENT,
    MACHINE,
    active_claims,
    claim_lane,
    release_lane,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="NouGen Lane Claims & Execution Enforcement")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("claim", help="Claim a file scope and enforce immediate execution")
    c.add_argument("scope", nargs="+", help="file paths or globs you are editing")
    c.add_argument("-g", "--goal", default="working", help="one-line goal")
    c.add_argument("--exec", dest="execute_cmd", default=None,
                   help="command to execute immediately upon claiming (forces work)")
    c.add_argument("--ttl", dest="ttl_hours", type=float, default=None,
                   help="claim TTL in hours")

    sub.add_parser("release", help="Release active lane claim")
    sub.add_parser("status", help="List active lane claims")
    args = ap.parse_args()

    if args.cmd == "claim":
        res = claim_lane(
            scope=args.scope,
            goal=args.goal,
            agent=AGENT,
            machine=MACHINE,
            ttl_hours=args.ttl_hours,
            execute_cmd=args.execute_cmd,
        )
        claim = res["claim"]
        print(f"claimed {claim['scope']} as {MACHINE}/{AGENT} (ttl {claim['ttl_hours']}h)")
        if res.get("shard_replicated"):
            print("✓ Claim replicated natively into NouGen shards cluster.")
        if res.get("wake_dispatch"):
            print("✓ Immediate work enforcement ping broadcast across fleet bus.")
        if res.get("execution_pid"):
            print(f"✓ Immediate execution launched (PID {res['execution_pid']}): {args.execute_cmd}")
        return 0

    if args.cmd == "release":
        ok = release_lane(agent=AGENT, machine=MACHINE)
        if ok:
            print("released")
        else:
            print("no claim on file")
        return 0

    # status
    live = active_claims()
    if not live:
        print("no active claims - every scope is free")
    for c in live:
        print(f"- {c['machine']}/{c['agent']}: {c.get('goal','')} scope={c.get('scope')} since {c['created_utc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
