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
import tempfile
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

# Structured retrieval error taxonomy (P6 regression gate)
ERROR_MISSED_SHARD = "MISSED_SHARD"
ERROR_STALE_RANK = "STALE_RANK"
ERROR_WRONG_DOMAIN = "WRONG_DOMAIN"
ERROR_TENANT_LEAK = "TENANT_LEAK"
ERROR_FALSE_POSITIVE = "FALSE_POSITIVE"
ERROR_LATENCY_BREACH = "LATENCY_BREACH"
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


def classify_query_failure(
    ranked: list,
    relevant,
    results: list,
    *,
    expected_domain: str | None = None,
    k: int = 10,
    stale_rank_cutoff: int = 3,
    latency_ms: float = 0.0,
    max_latency_ms: float | None = None,
) -> list[str]:
    """Classify retrieval failure modes for a single positive query."""
    errors: list[str] = []
    rank = first_rank(ranked[:k], set(relevant))
    if rank is None:
        errors.append(ERROR_MISSED_SHARD)
    elif rank > stale_rank_cutoff:
        errors.append(ERROR_STALE_RANK)

    if expected_domain and expected_domain != "*":
        for row in results[:k]:
            dom = row.get("domain_key") if isinstance(row, dict) else None
            if dom is not None and dom != expected_domain:
                errors.append(ERROR_WRONG_DOMAIN)
                break

    if max_latency_ms is not None and latency_ms > max_latency_ms:
        errors.append(ERROR_LATENCY_BREACH)
    return errors


def _latency_summary(vals: list[float]) -> dict:
    """Compute p50/p95 latency summary in milliseconds for a sample list."""
    if not vals:
        return {}
    lat = sorted(vals)
    return {
        "p50": round(statistics.median(lat), 1),
        "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1),
    }


def probe_tenant_vault_isolation(
    core,
    *,
    k: int = 10,
    domain_key: str = "shared_domain",
    research: bool = False,
) -> dict:
    """Verify owner/sibling vault isolation under core.bind_active_vault with shared domain_key."""
    env_keys = ("NOUGEN_EMBED_AT_CAPTURE", "NOUGEN_DISTILL_LANES", "NOUGEN_QUERY_EMBED", "NOUGEN_RERANK")
    prev_env = {key: os.environ.get(key) for key in env_keys}
    for key in env_keys:
        os.environ[key] = "0"

    sentinels = (
        ("owner", getattr(core, "OWNER_TENANT_ID", "owner"), "Owner Vault Sentinel", "owner_sentinel_token_alpha"),
        ("tenant_a", "tenant-a", "Tenant Alpha Vault Sentinel", "tenant_alpha_sentinel_bravo"),
        ("tenant_b", "tenant-b", "Tenant Beta Vault Sentinel", "tenant_beta_sentinel_charlie"),
    )

    probes_run = 0
    positive_hits = 0
    cross_leaks = 0
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            vault_dirs = {label: root / label for label, _, _, _ in sentinels}
            for vdir in vault_dirs.values():
                vdir.mkdir(parents=True, exist_ok=True)
            try:
                for label, tenant_id, title, marker in sentinels:
                    tok = core.bind_active_vault(vault_dirs[label], tenant_id)
                    try:
                        res = core.capture(
                            "KNOWLEDGE",
                            title,
                            f"Sentinel shard content for {marker} under {label}.",
                            domain_key=domain_key,
                        )
                        if not getattr(res, "captured", False):
                            raise RuntimeError(f"Failed capturing isolation sentinel for {label}: {res}")
                    finally:
                        core.reset_active_vault(tok)

                core.close_readonly_pool()

                for active_label, active_tenant, _, own_marker in sentinels:
                    tok = core.bind_active_vault(vault_dirs[active_label], active_tenant)
                    try:
                        for target_label, _, target_title, target_marker in sentinels:
                            probes_run += 1
                            rows = core.retrieve(
                                target_marker,
                                limit=k,
                                domain_key=domain_key,
                                include_research=research,
                            )
                            if target_label == active_label:
                                if any(
                                    isinstance(r, dict)
                                    and (own_marker in str(r.get("content") or "") or r.get("title") == target_title)
                                    for r in rows[:k]
                                ):
                                    positive_hits += 1
                            else:
                                for r in rows[:k]:
                                    if isinstance(r, dict) and (
                                        target_marker in str(r.get("content") or "")
                                        or r.get("title") == target_title
                                    ):
                                        cross_leaks += 1
                    finally:
                        core.reset_active_vault(tok)
            finally:
                core.close_readonly_pool()
                init_dbs = getattr(core, "_INITIALIZED_DBS", None)
                if isinstance(init_dbs, set):
                    prefixes = tuple(str(p) for p in vault_dirs.values())
                    stale = [
                        entry for entry in init_dbs
                        if isinstance(entry, tuple) and entry and str(entry[0]).startswith(prefixes)
                    ]
                    for entry in stale:
                        init_dbs.discard(entry)
    finally:
        for key, prev in prev_env.items():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev

    return {
        "probes_run": probes_run,
        "positive_expected": len(sentinels),
        "positive_hits": positive_hits,
        "cross_leaks": cross_leaks,
        "domain_key": domain_key,
    }


