"""Ingest exactly the arXiv shard files that are NOT yet rows in the shard DBs.

The bulk drain (arxiv_backlog_ingest.py) walks every file and lets capture()'s
dedupe absorb the ones already done. That is correct but re-reads and re-hashes
the whole backlog, and long-running background processes in this environment
get reaped mid-flight (observed three times, exit 1, no traceback).

So: diff the vault against the DBs first, then ingest only the true remainder,
with a wall-clock budget so each invocation finishes well inside a foreground
timeout. Re-run until it reports remaining=0.

Env:
  NOUGEN_VAULT_DIR                vault root
  NOUGEN_ARXIV_FINISH_BUDGET_S    stop cleanly after N seconds (default 420)
  NOUGEN_ARXIV_INGEST_GLOBS       which families to reconcile
  NOUGEN_ARXIV_INGEST_TAGS        tags applied to each shard
"""
import fnmatch
import glob as _glob
import json
import os
import sqlite3
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
# Both the package under src/ and the sibling lane modules in tools/, so this
# runs correctly from any working directory, not just from tools/.
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))
sys.path.insert(0, _HERE)

import arxiv_lane_config as cfg  # noqa: E402  (path set above)
from arxiv_backlog_ingest import (  # noqa: E402
    EVENT_TYPE, GLOBS, TAGS, _resolve_vault_root, local_density)

BUDGET_S, BUDGET_SRC = cfg.resolve(
    "NOUGEN_ARXIV_FINISH_BUDGET_S", "arxiv_finish_budget_s", "420", float)
PROGRESS_EVERY, PROGRESS_SRC = cfg.resolve(
    "NOUGEN_ARXIV_FINISH_PROGRESS", "arxiv_finish_progress", "250", int)


def titles_in_dbs(vault):
    """Every shard title already stored, across all nougen_shards_*.db."""
    have = set()
    for db in sorted(_glob.glob(os.path.join(vault, cfg.SHARD_DB_GLOB))):
        try:
            con = sqlite3.connect("file:{}?mode=ro".format(db.replace("\\", "/")),
                                  uri=True)
            # Table name comes from lane config; identifiers cannot be bound as
            # SQL parameters, so it is interpolated — it is operator config,
            # never user input.
            for (t,) in con.execute("select title from {}".format(cfg.SHARD_TABLE)):
                if t:
                    have.add(t)
            con.close()
        except Exception as e:
            print("  WARN {}: {}".format(os.path.basename(db), e), flush=True)
    return have


def main():
    if "--print-config" in sys.argv:
        print(cfg.describe([
            ("finish_budget_s", BUDGET_S, BUDGET_SRC),
            ("finish_progress", PROGRESS_EVERY, PROGRESS_SRC),
            ("reconcile_globs", ";".join(GLOBS), "from arxiv_backlog_ingest"),
        ]))
        return 0
    vault = _resolve_vault_root()
    have = titles_in_dbs(vault)
    print("titles already in DBs: {}".format(len(have)), flush=True)

    todo = []
    with os.scandir(vault) as it:
        for e in it:
            if not e.is_file():
                continue
            if any(fnmatch.fnmatch(e.name, g) for g in GLOBS) and e.name not in have:
                todo.append((e.name, e.path))
    todo.sort()
    print("files missing from DBs: {}".format(len(todo)), flush=True)
    if not todo:
        print(json.dumps({"remaining": 0, "captured": 0, "done": True}))
        return 0

    from nougen_shards import core as shards

    t0 = time.time()
    captured = skipped = failed = 0
    processed = 0
    for name, path in todo:
        if time.time() - t0 > BUDGET_S:
            break
        processed += 1
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            if shards.capture(EVENT_TYPE, name, content, list(TAGS),
                              density_score=local_density(content)):
                captured += 1
            else:
                skipped += 1
        except Exception as ex:
            failed += 1
            if failed <= 3:
                print("  FAIL {}: {}: {}".format(name, type(ex).__name__, ex), flush=True)
        if PROGRESS_EVERY and processed % PROGRESS_EVERY == 0:
            print("  {}/{} captured={} skipped={} failed={} {:.1f}/s".format(
                processed, len(todo), captured, skipped, failed,
                processed / max(0.001, time.time() - t0)), flush=True)

    remaining = len(todo) - processed
    print(json.dumps({
        "processed": processed, "captured": captured,
        "skipped_dedupe_or_junk": skipped, "failed": failed,
        "remaining": remaining, "done": remaining == 0,
        "elapsed_s": round(time.time() - t0, 1),
    }), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
