"""Eval: intent_alignment_check vs a goal-text-only baseline on synthetic scenarios.

The baseline sees only the task contract (as a planner without execution-plane
state would) and therefore always answers ALIGNED. Results prove wiring on
synthetic data, not production value.

    PYTHONPATH=src python tools/eval_control_loop.py
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nougen_shards.control_loop import intent_alignment_check  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "synthetic_control_loop", ROOT / "tests" / "fixtures" / "synthetic_control_loop.py")
fx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fx)


def baseline(goal: dict) -> str:
    return "ALIGNED"


def main() -> int:
    rows, agg = [], {"checker": 0, "baseline": 0, "n": 0,
                     "checker_false_conflict": 0, "baseline_missed_conflict": 0,
                     "checker_missed_conflict": 0, "unknown_coerced_aligned": 0}
    for name, goal, execution, expected, _ in fx.scenarios():
        got = intent_alignment_check(goal, execution, now=fx.NOW)["verdict"]
        base = baseline(goal)
        agg["n"] += 1
        agg["checker"] += got == expected
        agg["baseline"] += base == expected
        agg["checker_false_conflict"] += expected != "CONFLICTED" and got == "CONFLICTED"
        agg["checker_missed_conflict"] += expected == "CONFLICTED" and got != "CONFLICTED"
        agg["baseline_missed_conflict"] += expected == "CONFLICTED" and base != "CONFLICTED"
        agg["unknown_coerced_aligned"] += expected == "UNKNOWN" and got == "ALIGNED"
        rows.append({"scenario": name, "expected": expected, "checker": got, "baseline": base})
    print(json.dumps({"summary": agg, "rows": rows}, indent=2))
    return 0 if agg["checker"] == agg["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
