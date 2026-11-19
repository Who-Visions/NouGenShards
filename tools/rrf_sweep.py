#!/usr/bin/env python3
"""Sweep per-lane RRF weights and k against the recall_eval golden set.

Weighted RRF beats uniform RRF only when the weights are chosen on data the
final number is not reported on (arXiv 2610.24341, 2610.30612). This tool
splits the golden queries by a seeded shuffle, picks the best config on the
train half by MRR, and reports that config against the uniform baseline on the
held-out half. Read-only: it changes env vars in-process, never the vault.

Usage:
  python tools/rrf_sweep.py [--golden analysis/recall_eval/golden.json] [--k 10] [--seed 11]
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import recall_eval  # noqa: E402  pylint: disable=wrong-import-position

BASELINE = {"weights": "", "k": 60}


def candidate_configs() -> list:
    """A small grid around uniform: lane emphasis x k. 20 configs (phoebus budget)."""
    out = [dict(BASELINE)]
    emph = [
        "vector=2", "keyword=2", "vector=0.5", "keyword=0.5",
        "title=2,exact=2", "vector=2,title=2", "keyword=2,title=2",
        "vector=1.5,keyword=0.75", "vector=0.75,keyword=1.5",
    ]
    for w, k in itertools.product([""] + emph, (20, 60)):
        cfg = {"weights": w, "k": k}
        if cfg != BASELINE:
            out.append(cfg)
    return out


def evaluate(core, queries: list, cfg: dict, k: int, research: bool) -> dict:
    os.environ["NOUGEN_RRF_WEIGHTS"] = cfg["weights"]
    os.environ["NOUGEN_RRF_K"] = str(cfg["k"])
    rows = []
    for it in queries:
        res = core.retrieve(it["query"], limit=k, domain_key="*", include_research=research)
        ranked = [f"{r.get('id')}@{r.get('_db_index')}" for r in res]
        rows.append(recall_eval.score_query(ranked, it["relevant"], k))
    return recall_eval.aggregate(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--golden", default=str(recall_eval.GOLDEN))
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=str(recall_eval.ANALYSIS / "rrf_sweep.json"))
    a = ap.parse_args(argv)

    golden = json.loads(Path(a.golden).read_text(encoding="utf-8"))
    research = bool(golden.get("include_research", False))
    qs = list(golden["queries"])
    random.Random(a.seed).shuffle(qs)
    train, test = qs[: len(qs) // 2], qs[len(qs) // 2:]

    core = recall_eval._core()  # pylint: disable=protected-access
    core.lost_in_the_middle_reorder = list
    core.retrieve("warm up the grid", limit=a.k, domain_key="*")

    scored = []
    for cfg in candidate_configs():
        m = evaluate(core, train, cfg, a.k, research)
        scored.append((m.get("mrr", 0.0), cfg, m))
        print(f"train mrr={m.get('mrr', 0):.4f} k={cfg['k']:>3} w={cfg['weights'] or 'uniform'}", flush=True)
    scored.sort(key=lambda t: t[0], reverse=True)
    best = scored[0][1]

    base_test = evaluate(core, test, BASELINE, a.k, research)
    best_test = evaluate(core, test, best, a.k, research)
    rep = {"seed": a.seed, "n_train": len(train), "n_test": len(test), "best": best,
           "test_baseline": base_test, "test_best": best_test,
           "train_top5": [{"cfg": c, "mrr": s} for s, c, _ in scored[:5]]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps({"best": best, "test_baseline": base_test, "test_best": best_test}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