def evaluate_gate(
    report: dict,
    *,
    min_recall5: float = 0.85,
    min_mrr: float = 0.70,
    max_fp_rate: float = 0.20,
    max_p95_ms: float = 2000.0,
    max_domain_leaks: int = 0,
    require_isolation_coverage: bool = True,
) -> dict:
    """Gate-Then-Score evaluation (arXiv:2611.24039): governance gates first, quality floors second."""
    neg_total_raw = int(report.get("negatives_total", 0) or 0)
    neg_nonempty = int(report.get("negatives_nonempty", 0) or 0)
    fp_rate = (neg_nonempty / neg_total_raw) if neg_total_raw > 0 else 0.0

    iso_probes = int(report.get("isolation_probes_run") or 0)
    vault_leaks = int(report.get("vault_leaks") or 0)
    domain_leaks = int(report.get("domain_leaks") or 0)
    total_leaks = (
        int(report["tenant_leaks"])
        if report.get("tenant_leaks") is not None
        else (vault_leaks + domain_leaks)
    )
    vault_iso = report.get("vault_isolation") or {}
    pos_expected = int(vault_iso.get("positive_expected") or 0)
    pos_hits = int(vault_iso.get("positive_hits") or 0)

    coverage_ok = (not require_isolation_coverage) or (iso_probes > 0)
    own_recall_ok = pos_hits >= pos_expected
    iso_passed = coverage_ok and own_recall_ok and (total_leaks <= max_domain_leaks)

    p95_ms = float((report.get("latency_ms") or {}).get("p95") or 0.0)

    overall = report.get("overall") or {}
    recall5 = float(overall.get("recall@5", 0.0) or 0.0)
    mrr = float(overall.get("mrr", 0.0) or 0.0)

    gates = {
        "tenant_isolation": {
            "passed": iso_passed,
            "observed": total_leaks,
            "threshold": max_domain_leaks,
            "probes_run": iso_probes,
            "vault_leaks": vault_leaks,
            "domain_leaks": domain_leaks,
            "own_recall_ok": own_recall_ok,
        },
        "false_positive_rate": {
            "passed": fp_rate <= max_fp_rate,
            "observed": round(fp_rate, 4),
            "threshold": max_fp_rate,
        },
        "latency_p95_ms": {
            "passed": p95_ms <= max_p95_ms,
            "observed": round(p95_ms, 2),
            "threshold": max_p95_ms,
        },
        "recall@5": {
            "passed": recall5 >= min_recall5,
            "observed": round(recall5, 4),
            "threshold": min_recall5,
        },
        "mrr": {
            "passed": mrr >= min_mrr,
            "observed": round(mrr, 4),
            "threshold": min_mrr,
        },
    }

    governance_keys = ("tenant_isolation", "false_positive_rate", "latency_p95_ms")
    quality_keys = ("recall@5", "mrr")
    governance_passed = all(gates[g]["passed"] for g in governance_keys)
    quality_passed = all(gates[g]["passed"] for g in quality_keys)

    failures: list[str] = []
    for name in governance_keys + quality_keys:
        g = gates[name]
        if not g["passed"]:
            if name == "tenant_isolation":
                if not coverage_ok:
                    failures.append("tenant_isolation: no isolation probes executed (isolation_probes_run=0)")
                if not own_recall_ok:
                    failures.append(
                        f"tenant_isolation: own-vault sentinel recall failed ({pos_hits}/{pos_expected})"
                    )
                if total_leaks > max_domain_leaks:
                    failures.append(
                        f"tenant_isolation: observed {total_leaks} leaks (vault={vault_leaks}, domain={domain_leaks}) violates threshold {max_domain_leaks}"
                    )
            else:
                failures.append(f"{name}: observed {g['observed']} violates threshold {g['threshold']}")

    return {
        "passed": governance_passed and quality_passed,
        "governance_passed": governance_passed,
        "quality_passed": quality_passed,
        "gates": gates,
        "taxonomy_counts": dict(report.get("taxonomy_counts") or {}),
        "failures": failures,
    }


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


