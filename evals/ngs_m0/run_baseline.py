"""NGS M0: baseline numbers for the CURRENT recall stack on the labeled set.

Reads evals/ngs_m0/labeled_v1.json (see build_labeled_set.py), points
NOUGEN_VAULT_DIR at the same SNAPSHOT the labels were built from, runs
core.retrieve per query, and reports Recall@1/5/10, MRR, nDCG@10 (binary
relevance) and latency p50/p95/p99, plus the no-answer false-answer rate.

Modes
  fast_local  (default) keyword/FTS only via core.FAST_LOCAL: no embedder, no
              vector lane, no RRF. Safe on the 16 GB Phoebus mini.
  hybrid      full stack (vector + RRF). Loads embedding caches: opt in with
              --mode hybrid only when swap is quiet. Results are labeled by mode.

A hit is a result whose title equals the gold title (replicated copies of one
shard share a title) or whose (db, id) is a gold pair.

Abstention: the current stack has NO abstain path, so every no-answer query
returns results. That 100% false-answer rate IS the baseline for spec section 9's
abstention target; it is reported, not scored against a threshold.

Usage:
  python evals/ngs_m0/run_baseline.py [--mode fast_local|hybrid] [--limit 10] \
      [--labels FILE] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def pct(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, max(0, round(q * (len(vals) - 1))))] if vals else None


def is_hit(res: dict, item: dict) -> bool:
    if (res.get("title") or "") == item["gold_title"]:
        return True
    return any(res.get("id") == g["id"] and res.get("_db_index") in (None, g["db"]) for g in item["gold"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fast_local", "hybrid"], default="fast_local")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--labels", default=str(HERE / "labeled_v1.json"))
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    labels = json.loads(Path(a.labels).read_text(encoding="utf-8"))
    snap = os.path.expanduser(labels["snapshot_dir"])
    os.environ["NOUGEN_VAULT_DIR"] = snap  # the snapshot the labels refer to, never the live vault
    sys.path.insert(0, str(ROOT / "src"))
    from nougen_shards import core  # noqa: E402  (after the env var, on purpose)

    if a.mode == "fast_local":
        core.FAST_LOCAL.set(True)
    core.retrieve("ngs m0 warmup", limit=1)

    lat, rr, ndcg, r1, r5, r10 = [], [], [], 0, 0, 0
    ans = [i for i in labels["items"] if i["kind"] == "answerable"]
    for it in ans:
        t = time.perf_counter()
        res = core.retrieve(it["query"], limit=a.limit)
        lat.append(time.perf_counter() - t)
        rank = next((n for n, r in enumerate(res, 1) if is_hit(r, it)), None)
        r1 += rank == 1
        r5 += rank is not None and rank <= 5
        r10 += rank is not None and rank <= 10
        rr.append(1 / rank if rank else 0.0)
        ndcg.append(1 / math.log2(rank + 1) if rank and rank <= 10 else 0.0)  # one relevant doc: IDCG = 1
    noans = [i for i in labels["items"] if i["kind"] == "no_answer"]
    false_answers = 0
    for it in noans:
        t = time.perf_counter()
        res = core.retrieve(it["query"], limit=a.limit)
        lat.append(time.perf_counter() - t)
        false_answers += bool(res)
    n = len(ans)
    try:
        sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        sha = None
    out = {
        "schema": "ngs-m0-baseline/1",
        "mode": a.mode,
        "code_sha": sha,
        "labels_sha256": labels["items_sha256"],
        "snapshot_at": labels["snapshot_at"],
        "host": os.environ.get("NGS_M0_HOST", "local"),
        "python": platform.python_version(),
        "n_answerable": n,
        "n_no_answer": len(noans),
        "recall_at_1": round(r1 / n, 4),
        "recall_at_5": round(r5 / n, 4),
        "recall_at_10": round(r10 / n, 4),
        "mrr": round(statistics.fmean(rr), 4),
        "ndcg_at_10": round(statistics.fmean(ndcg), 4),
        "latency_s": {"p50": round(pct(lat, .5), 3), "p95": round(pct(lat, .95), 3),
                      "p99": round(pct(lat, .99), 3), "max": round(max(lat), 3), "n": len(lat)},
        "no_answer_false_answer_rate": round(false_answers / len(noans), 4) if noans else None,
        "caveats": [
            "labels are lexically easy (trimmed copies of gold bodies); regression guard, not a +10 pp proof",
            "single run, no bootstrap CI: n is small",
            "latency on one shared mini under memory pressure; engine-only targets need an idle box",
            "current stack has no abstain path: false-answer rate is the baseline, not a score",
        ],
    }
    text = json.dumps(out, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
