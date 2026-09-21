#!/usr/bin/env python3
"""Score a labeled corpus: ``eval_decision_plane.py CORPUS.jsonl --labels A,B,C [--baseline BASE.jsonl]``.

Each JSONL row: {"truth","predicted"(null=abstain),"confidence","probabilities","latency_ms",
"cost_usd","escalated","repeat_predictions"}. Prints an EvalReport as JSON; with --baseline,
also prints the promotion gates that FAIL (an empty list means every gate passed).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nougen_shards.decision.calibration import EvalRecord, evaluate, promotion_gate  # noqa: E402


def load(path: Path):
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            d["repeat_predictions"] = tuple(d.get("repeat_predictions") or ())
            out.append(EvalRecord(**d))
        except (ValueError, TypeError) as exc:
            raise SystemExit(f"{path}:{i}: bad record: {exc}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--labels", required=True, help="comma-separated label set")
    ap.add_argument("--baseline", type=Path, default=None)
    ap.add_argument("--min-examples", type=int, default=300)
    a = ap.parse_args(argv)
    labels = [s.strip() for s in a.labels.split(",") if s.strip()]
    report = evaluate(load(a.corpus), labels)
    out = {"report": dataclasses.asdict(report)}
    if a.baseline:
        base = evaluate(load(a.baseline), labels)
        out["failed_gates"] = promotion_gate(report, base, min_examples=a.min_examples)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