def run(
    golden_path: Path,
    k: int,
    no_embed: bool,
    fp_target: float,
    domain: str,
    *,
    out_dir: Path | None = None,
    write_report: bool = True,
    max_latency_ms: float | None = None,
    verify_vault_isolation: bool = True,
) -> dict:
    if no_embed:
        os.environ["NOUGEN_QUERY_EMBED"] = "0"
    core = _core()
    orig_reorder = core.lost_in_the_middle_reorder
    core.lost_in_the_middle_reorder = list  # measure rank order, not the reader-facing interleave
    try:
        golden = json.loads(Path(golden_path).read_text(encoding="utf-8"))
        research = bool(golden.get("include_research", False))

        def search(q, active_domain=domain):
            return core.retrieve(q, limit=k, domain_key=active_domain, include_research=research)
        search("warm up the grid")

        per_query, by_tier = [], {}
        pos_latencies: list[float] = []
        neg_latencies: list[float] = []
        latencies: list[float] = []
        pos = {f: [] for f in SCORE_FIELDS}
        domain_leaks = 0
        domain_probes_run = 0
        taxonomy_counts: dict[str, int] = {}

        for it in golden["queries"]:
            q_domain = it.get("domain_key", domain)
            t0 = time.perf_counter()
            res = search(it["query"], active_domain=q_domain)
            ms = (time.perf_counter() - t0) * 1000
            latencies.append(ms)
            pos_latencies.append(ms)
            ranked = [f"{r.get('id')}@{r.get('_db_index')}" for r in res]
            s = score_query(ranked, it["relevant"], k)
            by_tier.setdefault(it.get("tier", "manual"), []).append(s)
            hit = res[s["rank"] - 1] if s["rank"] else None
            for f in SCORE_FIELDS:
                pos[f].append(hit.get(f) if hit else None)
            if q_domain and q_domain != "*":
                domain_probes_run += 1
                domain_leaks += sum(
                    1 for r in res[:k]
                    if isinstance(r, dict) and r.get("domain_key") is not None and r.get("domain_key") != q_domain
                )
            errors = classify_query_failure(
                ranked,
                it["relevant"],
                res,
                expected_domain=q_domain,
                k=k,
                latency_ms=ms,
                max_latency_ms=max_latency_ms,
            )
            for err in errors:
                taxonomy_counts[err] = taxonomy_counts.get(err, 0) + 1
            per_query.append({
                "tier": it.get("tier"),
                "query": it["query"],
                "target": it.get("target"),
                "domain_key": q_domain,
                "rank": s["rank"],
                "ms": round(ms, 1),
                "top": ranked[:3],
                "errors": errors,
            })

        neg = {f: [] for f in SCORE_FIELDS}
        neg_queries = golden.get("negatives", [])
        for q in neg_queries:
            t0 = time.perf_counter()
            res = search(q)
            ms = (time.perf_counter() - t0) * 1000
            latencies.append(ms)
            neg_latencies.append(ms)
            if res:
                taxonomy_counts[ERROR_FALSE_POSITIVE] = taxonomy_counts.get(ERROR_FALSE_POSITIVE, 0) + 1
            if max_latency_ms is not None and ms > max_latency_ms:
                taxonomy_counts[ERROR_LATENCY_BREACH] = taxonomy_counts.get(ERROR_LATENCY_BREACH, 0) + 1
            for f in SCORE_FIELDS:
                neg[f].append(res[0].get(f) if res else None)

        vault_iso = (
            probe_tenant_vault_isolation(core, k=k, research=research)
            if verify_vault_isolation
            else {"probes_run": 0, "positive_expected": 0, "positive_hits": 0, "cross_leaks": 0}
        )
        vault_leaks = int(vault_iso.get("cross_leaks", 0) or 0)
        if vault_leaks > 0:
            taxonomy_counts[ERROR_TENANT_LEAK] = taxonomy_counts.get(ERROR_TENANT_LEAK, 0) + vault_leaks

        now = datetime.now(timezone.utc)
        report = {
            "created_utc": now.isoformat(timespec="seconds"), "created_eastern": _eastern(now),
            "config": {"k": k, "embed": not no_embed and os.environ.get("NOUGEN_QUERY_EMBED", "1") != "0",
                       "include_research": research,
                       "distill_lanes": os.environ.get("NOUGEN_DISTILL_LANES", "1") != "0",
                       "rerank": bool(getattr(core, "RERANK_ENABLED", False)), "domain": domain,
                       "fp_target": fp_target, "golden": str(golden_path), "golden_created": golden.get("created_utc")},
            "summary": {t: aggregate(rows) for t, rows in sorted(by_tier.items())},
            "overall": aggregate([s for rows in by_tier.values() for s in rows]),
            "latency_ms": _latency_summary(latencies),
            "positive_latency_ms": _latency_summary(pos_latencies),
            "negative_latency_ms": _latency_summary(neg_latencies),
            "negatives_total": len(neg_queries),
            "negatives_nonempty": sum(1 for s in neg[SCORE_FIELDS[0]] if s is not None),
            "domain_leaks": domain_leaks,
            "vault_leaks": vault_leaks,
            "tenant_leaks": vault_leaks + domain_leaks,
            "isolation_probes_run": int(vault_iso.get("probes_run", 0) or 0) + domain_probes_run,
            "vault_isolation": vault_iso,
            "taxonomy_counts": taxonomy_counts,
            "sweep": {f: sweep(pos[f], neg[f], fp_target) for f in SCORE_FIELDS},
            "per_query": per_query,
        }
        target_dir = Path(out_dir) if out_dir is not None else ANALYSIS
        if write_report:
            target_dir.mkdir(parents=True, exist_ok=True)
            previous = sorted(target_dir.glob("report_*.json"))
            out = target_dir / f"report_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
            out.write_text(json.dumps(report, indent=1), encoding="utf-8")
            _print(report, json.loads(previous[-1].read_text(encoding="utf-8")) if previous else None, out)
        return report
    finally:
        core.lost_in_the_middle_reorder = orig_reorder


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
          f"| negatives returning results: {rep['negatives_nonempty']}  "
          f"| isolation probes: {rep.get('isolation_probes_run', 0)} leaks: {rep.get('tenant_leaks', 0)}")
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
    g = sub.add_parser("gate")
    g.add_argument("--golden", type=Path, default=GOLDEN)
    g.add_argument("--k", type=int, default=10)
    g.add_argument("--no-embed", action="store_true")
    g.add_argument("--fp-target", type=float, default=0.2)
    g.add_argument("--domain", default="*")
    g.add_argument("--min-recall5", type=float, default=0.85)
    g.add_argument("--min-mrr", type=float, default=0.70)
    g.add_argument("--max-fp-rate", type=float, default=0.20)
    g.add_argument("--max-p95-ms", type=float, default=2000.0)
    g.add_argument("--max-domain-leaks", type=int, default=0)
    g.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        build(a.n, a.neg, a.seed, a.include_research)
    elif a.cmd == "gate":
        rep = run(
            a.golden,
            a.k,
            a.no_embed,
            a.fp_target,
            a.domain,
            write_report=not a.no_write,
            max_latency_ms=a.max_p95_ms,
        )
        verdict = evaluate_gate(
            rep,
            min_recall5=a.min_recall5,
            min_mrr=a.min_mrr,
            max_fp_rate=a.max_fp_rate,
            max_p95_ms=a.max_p95_ms,
            max_domain_leaks=a.max_domain_leaks,
        )
        print(json.dumps(verdict, indent=2))
        if not verdict["passed"]:
            raise SystemExit(1)
    else:
        run(a.golden, a.k, a.no_embed, a.fp_target, a.domain)


if __name__ == "__main__":
    main()
