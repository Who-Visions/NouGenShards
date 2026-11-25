#!/usr/bin/env python3
"""Run the NGS arm of the independent benchmark on all four docs.

Reads each doc's question from its existing fleet log (top level) and its
recall query from the log's recall.query when present. The Plato/Omar/
China logs predate the query_used field, so their recall queries are the
exact queries from the fleet runs that produced those logs (see the
RUNS table — same strings as the bench commands that wrote the logs).
Raw totals are NOT re-run; they come from the existing logs.
"""
import json, subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
# (fleet log, title-prefix, tag, recall query when the log lacks one)
RUNS = [
    ("plato-bench-v7.json", "Plato in Egypt (bench)", "plato-egypt",
     "Plato Egypt how long study Heliopolis Sechnuphis theory of Forms Ptahhotep Maat Akhenaten"),
    ("omar-bench-v4.json", "Omar search (bench)", "omar-search",
     "Sharbaugh Speech or Debate Clause Omar search concerns privilege Boasberg unsealed records 17 items"),
    ("china-bench-v4.json", "China Ma (bench)", "china-ma",
     "Ma Kailin China death sentence state secrets Gold Wall Press 35"),
    ("cgf-bench-v2.json", "CGF dark matter (bench)", "cgf-dark-matter",
     None),  # recall query is in the log
]

for log_name, prefix, tag, fallback_rq in RUNS:
    log = json.load(open(os.path.join(HERE, log_name)))
    doc = log["doc"]
    q = log["question"]
    rq = (log.get("recall") or {}).get("query") or fallback_rq
    out = os.path.join(HERE, os.path.splitext(doc)[0] + "-bench-ngs.json")
    print(f"=== {doc} (baseline {log_name}) ===", flush=True)
    print(f"  question: {q[:80]}...", flush=True)
    print(f"  recall query: {rq}", flush=True)
    cmd = [sys.executable, os.path.join(HERE, "shards-bench.py"),
           "--doc", doc, "--question", q, "--recall-query", rq,
           "--rounds", "2", "--recall-source", "ngs", "--skip-raw",
           "--title-prefix", prefix, "--tag", tag,
           "--ngs-k", "5", "--ngs-token-budget", "4000",
           "--out", out]
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    print(r.stdout, flush=True)
    if r.returncode != 0:
        print(r.stderr, flush=True)
        print(f"FAILED {doc}", flush=True)
        sys.exit(1)
print("ALL NGS RUNS DONE")
