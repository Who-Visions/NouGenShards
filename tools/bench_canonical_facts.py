"""Age-bucket latency benchmark for the local canonical fact index.

Run with: PYTHONPATH=src python tools/bench_canonical_facts.py --rows 5000 --repeat 100
This measures local SQLite lookup only; it excludes federation, MCP and model time.
"""
import argparse
import random
import statistics
import tempfile
import time
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nougen_shards.canonical_facts import CanonicalFactIndex


def make_snapshot(day: int, as_of: date) -> dict:
    machines = ["blade1tb", "phoebus", "whoart"]
    as_of_text = as_of.isoformat()
    captured_at = datetime.combine(as_of, datetime_time(12), ZoneInfo("America/New_York")).isoformat()
    per_machine = {name: {"value": str(day * 100 + offset), "exact": True}
                   for offset, name in enumerate(machines)}
    total = sum(int(row["value"]) for row in per_machine.values())
    return {
        "canonical_key": "token_usage:fleet:history", "intent": "fleet token usage history",
        "entities": ["fleet", "token_usage"], "aliases": {"fleet": ["all machine tokens history"]},
        "metric_namespace": "token_usage", "artifact_kind": "FACT_SNAPSHOT", "canonical": True,
        "temporal": {"timezone": "America/New_York", "period": "DAILY", "year": as_of.year,
                     "as_of": as_of_text, "event_at": as_of_text, "captured_at": captured_at},
        "scope": {"expected_machines": machines, "expected_entities": ["fleet", "token_usage"]},
        "per_machine": per_machine, "total": str(total),
        "completeness": {"state": "complete", "missing_machines": []},
        "provenance": {"source_ids": [f"benchmark:{day}"],
                       "source_hashes": {"benchmark": f"{day:064x}"}},
        "version": day + 1, "supersedes": None,
    }


def percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)

    def percentile(value: float) -> float:
        return ordered[min(len(ordered) - 1, max(0, int((value * len(ordered)) + 0.999999) - 1))]

    return {"p50_ms": round(statistics.median(ordered), 4),
            "p95_ms": round(percentile(0.95), 4), "p99_ms": round(percentile(0.99), 4)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--repeat", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260916)
    args = parser.parse_args()
    if args.rows < 31 or args.repeat < 1:
        parser.error("--rows must be >= 31 and --repeat must be >= 1")

    machines = ["blade1tb", "phoebus", "whoart"]
    entities = ["fleet", "token_usage"]
    november = "2025-11-30"
    current_date = date.today()
    historical_date = date(2025, 11, 30)
    if current_date <= historical_date:
        parser.error("the current date must be later than the November 2025 historical bucket")
    current = current_date.isoformat()
    with tempfile.TemporaryDirectory(prefix="nougen-facts-bench-") as tmp:
        path = Path(tmp) / "facts.sqlite"
        writer = CanonicalFactIndex(path)
        for day in range(args.rows):
            if day < 30:
                as_of = date(2025, 11, 1) + timedelta(days=day)
            else:
                span = (current_date - historical_date).days
                as_of = historical_date + timedelta(days=span * (day - 29) // (args.rows - 30))
            writer.put(make_snapshot(day, as_of))
        del writer
        index = CanonicalFactIndex(path, create=False)

        scenarios = {
            "november_2025_hit": november,
            "current_hit": current,
            "november_2025_miss": "2025-11-30",
            "current_miss": current,
        }
        query_for = {
            "november_2025_hit": ("token_usage:fleet:history", november),
            "current_hit": ("token_usage:fleet:history", None),
            "november_2025_miss": ("missing:historical:key", november),
            "current_miss": ("missing:current:key", None),
        }
        first_open = {}
        for name, (key, as_of) in query_for.items():
            started = time.perf_counter()
            result = index.resolve(key, expected_machines=machines, expected_entities=entities, as_of=as_of)
            first_open[name] = (time.perf_counter() - started) * 1000
            if name.endswith("_hit") and result["status"] != "complete":
                raise SystemExit(f"benchmark lookup failed: {name}")
            if name.endswith("_miss") and result["status"] != "cannot_determine":
                raise SystemExit(f"benchmark miss contract failed: {name}")

        rng = random.Random(args.seed)
        workload = [name for name in scenarios for _ in range(args.repeat)]
        rng.shuffle(workload)
        samples = {name: [] for name in scenarios}
        for name in workload:
            key, as_of = query_for[name]
            started = time.perf_counter()
            index.resolve(key, expected_machines=machines, expected_entities=entities, as_of=as_of)
            samples[name].append((time.perf_counter() - started) * 1000)

        result = {
            "rows": args.rows,
            "queries_per_bucket": args.repeat,
            "historical_as_of": november,
            "current_as_of": current,
            "first_query_ms": {key: round(value, 4) for key, value in first_open.items()},
            "warm_local_lookup": {key: percentiles(value) for key, value in samples.items()},
            "scope": "local SQLite only; no federation, MCP, filesystem discovery, or model time",
        }
        print(result)


if __name__ == "__main__":
    main()
