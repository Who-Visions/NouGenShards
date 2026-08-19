"""Register the sibling SQLite vaults alongside the shard substrate.

Schemas are DISCOVERED, not declared: each vault is opened read-only, its tables
inspected, and the best (table, title_col, content_col) triple chosen by which
one actually holds retrievable text. A vault whose schema later changes is
re-registered correctly by re-running this — nothing here encodes a layout that
can silently go stale.

`nougen_shards_*.db` are skipped: core.retrieve already reads them, and
registering them here would double every local hit through the RRF merge.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from nougen_shards import core, keymaker  # noqa: E402

TITLE_NAMES = ("title", "name", "subject", "heading")
CONTENT_NAMES = ("content", "body", "text", "description", "summary")


def best_schema(db: Path):
    """(table, title_col, content_col, rows) for the richest text table, or None."""
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        best = None
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%'")]
        for table in tables:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            lower = {c.lower(): c for c in cols}
            content = next((lower[n] for n in CONTENT_NAMES if n in lower), None)
            if not content:
                continue
            title = next((lower[n] for n in TITLE_NAMES if n in lower), content)
            try:
                rows = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            except sqlite3.Error:
                continue
            if best is None or rows > best[3]:
                best = (table, title, content, rows)
        return best
    finally:
        conn.close()


def main() -> int:
    vault_dir = Path(os.environ.get("NOUGEN_VAULT_DIR", str(core.GLOBAL_DIR)))
    print(f"[*] vault dir: {vault_dir}")
    if not vault_dir.is_dir():
        raise SystemExit(f"[!] vault dir does not exist: {vault_dir}")

    # Registered vaults become reachable through the public (token-gated) node,
    # so which ones are in is a policy call, not a technical one. Comma-separated
    # fnmatch patterns against the file stem; nothing is excluded by default so
    # the decision stays explicit and visible rather than buried in this file.
    exclude = [p.strip() for p in os.environ.get("NOUGEN_LOCAL_VAULT_EXCLUDE", "").split(",") if p.strip()]
    if exclude:
        print(f"[*] excluding: {', '.join(exclude)}")

    registered = 0
    for db in sorted(vault_dir.glob("*.db")):
        if db.stem.startswith("nougen_shards_"):
            continue  # already the primary substrate
        if any(fnmatch(db.stem, pat) for pat in exclude):
            print(f"    skip  {db.name:34s} (excluded by policy)")
            continue
        schema = best_schema(db)
        if not schema:
            print(f"    skip  {db.name:34s} (no text-bearing table found)")
            continue
        table, title, content, rows = schema
        keymaker.register_local_vault(str(db), table, title, content)
        registered += 1
        print(f"    add   {db.name:34s} {table}({title},{content})  rows={rows:,}")

    print(f"\n[=] {registered} local vault(s) registered")
    for v in keymaker.list_local_vaults():
        print(f"    #{v['id']}: {Path(v['path']).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
