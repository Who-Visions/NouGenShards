"""Build FTS5 indexes on registered local vaults so federated recall stops
scanning them row by row.

Why this and not more threads: the sweep was disk-bound, not concurrency-bound —
a LIKE scan reads every row of every vault, so ~500k rows across 36 vaults cost
20-30s no matter how many workers ran it. An index removes the scan instead of
sharing it out.

Uses **external-content** FTS5 (`content='<table>'`): the index stores terms and
positions only and reads column values back from the source table, so it does not
duplicate the vault's text. That matters here — one vault holds 379k rows.

Safe to re-run: an existing index of the right name is left alone unless --rebuild
is passed. Indexes are additive; dropping them (`DROP TABLE <table>_ngsfts`)
returns each vault to exactly its previous state, and the connector falls back to
LIKE automatically.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from nougen_shards import keymaker  # noqa: E402

#: Suffix kept distinct from any pre-existing `<table>_fts` so we never collide
#: with, or clobber, an index the vault already maintains for its own purposes.
FTS_SUFFIX = "_ngsfts"

#: Below this, a LIKE scan is already fast and an index is not worth the write.
MIN_ROWS = int(os.environ.get("NOUGEN_FTS_MIN_ROWS", "5000"))


def build_for(conf: dict, rebuild: bool) -> tuple[str, str]:
    path = Path(conf["path"])
    table = conf["table_name"]
    title_col = conf["title_col"]
    content_col = conf["content_col"]
    fts = f"{table}{FTS_SUFFIX}"

    if not path.exists():
        return path.name, "missing"

    conn = sqlite3.connect(str(path), timeout=30)
    try:
        rows = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        if rows < MIN_ROWS:
            return path.name, f"skipped ({rows:,} rows < {MIN_ROWS:,})"

        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (fts,)).fetchone()
        if exists and not rebuild:
            return path.name, f"already indexed ({rows:,} rows)"
        if exists:
            conn.execute(f'DROP TABLE "{fts}"')

        t0 = time.time()
        # Distinct column names are required even when title and content are the
        # same source column (some vaults have no separate title).
        if title_col == content_col:
            conn.execute(
                f'CREATE VIRTUAL TABLE "{fts}" USING fts5('
                f'"{content_col}", content="{table}", content_rowid="rowid")')
        else:
            conn.execute(
                f'CREATE VIRTUAL TABLE "{fts}" USING fts5('
                f'"{title_col}", "{content_col}", content="{table}", content_rowid="rowid")')
        conn.execute(f'INSERT INTO "{fts}"("{fts}") VALUES(\'rebuild\')')
        conn.commit()
        conn.execute("PRAGMA optimize")
        return path.name, f"built in {time.time()-t0:.1f}s ({rows:,} rows)"
    except sqlite3.Error as exc:
        # A read-only file, a lock, or a table shape FTS cannot mirror: report and
        # move on. The connector keeps working via LIKE for that vault.
        return path.name, f"FAILED: {type(exc).__name__}: {exc}"
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="drop and rebuild existing indexes")
    args = ap.parse_args()

    configs = keymaker.list_local_vaults()
    print(f"[*] {len(configs)} registered vault(s), min rows to index: {MIN_ROWS:,}\n")
    for conf in sorted(configs, key=lambda c: c["path"]):
        name, status = build_for(conf, args.rebuild)
        print(f"    {name:34s} {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
