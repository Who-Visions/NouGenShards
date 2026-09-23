#!/usr/bin/env python3
"""Triage the relay registry: ``relay_triage.py [--me NODE] [--dir DIR] [--json] [--all]``.

Reads leg JSON from ``$NOUGEN_RELAY_DIR/.handoffs`` (default ``~/.nougen/relay/.handoffs``)
and prints only the legs a node should look at, plus counts for the rest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nougen_shards.relay_triage import SURFACE, summarize, triage  # noqa: E402


def load(handoffs: Path):
    for p in sorted(handoffs.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("id"):
            yield d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--me", default=os.environ.get("NOUGEN_MACHINE", ""))
    ap.add_argument("--dir", default=os.environ.get("NOUGEN_RELAY_DIR") or str(Path.home() / ".nougen" / "relay"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--all", action="store_true", help="show every leg, not just those to surface")
    a = ap.parse_args(argv)
    handoffs = Path(a.dir) / ".handoffs"
    if not handoffs.is_dir():
        print(f"no handoffs dir at {handoffs}", file=sys.stderr)
        return 2
    rows = triage(load(handoffs), a.me)
    counts = summarize(rows)
    shown = rows if a.all else [r for r in rows if r["label"] in SURFACE]
    if a.json:
        print(json.dumps({"counts": counts, "surface": shown}, indent=2))
    else:
        print("counts:", " ".join(f"{k}={v}" for k, v in counts.items() if v))
        for r in shown:
            print(f"{r['label']:<11} {r['id']}  {r['goal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
