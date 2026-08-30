"""Gridion recall benchmark: latency percentiles + golden-query accuracy.

Runs the local retrieval stack (core.retrieve and federation.federated_retrieve)
against the live grid and reports p50/p95 latency plus hit-rate on a golden set
of (query, expected-title-substring) pairs. Exits nonzero when either budget is
missed so it can gate CI or a pre-push hook.

All budgets are env-first (Rule 0.2):
  NOUGEN_BENCH_P95_S        latency budget for core.retrieve, seconds (default 8.0)
  NOUGEN_BENCH_FED_P95_S    latency budget for federated_retrieve (default 15.0)
  NOUGEN_BENCH_MIN_ACC      minimum golden hit rate 0..1 (default 0.6)
  NOUGEN_BENCH_TOPK         top-k window a golden hit must land in (default 3)
  NOUGEN_BENCH_GOLDEN       path to a JSON file [[query, expected_substring], ...]
                            overriding the built-in set
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.core import retrieve  # noqa: E402
from nougen_shards.federation import federated_retrieve  # noqa: E402

# Built-in golden set: stable, era-spanning shards known to live in the grid.
# The canary shard exists specifically to be found by recall tests.
DEFAULT_GOLDEN = [
    ["seventeen lanterns in the Grand'Anse fog", "seventeen lanterns"],
    ["lane claim ttl enforcement", "claim"],
    ["gateway auth probe outpost", "gateway"],
    ["recall latency pin node", "recall"],
    ["shards capture provenance relay", "captur"],
]


def _f(env: str, fallback: float) -> float:
    raw = os.environ.get(env, "")
    try:
        return float(raw) if raw.strip() else fallback
    except ValueError:
        print(f"[bench] {env}={raw!r} invalid, using {fallback}", file=sys.stderr)
        return fallback


def _golden() -> list:
    path = os.environ.get("NOUGEN_BENCH_GOLDEN", "")
    if path.strip():
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return DEFAULT_GOLDEN


def _pct(vals, q):
    vals = sorted(vals)
    idx = min(len(vals) - 1, max(0, round(q * (len(vals) - 1))))
    return vals[idx]


def run() -> int:
    topk = int(_f("NOUGEN_BENCH_TOPK", 3))
    golden = _golden()
    if not golden:
        print("[bench] FAIL golden set is empty (NOUGEN_BENCH_GOLDEN)", file=sys.stderr)
        return 1

    # Warm pass: pays one-time process costs (vector cache load, model load)
    # so measured numbers reflect steady-state service latency.
    t0 = time.time()
    retrieve("bench warmup", limit=1)
    warm_s = time.time() - t0
    print(f"[bench] warmup (vector-cache load etc.): {warm_s:.2f}s")

    report = {"warmup_s": round(warm_s, 2), "lanes": {}}
    failures = []
    for lane_name, fn, p95_env, p95_default in [
        ("retrieve", retrieve, "NOUGEN_BENCH_P95_S", 8.0),
        ("federated", federated_retrieve, "NOUGEN_BENCH_FED_P95_S", 15.0),
    ]:
        lat, hits = [], 0
        for query, expected in golden:
            t = time.time()
            results = fn(query, limit=max(topk, 3))
            dt = time.time() - t
            lat.append(dt)
            titles = " || ".join((r.get("title") or "")[:120] for r in results[:topk])
            hit = expected.lower() in titles.lower()
            hits += hit
            print(f"[bench] {lane_name} {dt:6.2f}s {'HIT ' if hit else 'MISS'} "
                  f"q={query[:40]!r} top={titles[:90]!r}")
        acc = hits / len(golden) if golden else 0.0
        p50, p95 = _pct(lat, 0.5), _pct(lat, 0.95)
        budget = _f(p95_env, p95_default)
        min_acc = _f("NOUGEN_BENCH_MIN_ACC", 0.6)
        report["lanes"][lane_name] = {
            "p50_s": round(p50, 2), "p95_s": round(p95, 2),
            "mean_s": round(statistics.mean(lat), 2),
            "accuracy": round(acc, 2), "n": len(golden),
        }
        if p95 > budget:
            failures.append(f"{lane_name}: p95 {p95:.2f}s > budget {budget:.2f}s")
        if acc < min_acc:
            failures.append(f"{lane_name}: accuracy {acc:.2f} < {min_acc:.2f}")

    print(json.dumps(report, indent=2))
    if failures:
        for f in failures:
            print(f"[bench] FAIL {f}", file=sys.stderr)
        return 1
    print("[bench] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(run())
