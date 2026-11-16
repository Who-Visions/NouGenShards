"""FTS5 benchmark for the NouGenShards Native Memory Engine (P1).

Measures what the gap report says was missing: per-lane timings (raw FTS
MATCH vs the keyword lane vs the vector lane vs hybrid), index-size
tracking, a trigram-vs-plain tokenizer comparison on one fixed corpus, and
an EXPLAIN QUERY PLAN audit of the live queries.

The corpus is fixed: tools/fts_seed_corpus.json (60 shards, 6 topics x 10,
seed 20261116). Every variant is built from the same JSON, so deltas are
real. Scratch vaults only, under --workdir (default: a fresh /tmp dir);
production vaults are never touched.

Usage (from the repo root):
    python3 tools/fts_bench.py [--out report.json]
        [--tokenizers trigram,unicode61] [--weights 5.0,1.0]
        [--repeats 3] [--embed] [--workdir DIR] [--min-recall10 0.5]

    python3 tools/fts_bench.py --query-only --vault-dir DIR [--weights ...]
        Re-run the query lanes against an existing vault (weights are
        query-time, so weight experiments need no rebuild).

    python3 tools/fts_bench.py --explain-only --vault-dir DIR
    python3 tools/fts_bench.py --sizes-only --vault-dir DIR

Exit codes: 0 on success; 1 when the corpus is empty (n==0 assertion), when
a measured lane ran zero queries, or when --min-recall10 is missed.

Env knobs (Rule 0.2, env first, logged fallback):
    NOUGEN_FTS_BENCH_REPEATS   timed repeats per query (default 3)
    NOUGEN_FTS_TOKENIZER       tokenizer for a build (default trigram)
    NOUGEN_FTS_BM25_TITLE_WEIGHT / NOUGEN_FTS_BM25_BODY_WEIGHT
                               BM25 weights (defaults 5.0 / 1.0)

Linux notes: WAL needs POSIX shm/locking on the vault dir, so scratch
vaults live on a local filesystem, never a network mount; /tmp is fine
because the vaults are disposable. The sandbox proxy variables are stripped
before spawning workers (bracketed IPv6 no_proxy breaks httpx at gradio
import time). No Ollama is needed unless --embed is passed.
"""
import hashlib
import json
import math
import os
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

CORPUS_PATH = REPO_ROOT / "tools" / "fts_seed_corpus.json"
PROXY_VARS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
              "ALL_PROXY", "all_proxy", "no_proxy", "NO_PROXY")


def _pct(vals, q):
    """Nearest-rank percentile, same method as tools/recall_bench.py."""
    vals = sorted(vals)
    idx = min(len(vals) - 1, max(0, round(q * (len(vals) - 1))))
    return vals[idx]


def _recall_metrics(ranked_titles, targets):
    """Recall@k / MRR / nDCG@10 for one tier.

    Args:
        ranked_titles: per-query list of ranked titles (top 10).
        targets: per-query expected title (same order).

    Returns:
        Dict with n, recall@1/3/5/10, mrr, ndcg@10.
    """
    n = len(targets)
    if n == 0:
        return {"n": 0, "recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0,
                "recall@10": 0.0, "mrr": 0.0, "ndcg@10": 0.0}
    hits = {1: 0, 3: 0, 5: 0, 10: 0}
    rr_sum = 0.0
    ndcg_sum = 0.0
    for titles, target in zip(ranked_titles, targets):
        rank = titles.index(target) + 1 if target in titles else None
        if rank is not None:
            for k in hits:
                if rank <= k:
                    hits[k] += 1
            rr_sum += 1.0 / rank
            ndcg_sum += 1.0 / math.log2(rank + 1)
    return {"n": n,
            "recall@1": round(hits[1] / n, 4), "recall@3": round(hits[3] / n, 4),
            "recall@5": round(hits[5] / n, 4), "recall@10": round(hits[10] / n, 4),
            "mrr": round(rr_sum / n, 4), "ndcg@10": round(ndcg_sum / n, 4)}


