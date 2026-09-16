"""Benchmark: single-shot vs bounded retrieval-angle sweep on the synthetic fixture.

CPU only, no network, no live vault. Usage:
    PYTHONPATH=src python tools/bench_angle_sweep.py [--repeat N]
"""
import argparse
import importlib.util
import json
import os
import statistics
import time
from pathlib import Path

from nougen_shards.reconstruction import SweepConfig, retrieval_angle_sweep, single_shot

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "synthetic_reconstruction_vault", ROOT / "tests" / "fixtures" / "synthetic_reconstruction_vault.py")
fx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fx)


def run(mode: str, repeat: int) -> dict:
    cfg = SweepConfig.from_env()
    hits = fps = abstain = calls = 0
    lat = []
    for q, expected in fx.BAD_QUERIES:
        for _ in range(repeat):
            vaults = fx.build_vaults()
            t = time.perf_counter()
            if mode == "single_shot":
                env = single_shot(q, vaults, known_entities=fx.ENTITIES, config=cfg)
            else:
                env = retrieval_angle_sweep(q, vaults, aliases=fx.ALIASES,
                                            known_entities=fx.ENTITIES, config=cfg)
            lat.append((time.perf_counter() - t) * 1000.0)
        calls += env.calls
        if env.answer_key == expected:
            hits += 1
        elif env.answer_key is None:
            abstain += 1
        else:
            fps += 1
    n = len(fx.BAD_QUERIES)
    return {"mode": mode, "queries": n, "hit_rate": hits / n, "false_positives": fps,
            "abstained": abstain, "calls_total": calls, "calls_per_query": calls / n,
            "latency_ms_median": round(statistics.median(lat), 3),
            "latency_ms_p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=int(os.environ.get("NOUGEN_BENCH_REPEAT", "5")))
    args = ap.parse_args()
    base, sw = run("single_shot", args.repeat), run("sweep", args.repeat)
    sw["extra_calls_per_query"] = sw["calls_per_query"] - base["calls_per_query"]
    print(json.dumps({"single_shot": base, "sweep": sw}, indent=2))


if __name__ == "__main__":
    main()
