"""Model-free integrity checks for the distill sidecar (nougen_distill.db).

    python tools/check_distill_integrity.py            # read-only report on the live sidecar
    python tools/check_distill_integrity.py --json

Derived layers are text produced by a model, so they cannot be re-derived exactly. These checks are
the parts that can be decided without a model:

  stale     a distilled shard's content_hash no longer matches its source shard (title + body, sha1,
            the same recipe distill_shard uses). Its atoms describe text that has changed.
  orphan    a distilled shard whose source row no longer exists in the vault (the vault was read
            and the row is genuinely absent).
  unreadable  a source database could not be opened or read. Reported as its own class, never as orphan.
  leftover  a distilled row whose status is not done but that still has atoms, mentions or edges. A failed
            re-distill deletes nothing until it succeeds, so old derived rows survive the failure.
  dangling  an atom, mention or edge pointing at a shard_key that is not distilled, or an entity id
            that does not exist.
  scene_lag a scene's n_shards differs from the distinct shards that mention its entity. build_scenes
            only rewrites a scene when its count changes, so a mismatch is reported as lag, not corruption.

Nothing is written. The sidecar is opened read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

Source = Callable[[list[str]], tuple]  # keys -> ({key: {"title", "content"}}, unreadable_keys)


def content_hash(title, body) -> str:
    """Same recipe as distill.distill_shard."""
    return hashlib.sha1(f"{title}\n{body}".encode("utf-8", "replace")).hexdigest()


def check(conn: sqlite3.Connection, source: Source) -> dict:
    findings: list[dict] = []

    def add(kind: str, key: str, detail: str) -> None:
        findings.append({"check": kind, "key": key, "detail": detail})

    done = {
        k: h
        for k, h in conn.execute("SELECT shard_key, content_hash FROM distilled WHERE status='done'")
    }
    sources, unreadable = source(list(done)) if done else ({}, set())
    for key, want in done.items():
        row = sources.get(key)
        if key in unreadable:
            add("unreadable", key, "source database could not be read; not judged")
        elif row is None:
            add("orphan", key, "source shard absent from a readable vault")
        elif content_hash(row.get("title"), row.get("content") or "") != want:
            add("stale", key, "content_hash no longer matches the source shard")

    for (key, status) in conn.execute("SELECT shard_key, status FROM distilled WHERE status IS NOT 'done'"):
        n = sum(
            conn.execute(f"SELECT COUNT(*) FROM {t} WHERE shard_key=?", (key,)).fetchone()[0]
            for t in ("atoms", "mentions", "edges")
        )
        if n:
            add("leftover", key, f"status {status!r} but {n} derived rows survive from before the failure")

    distilled = {k for (k,) in conn.execute("SELECT shard_key FROM distilled")}
    for table in ("atoms", "mentions", "edges"):
        col = "shard_key"
        for (k,) in conn.execute(f"SELECT DISTINCT {col} FROM {table}"):
            if k not in distilled:
                add("dangling", k, f"{table} rows for a shard that is not in distilled")

    entities = {i for (i,) in conn.execute("SELECT id FROM entities")}
    for table, cols in (("mentions", ["entity_id"]), ("edges", ["src", "dst"])):
        for row in conn.execute(f"SELECT {', '.join(cols)} FROM {table}"):
            for c, v in zip(cols, row):
                if v not in entities:
                    add("dangling", f"{table}.{c}={v}", "entity id does not exist")

    mentioned = defaultdict(set)
    for eid, k in conn.execute("SELECT entity_id, shard_key FROM mentions"):
        mentioned[eid].add(k)
    for eid, n in conn.execute("SELECT entity_id, n_shards FROM scenes"):
        actual = len(mentioned.get(eid, ()))
        if actual != n:
            add("scene_lag", f"entity {eid}", f"scene says {n} shards, mentions show {actual}")

    counts = defaultdict(int)
    for f in findings:
        counts[f["check"]] += 1
    return {
        "distilled_done": len(done),
        "counts": dict(sorted(counts.items())),
        "findings": findings,
    }


def vault_source(keys: list[str]) -> tuple:
    """Read source rows straight from each vault DB, read-only.

    Does not go through core.get_connection (that opens read-write and sets journal_mode).
    A missing or unreadable DB marks its keys unreadable instead of silently dropping them.
    Returns (rows, unreadable_keys)."""
    from nougen_shards import core, distill  # pylint: disable=import-outside-toplevel
    from nougen_shards.core import hydrate  # pylint: disable=import-outside-toplevel

    by_db: dict[int, list[int]] = {}
    for k in keys:
        db, sid = distill._split(k)  # noqa: SLF001
        by_db.setdefault(db, []).append(sid)
    rows, unreadable = {}, set()
    for db, ids in by_db.items():
        keys_db = {distill.shard_key(db, i) for i in ids}
        path = core.get_db_path(db)
        if not path.exists():
            unreadable |= keys_db
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
            try:
                marks = ",".join("?" * len(ids))
                cur = conn.execute(
                    f"SELECT {distill.SHARD_COLS} FROM shards WHERE id IN ({marks})", ids)
                cols = [c[0] for c in cur.description]
                for row in cur.fetchall():
                    item = hydrate(dict(zip(cols, row)))
                    rows[distill.shard_key(db, item["id"])] = {
                        "title": item.get("title"), "content": item.get("content")}
            finally:
                conn.close()
        except (sqlite3.Error, OSError):
            unreadable |= keys_db
    return rows, unreadable


def open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", help="sidecar path (default: distill.sidecar_path())")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    from nougen_shards import distill  # pylint: disable=import-outside-toplevel

    path = Path(args.path) if args.path else distill.sidecar_path()
    conn = open_readonly(path)
    try:
        report = check(conn, vault_source)
    finally:
        conn.close()
    report["path"] = str(path)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"sidecar: {path}")
        print(f"distilled (done): {report['distilled_done']}")
        print(f"findings: {report['counts'] or 'none'}")
        for f in report["findings"][:40]:
            print(f"  [{f['check']}] {f['key']}: {f['detail']}")
        if len(report["findings"]) > 40:
            print(f"  ... {len(report['findings']) - 40} more (use --json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