def load_corpus():
    """Load and verify the fixed seed corpus."""
    with open(CORPUS_PATH, encoding="utf-8") as fh:
        corpus = json.load(fh)
    shards = corpus["shards"]
    payload = json.dumps(shards, sort_keys=True).encode()
    actual_sha = hashlib.sha256(payload).hexdigest()
    assert actual_sha == corpus["meta"]["sha256"], (
        f"corpus sha mismatch: {actual_sha} != {corpus['meta']['sha256']} "
        "(the seed corpus must not drift)")
    assert len({s["title"] for s in shards}) == len(shards), "titles not unique"
    return corpus


def _worker_env(vault_dir, tokenizer=None, weights=None, embed=False):
    """Env for a bench worker subprocess (proxy vars stripped)."""
    env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["NOUGEN_VAULT_DIR"] = str(vault_dir)
    env["NOUGEN_EMBED_AT_CAPTURE"] = "1" if embed else "0"
    if tokenizer:
        env["NOUGEN_FTS_TOKENIZER"] = tokenizer
    if weights:
        env["NOUGEN_FTS_BM25_TITLE_WEIGHT"] = str(weights[0])
        env["NOUGEN_FTS_BM25_BODY_WEIGHT"] = str(weights[1])
    return env


def _run_worker(args, env):
    """Run this file as a worker subprocess; return its parsed JSON stdout."""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *args],
        env=env, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(
            f"worker {args} failed (rc={proc.returncode}):\n{proc.stderr[-2000:]}")
    # Workers print exactly one JSON document on stdout; anything before the
    # first "{" would be a stray print, so parse from the first brace on.
    return json.loads(proc.stdout[proc.stdout.index("{"):])


# ---------------------------------------------------------------- workers

def _worker_build(vault_dir, embed):
    """Build a scratch vault from the fixed corpus; print sizes JSON."""
    from nougen_shards import core  # noqa: PLC0415 (env set by parent)
    corpus = load_corpus()
    vault = Path(vault_dir)
    vault.mkdir(parents=True, exist_ok=True)
    for shard in corpus["shards"]:
        ok = core.capture(
            shard["event_type"], shard["title"], shard["content"],
            domain_key=shard["domain_key"])
        if not ok:
            raise RuntimeError(f"capture failed for {shard['title']!r}")
    print(json.dumps({"built": len(corpus["shards"]),
                      "sizes": measure_sizes(vault)}))
    return 0


def measure_sizes(vault_dir):
    """Per-DB file bytes + per-table bytes (dbstat, with row-count fallback).

    Args:
        vault_dir: vault directory to measure.

    Returns:
        Dict with per_db file bytes, fts_tables bytes, total_bytes,
        bytes_per_shard, and the dbstat availability flag.
    """
    vault = Path(vault_dir)
    per_db = {}
    total = 0
    fts_tables = {}
    shards_table_bytes = 0
    dbstat_ok = True
    for db_file in sorted(vault.glob("nougen_shards_*.db")):
        size = db_file.stat().st_size
        per_db[db_file.name] = size
        total += size
        try:
            conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
            try:
                rows = conn.execute(
                    "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name"
                ).fetchall()
                for name, nbytes in rows:
                    # Keep the shards table OUT of the FTS figure: it holds
                    # the rows (and embedding BLOBs), not the index. Mixing
                    # them once overstated FTS size by the embedding bytes.
                    if name == "shards":
                        shards_table_bytes += int(nbytes or 0)
                    elif name.startswith("shards_fts"):
                        fts_tables[f"{db_file.name}:{name}"] = int(nbytes or 0)
            finally:
                conn.close()
        except sqlite3.OperationalError:
            dbstat_ok = False
    shards_total = 0
    for db_file in sorted(vault.glob("nougen_shards_*.db")):
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            shards_total += conn.execute(
                "SELECT count(*) FROM shards").fetchone()[0]
        finally:
            conn.close()
    return {"per_db": per_db, "fts_tables": fts_tables,
            "shards_table_bytes": shards_table_bytes,
            "dbstat_available": dbstat_ok, "total_bytes": total,
            "shards": shards_total,
            "bytes_per_shard": round(total / shards_total, 1) if shards_total else 0}


def _worker_sizes(vault_dir):
    print(json.dumps(measure_sizes(Path(vault_dir))))
    return 0


