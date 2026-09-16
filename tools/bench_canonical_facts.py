"""Local resolver latency benchmark; uses only a temporary SQLite index.

Run with: PYTHONPATH=src python tools/bench_canonical_facts.py --rows 1000 --repeat 100
"""
import argparse
import statistics
import tempfile
import time
from pathlib import Path

from nougen_shards.canonical_facts import CanonicalFactIndex


def make_snapshot(day: int) -> dict:
    machines = ["blade1tb", "phoebus", "whoart"]
    per_machine = {name: {"value": str(day * 100 + offset), "exact": True}
                   for offset, name in enumerate(machines)}
    total = sum(int(row["value"]) for row in per_machine.values())
    date = "2026-09-16"
    return {
        "canonical_key": "token_usage:fleet:YTD:2026", "intent": "fleet token usage YTD",
        "entities": ["fleet", "token_usage"], "aliases": {"fleet": ["all machines"]},
        "metric_namespace": "token_usage", "artifact_kind": "FACT_SNAPSHOT", "canonical": True,
        "temporal": {"timezone": "America/New_York", "period": "YTD", "year": 2026,
                     "as_of": date, "event_at": date, "captured_at": date + "T12:00:00-04:00"},
        "scope": {"expected_machines": machines, "expected_entities": ["fleet", "token_usage"]},
        "per_machine": per_machine, "total": str(total),
        "completeness": {"state": "complete", "missing_machines": []},
        "provenance": {"source_ids": [f"benchmark:{day}"], "source_hashes": {"benchmark": f"{day:064x}"}},
        "version": day, "supersedes": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--repeat", type=int, default=50)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="nougen-facts-bench-") as tmp:
        index = CanonicalFactIndex(Path(tmp) / "facts.sqlite")
        for day in range(1, args.rows + 1):
            index.put(make_snapshot(day))
        samples = []
        for _ in range(args.repeat):
            started = time.perf_counter()
            result = index.resolve("token_usage:fleet:YTD:2026",
                                   expected_machines=["blade1tb", "phoebus", "whoart"],
                                   expected_entities=["fleet", "token_usage"])
            samples.append((time.perf_counter() - started) * 1000)
            if result["status"] != "complete":
                raise SystemExit("resolver failed to select a canonical snapshot")
        ordered = sorted(samples)
        p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
        print({"rows": args.rows, "queries": args.repeat,
               "p50_ms": round(statistics.median(samples), 3), "p95_ms": round(p95, 3),
               "result_as_of": result["snapshot"]["temporal"]["as_of"]})


if __name__ == "__main__":
    main()
