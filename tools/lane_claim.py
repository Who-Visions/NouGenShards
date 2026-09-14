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
import fnmatch
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAIMS_DIR = Path(os.environ.get("NOUGEN_RELAY_LOCAL_DIR") or (
    Path.home() / "Watchtower" / "NouGen" / "NouGenRelay" / ".handoffs")) / "claims"
AGENT = os.environ.get("NOUGEN_AGENT", "unknown-agent")
MACHINE = os.environ.get("COMPUTERNAME", socket.gethostname()).lower()
TTL_HOURS = float(os.environ.get("NOUGEN_CLAIM_TTL_HOURS", 8))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _my_claim_path() -> Path:
    return CLAIMS_DIR / f"{MACHINE}__{AGENT}.json"


def active_claims() -> list[dict]:
    out = []
    if not CLAIMS_DIR.is_dir():
        return out
    for f in CLAIMS_DIR.glob("*.json"):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if c.get("status") == "released":
            continue
        try:
            born = datetime.strptime(c["created_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        ttl = float(c.get("ttl_hours", 8))
        if (datetime.now(timezone.utc) - born).total_seconds() < ttl * 3600:
            out.append(c)
    return out


def conflicts_for(paths: list[str], me_agent: str, me_machine: str) -> list[tuple[str, dict]]:
    """Paths claimed by someone who is not me."""
    hits = []
    for c in active_claims():
        if c.get("agent") == me_agent and c.get("machine") == me_machine:
            continue
        scopes = c.get("scope", "")
        scopes = scopes if isinstance(scopes, list) else [s.strip() for s in str(scopes).split(",") if s.strip()]
        for p in paths:
            norm = p.replace("\\", "/")
            for scope in scopes:
                if fnmatch.fnmatch(norm, scope) or norm == scope:
                    hits.append((p, c))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("claim")
    c.add_argument("scope", nargs="+", help="file paths or globs you are editing")
    c.add_argument("-g", "--goal", default="working", help="one-line goal")
    sub.add_parser("release")
    sub.add_parser("status")
    args = ap.parse_args()

    if args.cmd == "claim":
        CLAIMS_DIR.mkdir(parents=True, exist_ok=True)
        claim = {
            "machine": MACHINE, "agent": AGENT, "goal": args.goal,
            "scope": [s.replace("\\", "/") for s in args.scope],
            "created_utc": _now(), "ttl_hours": TTL_HOURS, "status": "active",
        }
        _my_claim_path().write_text(json.dumps(claim, indent=2), encoding="utf-8")
        print(f"claimed {claim['scope']} as {MACHINE}/{AGENT} (ttl {TTL_HOURS}h)")
        return 0
    if args.cmd == "release":
        p = _my_claim_path()
        if p.exists():
            c = json.loads(p.read_text(encoding="utf-8"))
            c["status"] = "released"
            p.write_text(json.dumps(c, indent=2), encoding="utf-8")
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