def _fts_direct_query(db_file, match_expr, title_w, body_w, limit):
    """One raw FTS MATCH query against one DB file; returns ranked titles."""
    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"SELECT s.title, bm25(shards_fts, {title_w:.6g}, {body_w:.6g})"
            " FROM shards s JOIN shards_fts ON s.id = shards_fts.rowid"
            " WHERE s.domain_key = 'global' AND shards_fts MATCH ?"
            " ORDER BY 2 ASC, s.id ASC LIMIT ?",
            (match_expr, limit)).fetchall()
        return [(r[0], float(r[1])) for r in rows]
    finally:
        conn.close()


def _worker_query(vault_dir, repeats, weights, embed):
    """Time the lanes over the corpus query set; print a lane report JSON."""
    from nougen_shards import core  # noqa: PLC0415 (env set by parent)
    corpus = load_corpus()
    queries = [q for q in corpus["queries"] if q["tier"] != "negative"]
    negatives = [q for q in corpus["queries"] if q["tier"] == "negative"]
    db_files = sorted(Path(vault_dir).glob("nougen_shards_*.db"))
    title_w, body_w = weights

    lanes = {"fts_direct": {"lat_ms": [], "ranked": []},
             "keyword": {"lat_ms": [], "ranked": []}}
    if embed:
        lanes["vector"] = {"lat_ms": [], "ranked": [], "embed_ms": []}
        lanes["hybrid"] = {"lat_ms": [], "ranked": []}
    neg_nonempty = {name: 0 for name in lanes}

    # Warmup (untimed): pays one-time costs (pool, cache load).
    core._keyword_retrieve("bench warmup", limit=1, domain_key="global")

    for _ in range(repeats):
        for q in queries:
            and_expr = core._build_fts_match_query(q["query"])
            or_expr = core._build_fts_match_query(q["query"], joiner=" OR ")
            t0 = time.perf_counter()
            merged = {}
            for expr in [and_expr] + ([or_expr] if or_expr != and_expr else []):
                if expr is None:
                    continue
                for db_file in db_files:
                    for title, score in _fts_direct_query(
                            db_file, expr, title_w, body_w, 10):
                        if title not in merged or score < merged[title]:
                            merged[title] = score
                if merged:
                    break
            ranked = [t for t, _ in sorted(merged.items(), key=lambda kv: kv[1])][:10]
            lanes["fts_direct"]["lat_ms"].append((time.perf_counter() - t0) * 1000)
            lanes["fts_direct"]["ranked"].append(ranked)

            t0 = time.perf_counter()
            kw = core._keyword_retrieve(q["query"], limit=10, domain_key="global")
            lanes["keyword"]["lat_ms"].append((time.perf_counter() - t0) * 1000)
            lanes["keyword"]["ranked"].append([r["title"] for r in kw])

            if embed:
                t0 = time.perf_counter()
                emb = core._embed_query(q["query"])
                embed_ms = (time.perf_counter() - t0) * 1000
                if emb is None:
                    raise RuntimeError("query embedding failed (is Ollama up?)")
                t0 = time.perf_counter()
                vec = core._vector_retrieve(emb, limit=10, domain_key="global")
                lanes["vector"]["lat_ms"].append((time.perf_counter() - t0) * 1000)
                lanes["vector"]["embed_ms"].append(embed_ms)
                lanes["vector"]["ranked"].append([r["title"] for r in vec])

                t0 = time.perf_counter()
                hyb = core.retrieve(q["query"], limit=10, domain_key="global")
                lanes["hybrid"]["lat_ms"].append((time.perf_counter() - t0) * 1000)
                lanes["hybrid"]["ranked"].append([r["title"] for r in hyb])

    # Negatives: count non-empty returns per lane (reported, not asserted).
    for q in negatives:
        if core._keyword_retrieve(q["query"], limit=10, domain_key="global"):
            neg_nonempty["keyword"] += 1
        merged = {}
        expr = core._build_fts_match_query(q["query"])
        if expr:
            for db_file in db_files:
                for title, score in _fts_direct_query(
                        db_file, expr, title_w, body_w, 10):
                    merged[title] = score
        if merged:
            neg_nonempty["fts_direct"] += 1

    targets = [q["target_title"] for q in queries]
    tiers = {"title": [i for i, q in enumerate(queries) if q["tier"] == "title"],
             "body": [i for i, q in enumerate(queries) if q["tier"] == "body"]}
    report = {"n_queries": len(queries), "repeats": repeats,
              "weights": [title_w, body_w], "lanes": {},
              "negatives_nonempty": neg_nonempty}
    for name, lane in lanes.items():
        lat = lane["lat_ms"]
        # Ranked lists repeat per repeat; quality uses the first pass only.
        first_pass = lane["ranked"][:len(queries)]
        quality = {"all": _recall_metrics(first_pass, targets)}
        for tier, idxs in tiers.items():
            quality[tier] = _recall_metrics(
                [first_pass[i] for i in idxs], [targets[i] for i in idxs])
        entry = {"n": len(lat),
                 "p50_ms": round(_pct(lat, 0.5), 1),
                 "p95_ms": round(_pct(lat, 0.95), 1),
                 "mean_ms": round(statistics.mean(lat), 1),
                 "quality": quality}
        if "embed_ms" in lane:
            entry["embed_p50_ms"] = round(_pct(lane["embed_ms"], 0.5), 1)
        report["lanes"][name] = entry
    print(json.dumps(report))
    return 0


