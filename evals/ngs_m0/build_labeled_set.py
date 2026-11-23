"""NGS M0: build the labeled query set from a pinned vault snapshot.

Spec: docs/memory-engine/SPEC.md section 9 / M0. Deterministic and read-only.

Source of truth is a SNAPSHOT directory (default ~/.nougen/replica/shards, the
read-only replica, never the live vault) so labels and the corpus they refer to
cannot drift apart. Every nougen_shards_<n>.db is opened mode=ro (NOT
immutable=1: that skips the WAL and can report a healthy db as malformed).

Gold rule (only what can be derived without a human or a model):
  A shard titled "Autonomous Verified Relay: <leg id>" carries the leg's
  "Goal: ..." sentence. Query = that goal with leg ids and the word "Handoff"
  removed and cut at 160 chars. Gold = every shard in the snapshot with the same
  title (the same shard can be replicated across vault dbs).

KNOWN BIAS, stated in the output file: the query is a prefix-trimmed copy of the
gold body, so this set is LEXICALLY EASY and favours keyword search. It guards
against regressions; it cannot prove a +10 pp Recall@5 gain. The 200-400 pair
set the spec asks for needs human or independently-written queries (open item).

No-answer set: fixed fictional-name queries that cannot appear in the corpus
(verified here by an FTS-free substring check on titles).

Usage:
  python evals/ngs_m0/build_labeled_set.py [--snapshot DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
from pathlib import Path

LEG_ID = re.compile(r"\b20\d{6}T\d{6}Z(?:__[\w.-]+){0,2}\b")
GOAL = re.compile(r"Goal:\s*(.+)", re.S)
SEED = 4101  # fixed; change only with a new set version

FICTIONAL = [
    "zorblax", "quillfeather", "mandrake lattice", "vexillum", "orrery crumb",
    "thistledown", "krellmoor", "plinth sonata", "gwendolyth", "ashfall cadence",
]


def clean_goal(text: str) -> str:
    m = GOAL.search(text or "")
    if not m:
        return ""
    g = LEG_ID.sub(" ", m.group(1))
    g = re.sub(r"\bHandoff\b", " ", g)
    g = re.sub(r"\s+", " ", g).strip(" .:;-")
    return g[:160].rsplit(" ", 1)[0] if len(g) == 160 else g


def open_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)


def build(snapshot: Path) -> dict:
    dbs = sorted(snapshot.glob("nougen_shards_[0-9].db"))
    if not dbs:
        raise SystemExit(f"no nougen_shards_<n>.db under {snapshot}")
    by_title: dict[str, list[dict]] = {}
    corpus = {}
    for p in dbs:
        n = int(re.search(r"_(\d)\.db$", p.name).group(1))
        con = open_ro(p)
        corpus[p.name] = con.execute("select count(*) from shards").fetchone()[0]
        for sid, title, content in con.execute(
            "select id, title, content from shards where title like 'Autonomous Verified Relay:%'"
        ):
            by_title.setdefault(title, []).append({"db": n, "id": sid, "content": content})
        con.close()
    rows = []
    for title in sorted(by_title):
        copies = by_title[title]
        q = clean_goal(copies[0]["content"])
        if len(q.split()) < 6:  # too short to be a query
            continue
        rows.append({
            "kind": "answerable",
            "query": q,
            "gold": [{"db": c["db"], "id": c["id"]} for c in copies],
            "gold_title": title,
        })
    rng = random.Random(SEED)
    titles_blob = "\n".join(by_title).lower()
    noans = []
    for i in range(len(FICTIONAL)):
        a, b = rng.sample(FICTIONAL, 2)
        q = f"status of {a} {b} migration"
        if a in titles_blob or b in titles_blob:
            continue
        noans.append({"kind": "no_answer", "query": q, "gold": []})
    stamp = (snapshot / "SNAPSHOT_AT").read_text().strip() if (snapshot / "SNAPSHOT_AT").exists() else None
    body = {
        "name": "ngs-m0-labeled-v1",
        "snapshot_dir": "~/.nougen/replica/shards" if str(snapshot).startswith(os.path.expanduser("~")) else str(snapshot),
        "snapshot_at": stamp,
        "corpus_rows_per_db": corpus,
        "seed": SEED,
        "bias_note": "answerable queries are trimmed copies of gold bodies: lexically easy, favours keyword search; regression guard only",
        "items": rows + noans,
    }
    canon = json.dumps(body["items"], sort_keys=True, ensure_ascii=False).encode()
    body["items_sha256"] = hashlib.sha256(canon).hexdigest()
    body["counts"] = {"answerable": len(rows), "no_answer": len(noans)}
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=os.path.expanduser("~/.nougen/replica/shards"))
    ap.add_argument("--out", default=str(Path(__file__).with_name("labeled_v1.json")))
    a = ap.parse_args()
    body = build(Path(a.snapshot).expanduser())
    Path(a.out).write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"out": a.out, "counts": body["counts"], "sha256": body["items_sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
