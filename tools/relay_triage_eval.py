#!/usr/bin/env python3
"""Rule arm vs model arm over real legs: ``relay_triage_eval.py [--me NODE] [--limit N] [--ids ID,...]``.

Prints per-leg disagreements and a surface/silent confusion table with the
rule arm as the reference. The rule arm is NOT ground truth -- this measures
agreement, and every disagreement is a leg for a human to label.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nougen_shards.relay_triage import SURFACE, confusion  # noqa: E402
from nougen_shards.relay_triage_model import shadow  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--me", default=os.environ.get("NOUGEN_MACHINE", ""))
    ap.add_argument("--dir", default=os.environ.get("NOUGEN_RELAY_DIR") or str(Path.home() / ".nougen" / "relay"))
    ap.add_argument("--limit", type=int, default=20, help="newest N legs")
    ap.add_argument("--ids", default="", help="comma-separated leg ids instead of newest N")
    ap.add_argument("--backends", default=None)
    a = ap.parse_args(argv)
    files = sorted((Path(a.dir) / ".handoffs").glob("*.json"))
    if a.ids:
        want = {i.strip() for i in a.ids.split(",") if i.strip()}
        files = [p for p in files if p.stem in want]
    else:
        files = files[-a.limit:]
    rows = []
    for p in files:
        try:
            leg = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        leg.setdefault("id", p.stem)
        r = shadow(leg, a.me, backends=a.backends)
        rows.append(r)
        mark = "  " if r["agree_surface"] else "!!"
        print(f"{mark} rule={r['rule']:<11} model={str(r['model']):<11} {r['backend'] or '-':<13} {r['id']}", flush=True)
    answered = [r for r in rows if r["model"]]
    print(f"\nlegs={len(rows)} model_answered={len(answered)} "
          f"label_agree={sum(r['agree'] for r in answered)} surface_agree={sum(r['agree_surface'] for r in answered)}")
    if answered:
        print("surface confusion (model vs rule reference):",
              confusion([r["model"] for r in answered], [r["rule"] for r in answered], tuple(SURFACE)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