def _worker_explain(vault_dir):
    """EXPLAIN QUERY PLAN audit of the live queries; print JSON."""
    from nougen_shards import core  # noqa: PLC0415 (env set by parent)
    corpus = load_corpus()
    db_files = sorted(Path(vault_dir).glob("nougen_shards_*.db"))
    counts = {}
    for db_file in db_files:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            counts[db_file.name] = conn.execute(
                "SELECT count(*) FROM shards").fetchone()[0]
        finally:
            conn.close()
    rep_db = max(counts, key=lambda k: counts[k])
    conn = sqlite3.connect(f"file:{Path(vault_dir) / rep_db}?mode=ro", uri=True)
    try:
        indexes = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]
        title_q = corpus["queries"][0]["query"]
        body_q = [q["query"] for q in corpus["queries"] if q["tier"] == "body"][0]
        and_expr = core._build_fts_match_query(title_q)
        or_expr = core._build_fts_match_query(body_q, joiner=" OR ")
        plans = []
        for name, sql, params in [
            ("fts_and_match",
             "SELECT s.id FROM shards s JOIN shards_fts ON s.id = shards_fts.rowid"
             " WHERE s.domain_key = ? AND UPPER(s.event_type) NOT IN (?,?)"
             " AND shards_fts MATCH ? ORDER BY bm25(shards_fts, 5.0, 1.0) ASC,"
             " s.id ASC LIMIT ?", ("global", "IMPORT", "INGEST", and_expr, 10)),
            ("fts_or_match",
             "SELECT s.id FROM shards s JOIN shards_fts ON s.id = shards_fts.rowid"
             " WHERE s.domain_key = ? AND UPPER(s.event_type) NOT IN (?,?)"
             " AND shards_fts MATCH ? ORDER BY bm25(shards_fts, 5.0, 1.0) ASC,"
             " s.id ASC LIMIT ?", ("global", "IMPORT", "INGEST", or_expr, 10)),
            ("like_fallback",
             "SELECT id FROM shards WHERE domain_key = ?"
             " AND (title LIKE ? OR content LIKE ?)"
             " ORDER BY utility_score DESC, id ASC LIMIT ?",
             ("global", "%relay leg%", "%relay leg%", 10)),
            ("domain_utility",
             "SELECT id FROM shards WHERE domain_key = ?"
             " ORDER BY utility_score DESC, id ASC LIMIT ?",
             ("global", 10)),
            ("title_nocase",
             "SELECT id FROM shards WHERE title = ? COLLATE NOCASE",
             (title_q,)),
            ("file_hash_lookup",
             "SELECT id FROM shards WHERE file_hash = ?",
             ("0" * 64,)),
        ]:
            rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
            plans.append({"name": name, "plan": [r[3] for r in rows]})
        used = set()
        for plan in plans:
            for line in plan["plan"]:
                if "USING INDEX" in line or "USING COVERING INDEX" in line:
                    used.add(line.split("USING COVERING INDEX ")[-1].split("USING INDEX ")[-1].strip().split(" ")[0])
                if "VIRTUAL TABLE INDEX" in line:
                    used.add("shards_fts (virtual table index)")
        unused = [ix for ix in indexes if ix not in used]
        print(json.dumps({"db": rep_db, "db_rows": counts[rep_db],
                          "indexes": sorted(indexes),
                          "indexes_used": sorted(used),
                          "indexes_unused": sorted(unused),
                          "plans": plans}))
    finally:
        conn.close()
    return 0


