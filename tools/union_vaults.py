"""Deduplicating offline union of two NouGen nine-database shard vaults.

The target must be stopped while ``--apply`` runs. Rows retain their original
metadata, float32 embedding BLOBs, sensitivity and encrypted bodies. Integer
row IDs are intentionally regenerated to avoid collisions; ``file_hash`` is
the durable identity. The target's FTS triggers update indexes on insert and
the central dedup cache is backfilled after every database commits.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


DB_COUNT = 9
BATCH = 2000


def _db(vault: Path, index: int) -> Path:
    return vault / f"nougen_shards_{index}.db"


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(shards)")]


def _existing_hashes(vault: Path) -> set[str]:
    seen: set[str] = set()
    for index in range(1, DB_COUNT + 1):
        path = _db(vault, index)
        if not path.exists():
            continue
        conn = sqlite3.connect(path)
        try:
            seen.update(row[0] for row in conn.execute(
                "SELECT file_hash FROM shards WHERE file_hash IS NOT NULL"))
        finally:
            conn.close()
    return seen


def _backfill_dedup(vault: Path) -> int:
    path = vault / "dedup_index.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                file_hash TEXT PRIMARY KEY,
                db_index INTEGER NOT NULL
            ) WITHOUT ROWID
        """)
        # This table is a derived routing cache, not an authority. Rebuild it
        # exactly so hashes for rolled-back or removed rows cannot survive and
        # cause future captures to false-deduplicate.
        conn.execute("DELETE FROM hashes")
        for index in range(1, DB_COUNT + 1):
            shard_db = _db(vault, index)
            if not shard_db.exists():
                continue
            src = sqlite3.connect(shard_db)
            try:
                cursor = src.execute(
                    "SELECT file_hash FROM shards WHERE file_hash IS NOT NULL")
                while True:
                    rows = cursor.fetchmany(BATCH)
                    if not rows:
                        break
                    conn.executemany(
                        "INSERT OR IGNORE INTO hashes(file_hash, db_index) VALUES (?, ?)",
                        [(row[0], index) for row in rows])
            finally:
                src.close()
        conn.commit()
        return conn.execute("SELECT COUNT(*) FROM hashes").fetchone()[0]
    finally:
        conn.close()


def union_vaults(source: Path, target: Path, apply: bool = False) -> dict:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ValueError("source and target vaults must differ")
    if not source.is_dir() or not target.is_dir():
        raise FileNotFoundError("source and target vault directories must exist")

    seen = _existing_hashes(target)
    starting = len(seen)
    report = {"mode": "apply" if apply else "dry-run", "starting_unique": starting,
              "inserted": 0, "duplicates": 0, "databases": {}}

    for index in range(1, DB_COUNT + 1):
        src_path, dst_path = _db(source, index), _db(target, index)
        if not src_path.exists() or not dst_path.exists():
            report["databases"][str(index)] = {"inserted": 0, "duplicates": 0,
                                                 "skipped": "missing source or target"}
            continue
        src = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
        dst = sqlite3.connect(dst_path)
        src.row_factory = sqlite3.Row
        try:
            common = [name for name in _columns(dst)
                      if name != "id" and name in set(_columns(src))]
            if "file_hash" not in common:
                raise RuntimeError(f"database {index} has no shared file_hash column")
            select_sql = f"SELECT {', '.join(common)} FROM shards ORDER BY id"
            placeholders = ", ".join("?" for _ in common)
            insert_sql = (f"INSERT OR IGNORE INTO shards ({', '.join(common)}) "
                          f"VALUES ({placeholders})")
            hash_pos = common.index("file_hash")
            starting_rows = dst.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            planned = duplicates = 0
            cursor = src.execute(select_sql)
            while True:
                rows = cursor.fetchmany(BATCH)
                if not rows:
                    break
                fresh = []
                for row in rows:
                    values = tuple(row[name] for name in common)
                    fhash = values[hash_pos]
                    if not fhash or fhash in seen:
                        duplicates += 1
                        continue
                    seen.add(fhash)
                    fresh.append(values)
                if apply and fresh:
                    dst.executemany(insert_sql, fresh)
                planned += len(fresh)
            if apply:
                dst.commit()
                inserted = (dst.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
                            - starting_rows)
            else:
                inserted = planned
            report["databases"][str(index)] = {
                "inserted": inserted, "duplicates": duplicates}
            report["inserted"] += inserted
            report["duplicates"] += duplicates
        finally:
            dst.close()
            src.close()

    report["ending_unique"] = len(seen)
    if apply:
        report["dedup_index"] = _backfill_dedup(target)
    return report


def verify_vault(vault: Path) -> dict:
    from nougen_shards import private_vault

    total = fts = private = private_errors = 0
    integrity = {}
    hashes: set[str] = set()
    for index in range(1, DB_COUNT + 1):
        path = _db(vault, index)
        if not path.exists():
            integrity[str(index)] = "missing"
            continue
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            integrity[str(index)] = conn.execute("PRAGMA integrity_check").fetchone()[0]
            total += conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            hashes.update(row[0] for row in conn.execute(
                "SELECT file_hash FROM shards WHERE file_hash IS NOT NULL"))
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "shards_fts" in tables:
                fts += conn.execute("SELECT COUNT(*) FROM shards_fts").fetchone()[0]
            cols = set(_columns(conn))
            if {"sensitivity", "content"} <= cols:
                rows = conn.execute(
                    "SELECT content FROM shards WHERE sensitivity IN ('private','secret')")
                for row in rows:
                    private += 1
                    try:
                        private_vault.decrypt_text(row["content"])
                    except Exception:  # report only; never print private content
                        private_errors += 1
        finally:
            conn.close()
    dedup_path = vault / "dedup_index.db"
    dedup = 0
    if dedup_path.exists():
        conn = sqlite3.connect(dedup_path)
        try:
            dedup = conn.execute("SELECT COUNT(*) FROM hashes").fetchone()[0]
        finally:
            conn.close()
    return {"total_rows": total, "unique_hashes": len(hashes), "fts_rows": fts,
            "dedup_rows": dedup, "private_rows": private,
            "private_decrypt_errors": private_errors, "integrity": integrity}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--apply", action="store_true",
                        help="write the union; default is a read-only dry run")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = {"union": union_vaults(args.source, args.target, apply=args.apply)}
    if args.verify and args.apply:
        result["verification"] = verify_vault(args.target)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
