#!/usr/bin/env python3
"""Distil shards into the NouGen sidecar on the LOCAL e2b lane (text never leaves the box).

Resumable and idempotent: every shard commits on its own, and an unchanged shard
(same content hash) is skipped, so a killed run just resumes. Five consecutive
failures stop the run with the cause, the no-progress breaker lesson from
openhuman: a dead Ollama is a stop, not 400 errors.

Usage:
  python tools/distill_run.py --from-eval          # golden targets + the shards that outrank them
  python tools/distill_run.py --sample 500 --seed 7
  python tools/distill_run.py --scenes --persona   # L2 + L3 over what is distilled
  python tools/distill_run.py --stats
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from nougen_shards import core, distill  # noqa: E402
import coach  # noqa: E402

MAX_CONSECUTIVE_FAILS = 5


def llm(prompt: str, schema):
    # E-series floor: >= 1400 tokens, 2048 for JSON (Rule 0.5.1). Reasoning is off in coach.local.
    return coach.local(prompt, schema=schema, max_tokens=2048 if schema else 1400)


def keys_from_eval() -> list[str]:
    """Golden targets plus every shard that outranked or crowded them in the latest
    report for this golden set: hard negatives, so the atoms lane competes where it matters."""
    gpath = ROOT / "analysis" / "recall_eval" / "golden.json"
    golden = json.loads(gpath.read_text(encoding="utf-8"))
    reports = sorted(glob.glob(str(ROOT / "analysis" / "recall_eval" / "report_*.json")))
    rep = next((json.loads(Path(p).read_text(encoding="utf-8")) for p in reversed(reports)
                if json.loads(Path(p).read_text(encoding="utf-8"))["config"].get("golden_created") == golden["created_utc"]), None)
    if rep is None:
        raise SystemExit("no report for the current golden set: run tools/recall_eval.py run first")
    keys = []
    for q in golden["queries"]:
        keys += q.get("relevant", [])[:1]
    for r in rep["per_query"]:
        keys += r.get("top", [])
    return list(dict.fromkeys(keys))


def keys_sample(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    bulk = tuple(core.bulk_ingest_event_types() or ())
    bulk_sql = f"AND UPPER(COALESCE(event_type,'')) NOT IN ({','.join('?' * len(bulk))})" if bulk else ""
    dbs = [i for i in range(1, core.MAX_DB_COUNT + 1) if core.get_db_path(i).exists()]
    keys: list[str] = []
    tries = 0
    while len(keys) < n and tries < n * 50:  # bounded: a small eligible pool must not spin forever
        tries += 1
        db = rng.choice(dbs)
        conn = core.get_connection(db)
        try:
            top = conn.execute("SELECT max(id) FROM shards").fetchone()[0] or 0
            row = conn.execute(f"SELECT id FROM shards WHERE id >= ? AND COALESCE(enc,0)=0 {bulk_sql} ORDER BY id LIMIT 1",
                               (rng.randint(1, top), *bulk)).fetchone()
        finally:
            conn.close()
        if row and distill.shard_key(db, row[0]) not in keys:
            keys.append(distill.shard_key(db, row[0]))
    return keys


def run(keys: list[str], limit: int | None) -> None:
    conn = distill.connect()
    keys = keys[:limit] if limit else keys
    done = skip = fail = streak = 0
    t0 = time.time()
    for n, key in enumerate(keys, 1):
        try:
            status = distill.distill_shard(conn, key, llm)
            done += status == "done"
            skip += status in ("skip", "empty")
            streak = 0
        except Exception as ex:  # one bad shard is recorded, a dead lane stops the run
            fail += 1
            streak += 1
            db, sid = key.split("@")[1], key.split("@")[0]
            with conn:
                conn.execute("INSERT OR REPLACE INTO distilled VALUES (?,?,?,?,?,?,?,?)",
                             (key, int(db), int(sid), "", "e2b", 0, f"error: {type(ex).__name__}: {str(ex)[:120]}",
                              distill._now()))  # pylint: disable=protected-access
            if streak >= MAX_CONSECUTIVE_FAILS:
                print(f"STOP after {streak} consecutive failures; last: {type(ex).__name__}: {str(ex)[:160]}", flush=True)
                break
        if n % 10 == 0 or n == len(keys):
            rate = (time.time() - t0) / n
            print(f"{n}/{len(keys)} done={done} skip={skip} fail={fail} {rate:.1f}s/shard "
                  f"eta {rate * (len(keys) - n) / 60:.1f} min", flush=True)
    print(json.dumps(distill.stats(conn)), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-eval", action="store_true")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max", type=int)
    ap.add_argument("--scenes", action="store_true")
    ap.add_argument("--persona", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--force", action="store_true", help="skip the coach load gate (logged)")
    a = ap.parse_args(argv)
    if a.stats:
        print(json.dumps(distill.stats(), indent=1))
        return
    c = coach.check()
    if not c["ok"] and not a.force:
        raise SystemExit("coach refused: " + "; ".join(c["reasons"]))
    if a.from_eval or a.sample:
        run(keys_from_eval() if a.from_eval else keys_sample(a.sample, a.seed), a.max)
    if a.scenes:
        print("scenes written:", distill.build_scenes(distill.connect(), llm), flush=True)
    if a.persona:
        text = distill.build_persona(distill.connect(), llm)
        print("persona:", (text or "none (no scenes yet)")[:400], flush=True)


if __name__ == "__main__":
    main()
