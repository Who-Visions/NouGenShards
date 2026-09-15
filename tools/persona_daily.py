#!/usr/bin/env python3
"""NouGen Persona Daily Rebuilder.

Runs nightly (or on demand) to discover all `via:` scopes active in the last 7 days
and rebuild their deterministic personas into ~/.nougen/shards/personas.json.
"""
import sys
from pathlib import Path

# Ensure src is on path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from nougen_shards.persona import rebuild_recent_personas

def main():
    print("[*] Rebuilding active personas from 9-DB grid (last 7 days)...")
    res = rebuild_recent_personas(days=7, tz="America/New_York")
    print(f"✓ Successfully rebuilt {len(res)} active personas:")
    for s, fp in res.items():
        print(f"  • {s} -> {fp}")

if __name__ == "__main__":
    main()
