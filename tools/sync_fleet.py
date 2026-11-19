#!/usr/bin/env python3
"""
Fleet Auto-Sync CLI Tool.
Synchronizes all fleet repositories across WhoVisions and Who-Visions without
requiring manual 'git stash && git pull --rebase origin <branch>' executions.

Usage:
    python3 tools/sync_fleet.py [--all] [--push] [--json] [--repo <path>]
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nougen_shards.fleet_sync import FleetSyncManager


def main():
    parser = argparse.ArgumentParser(description="Fleet Auto-Sync & Rebase Utility")
    parser.add_argument("--repo", type=str, default=None, help="Explicit repository path to sync")
    parser.add_argument("--no-push", dest="auto_push", action="store_false", default=True, help="Fetch and rebase only, do not push")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    manager = FleetSyncManager()
    explicit = [Path(args.repo)] if args.repo else None
    results = manager.sync_all(explicit_paths=explicit, auto_push=args.auto_push)

    if args.json:
        data = [r.__dict__ for r in results]
        print(json.dumps(data, indent=2))
        return

    print("=" * 80)
    print("🔄 NouGen Fleet Auto-Sync Engine — Upstream Rebase & Alignment")
    print("=" * 80)
    for r in results:
        if r.status == "skipped":
            continue
        icon = "✅" if r.status in ("synced", "up_to_date", "pushed") else "⚠️" if "dirty" in r.status else "❌"
        print(f"{icon} {r.repo_name:<28} [{r.branch:<25}] status: {r.status}")
        if r.details:
            print(f"   Details: {r.details}")
        if r.error:
            print(f"   Error:   {r.error}")
    print("=" * 80)
    print("✨ Sync cycle complete. All working trees aligned.")


if __name__ == "__main__":
    main()
