#!/usr/bin/env python3
"""Recall eval: golden-set retrieval quality for the NouGen vault.

Absorbed from mraza007/echovault (MIT) `memory evaluate` / `--sweep`, rebuilt
for the 9-DB grid. Retrieval changes (rerank, embeddings, decay, thresholds)
must show a number, not a vibe: build a fixed golden set once, re-run it after
every change, and read the delta against the previous report.

Golden set (analysis/recall_eval/golden.json):
  title   - known-item: the shard's own title is the query (easy tier)
  body    - known-item: 5 content words spread through the body, title words
            excluded (the tier that shows whether recall finds meaning)
  manual  - hand-written {"query", "relevant": ["id@db", ...]}; kept on rebuild
  negatives - seeded nonsense queries; any hit above a threshold is a false positive
A shard with an identical title in another DB counts as the same item (mirrors).

Metrics: Recall@1/3/5/10, MRR, nDCG@k (first relevant hit), latency p50/p95,
and a threshold sweep per score field (final_score, utility_score_tripartite):
the best threshold is the one with the highest recall whose negative
false-positive rate stays under --fp-target.

Rank is measured before lost_in_the_middle_reorder (that interleave is for the
LLM reader, and would scramble MRR). Retrieval is read-only; nothing is written
to the vault. Reports land in analysis/recall_eval/report_<utc>.json.

Usage:
  python tools/recall_eval.py build [--n 75] [--neg 30] [--seed 7]
  python tools/recall_eval.py run [--k 10] [--no-embed] [--fp-target 0.2] [--domain *]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nougen_time import InvalidTimestampError, format_display_time

ANALYSIS = ROOT / "analysis" / "recall_eval"
GOLDEN = ANALYSIS / "golden.json"
KS = (1, 3, 5, 10)
SCORE_FIELDS = ("final_score", "utility_score_tripartite")
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]{4,}")
STOP = frozenset("""
about above after again against along already also because before being below
between both could doesn during every first from have into just later might more
most never other over should since some still such than that their them then
there these they this those through under until very were what when where which
while with would your shard shards nougen
""".split())


def _core():
    sys.path.insert(0, str(ROOT / "src"))
    from nougen_shards import core  # pylint: disable=import-outside-toplevel
    return core


# ---------------------------------------------------------------- queries

def body_query(title: str, content: str, n_terms: int = 5):
    """n_terms distinct content words spread through the body, title words and
    stopwords excluded. None when the body is too thin to make a fair query."""
    title_words = {w.lower() for w in TOKEN.findall(title or "")}
    seen, toks = set(), []
    for w in TOKEN.findall(content or ""):
        lw = w.lower()
        if lw in title_words or lw in STOP or lw in seen:
            continue
        seen.add(lw)
        toks.append(w)
    if len(toks) < n_terms:
        return None
    step = len(toks) / n_terms
    return " ".join(toks[int(i * step)] for i in range(n_terms))


def negative_queries(n: int, seed: int) -> list:
    """Seeded pseudo-words that should match nothing real."""
    rng = random.Random(seed * 7919)
    cons, vows = "bcdfghjklmnprstvwxz", "aeiou"

    def word():
        return "".join(rng.choice(cons) + rng.choice(vows) for _ in range(rng.randint(3, 4))) + rng.choice(cons)
    return [" ".join(word() for _ in range(3)) for _ in range(n)]


# ---------------------------------------------------------------- metrics

def first_rank(ranked: list, relevant) -> "int | None":
    for i, key in enumerate(ranked, 1):
        if key in relevant:
            return i
    return None


def score_query(ranked: list, relevant, k: int) -> dict:
    r = first_rank(ranked[:k], set(relevant))
    out = {f"recall@{x}": (1.0 if r and r <= x else 0.0) for x in KS if x <= k}
    out["mrr"] = 1.0 / r if r else 0.0
    out[f"ndcg@{k}"] = 1.0 / math.log2(r + 1) if r else 0.0
    out["rank"] = r
    return out


def aggregate(rows: list) -> dict:
    if not rows:
        return {"n": 0}
    keys = [k for k in rows[0] if k != "rank"]
    out = {"n": len(rows)}
    for k in keys:
        out[k] = round(statistics.fmean(r[k] for r in rows), 4)
    return out


def sweep(pos: list, neg: list, fp_target: float) -> dict:
    """pos: score of the first relevant hit per positive query (None = missed).
    neg: top score per negative query (None = empty result)."""
    observed = sorted({round(s, 6) for s in pos + neg if s is not None})
    if len(observed) > 24:
        observed = [observed[int(i * (len(observed) - 1) / 23)] for i in range(24)]
    rows = []
    for t in [0.0] + observed:
        rec = sum(1 for s in pos if s is not None and s >= t) / len(pos) if pos else 0.0
        fp = sum(1 for s in neg if s is not None and s >= t) / len(neg) if neg else 0.0
        rows.append({"threshold": t, "recall": round(rec, 4), "fp_rate": round(fp, 4)})
    ok = [r for r in rows if r["fp_rate"] <= fp_target]
    best = max(ok, key=lambda r: (r["recall"], -r["fp_rate"], r["threshold"])) if ok else None
    return {"best": best, "grid": rows}


# ---------------------------------------------------------------- build

def build(n: int, neg: int, seed: int, include_research: bool = False) -> dict:
    """Sample known items from the population recall actually serves. Bulk
    IMPORT/INGEST shards (arxiv etc.) are excluded from default recall, so
    sampling them measured the filter, not retrieval: the first golden set was
    68% research and read body Recall@10 0.28 when eligible shards scored 0.71."""
    core = _core()
    rng = random.Random(seed)
    bulk = () if include_research else tuple(core.bulk_ingest_event_types() or ())
    bulk_sql = f"AND UPPER(COALESCE(event_type, '')) NOT IN ({','.join('?' * len(bulk))}) " if bulk else ""
    dbs = [i for i in range(1, core.MAX_DB_COUNT + 1) if core.get_db_path(i).exists()]
    conns = {i: core.get_connection(i) for i in dbs}
    max_id = {i: conns[i].execute("SELECT max(id) FROM shards").fetchone()[0] or 0 for i in dbs}

    def equivalents(title):
        keys = []
        for i, c in conns.items():
            keys += [f"{r[0]}@{i}" for r in c.execute("SELECT id FROM shards WHERE title = ?", (title,))]
        return keys

    items, seen, tries = [], set(), 0
    while len(seen) < n and tries < n * 50:
        tries += 1
        db = rng.choice(dbs)
        row = conns[db].execute(
            "SELECT id, title, content FROM shards WHERE id >= ? AND COALESCE(enc, 0) = 0 "
            "AND COALESCE(sensitivity, 'normal') = 'normal' AND length(content) >= 200 "
            f"AND length(title) >= 12 {bulk_sql}ORDER BY id LIMIT 1", (rng.randint(1, max_id[db]), *bulk)).fetchone()
        if not row or f"{row[0]}@{db}" in seen:
            continue
        q = body_query(row[1], row[2])
        if not q:
            continue
        key = f"{row[0]}@{db}"
        seen.add(key)
        rel = equivalents(row[1]) or [key]
        items.append({"tier": "title", "query": row[1][:200], "relevant": rel, "target": key})
        items.append({"tier": "body", "query": q, "relevant": rel, "target": key})

    for c in conns.values():
        c.close()

    manual = []
    if GOLDEN.exists():
        manual = [q for q in json.loads(GOLDEN.read_text(encoding="utf-8")).get("queries", [])
                  if q.get("tier") == "manual"]
    golden = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "seed": seed, "include_research": include_research,
              "queries": items + manual, "negatives": negative_queries(neg, seed)}
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(golden, indent=1), encoding="utf-8")
    print(f"golden: {len(items)} known-item + {len(manual)} manual queries, "
          f"{len(golden['negatives'])} negatives -> {GOLDEN}")
    return golden


# ---------------------------------------------------------------- run

def _eastern(dt):
    try:
        return format_display_time(dt.isoformat(), paired=False)
    except (InvalidTimestampError, AttributeError):
        return None


def run(golden_path: Path, k: int, no_embed: bool, fp_target: float, domain: str) -> dict:
    if no_embed:
        os.environ["NOUGEN_QUERY_EMBED"] = "0"
    core = _core()
    core.lost_in_the_middle_reorder = list  # measure rank order, not the reader-facing interleave
    golden = json.loads(Path(golden_path).read_text(encoding="utf-8"))
    research = bool(golden.get("include_research", False))

    def search(q):
        return core.retrieve(q, limit=k, domain_key=domain, include_research=research)
    search("warm up the grid")

    per_query, by_tier, latencies = [], {}, []
    pos = {f: [] for f in SCORE_FIELDS}
    for it in golden["queries"]:
        t0 = time.perf_counter()
        res = search(it["query"])
        ms =(time.perf_counter() - t0) * 1000
        latencies.append(ms)
        ranked = [f"{r.get('id')}@{r.get('_db_index')}" for r in res]
        s = score_query(ranked, it["relevant"], k)
        by_tier.setdefault(it.get("tier", "manual"), []).append(s)
        hit = res[s["rank"] - 1] if s["rank"] else None
        for f in SCORE_FIELDS:
            pos[f].append(hit.get(f) if hit else None)
        per_query.append({"tier": it.get("tier"), "query": it["query"], "target": it.get("target"),
                          "rank": s["rank"], "ms": round(ms, 1), "top": ranked[:3]})

    neg = {f: [] for f in SCORE_FIELDS}
    for q in golden.get("negatives", []):
        res = search(q)
        for f in SCORE_FIELDS:
            neg[f].append(res[0].get(f) if res else None)

    now = datetime.now(timezone.utc)
    lat = sorted(latencies)
    report = {
        "created_utc": now.isoformat(timespec="seconds"), "created_eastern": _eastern(now),
        "config": {"k": k, "embed": not no_embed and os.environ.get("NOUGEN_QUERY_EMBED", "1") != "0",
                   "include_research": research,
                   "distill_lanes": os.environ.get("NOUGEN_DISTILL_LANES", "1") != "0",
                   "rerank": bool(getattr(core, "RERANK_ENABLED", False)), "domain": domain,
                   "fp_target": fp_target, "golden": str(golden_path), "golden_created": golden.get("created_utc")},
        "summary": {t: aggregate(rows) for t, rows in sorted(by_tier.items())},
        "overall": aggregate([s for rows in by_tier.values() for s in rows]),
        "latency_ms": {"p50": round(statistics.median(lat), 1),
                       "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1)} if lat else {},
        "negatives_nonempty": sum(1 for s in neg[SCORE_FIELDS[0]] if s is not None),
        "sweep": {f: sweep(pos[f], neg[f], fp_target) for f in SCORE_FIELDS},
        "per_query": per_query,
    }
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    previous = sorted(ANALYSIS.glob("report_*.json"))
    out = ANALYSIS / f"report_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    _print(report, json.loads(previous[-1].read_text(encoding="utf-8")) if previous else None, out)
    return report


def _print(rep: dict, prev, out: Path):
    k = rep["config"]["k"]
    cols = [f"recall@{x}" for x in KS if x <= k] + ["mrr", f"ndcg@{k}"]
    print(f"{'tier':8}{'n':>5}" + "".join(f"{c:>11}" for c in cols))
    for tier, agg in list(rep["summary"].items()) + [("ALL", rep["overall"])]:
        line = f"{tier:8}{agg['n']:>5}" + "".join(f"{agg.get(c, 0):>11.3f}" for c in cols)
        if tier == "ALL" and prev and prev.get("overall"):
            line += "   delta MRR " + f"{agg['mrr'] - prev['overall'].get('mrr', 0):+.3f}"
        print(line)
    print(f"latency ms p50 {rep['latency_ms'].get('p50')}  p95 {rep['latency_ms'].get('p95')}  "
          f"| negatives returning results: {rep['negatives_nonempty']}")
    for f, sw in rep["sweep"].items():
        b = sw["best"]
        print(f"sweep {f}: " + (f"t={b['threshold']:.4f} recall {b['recall']:.3f} fp {b['fp_rate']:.3f}"
                                if b else f"no threshold keeps fp <= {rep['config']['fp_target']}"))
    print(f"report -> {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--n", type=int, default=75)
    b.add_argument("--neg", type=int, default=30)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--include-research", action="store_true",
                   help="also sample bulk IMPORT/INGEST shards (excluded from default recall)")
    r = sub.add_parser("run")
    r.add_argument("--golden", type=Path, default=GOLDEN)
    r.add_argument("--k", type=int, default=10)
    r.add_argument("--no-embed", action="store_true")
    r.add_argument("--fp-target", type=float, default=0.2)
    r.add_argument("--domain", default="*")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        build(a.n, a.neg, a.seed, a.include_research)
    else:
        run(a.golden, a.k, a.no_embed, a.fp_target, a.domain)


if __name__ == "__main__":
    main()