# ---------------------------------------------------------------- top level

def _parse_weights(text):
    parts = text.split(",")
    if len(parts) != 2:
        raise ValueError("--weights takes 'title,body', e.g. 5.0,1.0")
    return (float(parts[0]), float(parts[1]))


def run(argv):
    """Orchestrate the benchmark across tokenizer variants."""
    import argparse
    parser = argparse.ArgumentParser(description="FTS5 benchmark (P1)")
    parser.add_argument("--out", default=None)
    parser.add_argument("--tokenizers", default="trigram")
    parser.add_argument("--weights", default="5.0,1.0")
    parser.add_argument("--repeats", type=int,
                        default=int(os.environ.get("NOUGEN_FTS_BENCH_REPEATS", "3")))
    parser.add_argument("--embed", action="store_true")
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--min-recall10", type=float, default=None)
    parser.add_argument("--query-only", default=None, metavar="VAULT_DIR")
    parser.add_argument("--explain-only", default=None, metavar="VAULT_DIR")
    parser.add_argument("--sizes-only", default=None, metavar="VAULT_DIR")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)
    weights = _parse_weights(args.weights)
    corpus = load_corpus()
    if corpus["shards"] == [] or corpus["queries"] == []:
        print("[fts_bench] FAIL corpus is empty", file=sys.stderr)
        return 1

    if args.query_only:
        env = _worker_env(args.query_only, weights=weights, embed=args.embed)
        report = _run_worker(["_query", args.query_only, str(args.repeats),
                              str(weights[0]), str(weights[1]),
                              "1" if args.embed else "0"], env)
        print(json.dumps(report, indent=2))
        return _check_min_recall(report, args.min_recall10)
    if args.explain_only:
        env = _worker_env(args.explain_only)
        print(json.dumps(_run_worker(["_explain", args.explain_only], env), indent=2))
        return 0
    if args.sizes_only:
        env = _worker_env(args.sizes_only)
        print(json.dumps(_run_worker(["_sizes", args.sizes_only], env), indent=2))
        return 0

    workdir = Path(args.workdir) if args.workdir else Path(
        tempfile.mkdtemp(prefix="p1-fts-bench-"))
    workdir.mkdir(parents=True, exist_ok=True)
    variants = {}
    for tokenizer in [t.strip() for t in args.tokenizers.split(",") if t.strip()]:
        vault_dir = workdir / f"vault-{tokenizer}"
        env = _worker_env(vault_dir, tokenizer=tokenizer, weights=weights,
                          embed=args.embed)
        built = _run_worker(["_build", str(vault_dir),
                             "1" if args.embed else "0"], env)
        query = _run_worker(["_query", str(vault_dir), str(args.repeats),
                             str(weights[0]), str(weights[1]),
                             "1" if args.embed else "0"], env)
        explain = _run_worker(["_explain", str(vault_dir)], env)
        variants[tokenizer] = {"vault_dir": str(vault_dir),
                               "sizes": built["sizes"],
                               "lanes": query["lanes"],
                               "n_queries": query["n_queries"],
                               "negatives_nonempty": query["negatives_nonempty"],
                               "explain": explain}
    report = {
        "meta": {
            "tool": "tools/fts_bench.py (P1)",
            "corpus": {"name": corpus["meta"]["name"],
                       "sha256": corpus["meta"]["sha256"],
                       "n_shards": len(corpus["shards"]),
                       "n_queries": len(corpus["queries"]),
                       "body_chars": corpus["meta"]["body_chars"]},
            "sqlite_version": sqlite3.sqlite_version,
            "platform": platform.system(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "weights": list(weights),
            "repeats": args.repeats,
            "embed": args.embed,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workdir": str(workdir),
        },
        "variants": variants,
        "deltas": _deltas(variants),
    }
    out_path = Path(args.out) if args.out else workdir / "fts_bench_report.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    _print_summary(report)
    print(f"[fts_bench] report: {out_path}")
    rc = 0
    for variant in variants.values():
        for lane in variant["lanes"].values():
            if lane["n"] == 0:
                print("[fts_bench] FAIL a lane measured zero queries", file=sys.stderr)
                rc = 1
    if args.min_recall10 is not None:
        for name, variant in variants.items():
            rec = variant["lanes"]["keyword"]["quality"]["all"]["recall@10"]
            if rec < args.min_recall10:
                print(f"[fts_bench] FAIL {name} keyword Recall@10 {rec} "
                      f"< {args.min_recall10}", file=sys.stderr)
                rc = 1
    return rc


def _check_min_recall(report, threshold):
    if threshold is None:
        return 0
    rec = report["lanes"]["keyword"]["quality"]["all"]["recall@10"]
    if rec < threshold:
        print(f"[fts_bench] FAIL keyword Recall@10 {rec} < {threshold}",
              file=sys.stderr)
        return 1
    return 0


def _deltas(variants):
    """Plain-vs-trigram deltas (latency, size, quality), if both ran."""
    if "trigram" not in variants or "unicode61" not in variants:
        return {}
    out = {}
    tri, plain = variants["trigram"], variants["unicode61"]
    for lane in ("fts_direct", "keyword"):
        if lane in tri["lanes"] and lane in plain["lanes"]:
            out[f"{lane}_p50_ms_delta"] = round(
                plain["lanes"][lane]["p50_ms"] - tri["lanes"][lane]["p50_ms"], 1)
            out[f"{lane}_recall10_delta"] = round(
                plain["lanes"][lane]["quality"]["all"]["recall@10"]
                - tri["lanes"][lane]["quality"]["all"]["recall@10"], 4)
    out["total_bytes_delta"] = (
        plain["sizes"]["total_bytes"] - tri["sizes"]["total_bytes"])
    out["fts_bytes_delta"] = (
        sum(plain["sizes"]["fts_tables"].values())
        - sum(tri["sizes"]["fts_tables"].values()))
    return out


def _print_summary(report):
    print("[fts_bench] corpus: "
          f"{report['meta']['corpus']['n_shards']} shards, "
          f"{report['meta']['corpus']['n_queries']} queries, "
          f"sha {report['meta']['corpus']['sha256'][:12]}")
    for name, variant in report["variants"].items():
        sizes = variant["sizes"]
        fts_bytes = sum(sizes["fts_tables"].values())
        print(f"[fts_bench] {name}: vault {sizes['total_bytes']} B "
              f"({sizes['bytes_per_shard']} B/shard), "
              f"shards table {sizes['shards_table_bytes']} B, "
              f"FTS tables {fts_bytes} B, dbstat={sizes['dbstat_available']}")
        for lane_name, lane in variant["lanes"].items():
            q = lane["quality"]["all"]
            print(f"[fts_bench]   {lane_name}: p50 {lane['p50_ms']} ms, "
                  f"p95 {lane['p95_ms']} ms, Recall@10 {q['recall@10']}, "
                  f"MRR {q['mrr']}")
        print(f"[fts_bench]   negatives non-empty: "
              f"{variant['negatives_nonempty']}")
        print(f"[fts_bench]   indexes unused: "
              f"{variant['explain']['indexes_unused']}")
    if report["deltas"]:
        print(f"[fts_bench] deltas (unicode61 - trigram): {report['deltas']}")


def main(argv):
    """Dispatch worker subcommands vs the top-level orchestrator."""
    if argv and argv[0] in ("_build", "_query", "_explain", "_sizes"):
        cmd = argv[0]
        if cmd == "_build":
            return _worker_build(argv[1], argv[2] == "1")
        if cmd == "_query":
            return _worker_query(argv[1], int(argv[2]), (float(argv[3]), float(argv[4])),
                                 argv[5] == "1")
        if cmd == "_explain":
            return _worker_explain(argv[1])
        if cmd == "_sizes":
            return _worker_sizes(argv[1])
    return run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
