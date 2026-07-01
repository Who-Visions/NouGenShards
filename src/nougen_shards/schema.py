"""
Dynamic, versioned schema migration for the NouGen shard cluster.

Replaces the ad-hoc `try/except ALTER TABLE` soup in core.init_db with an
idempotent, version-tracked migration runner applied uniformly across every
shard DB (current and future). Each DB carries its schema version in
`PRAGMA user_version`; migrations strictly greater than the stored version run
in a single transaction, then the version is stamped.

Mutation-gated by design: `plan_vault()` and the CLI default are READ-ONLY
(dry-run). Nothing is written to a vault unless `execute=True` is passed, and
even then each DB is backed up to `<db>.bak` first so a bad pass can be rolled
back. This is the fail-safe pattern from the Keymaker DPAPI migration.

Usage:
    python -m nougen_shards.schema --vault <dir>            # dry-run report
    python -m nougen_shards.schema --vault <dir> --execute  # apply (backs up first)
"""
from __future__ import annotations

import os
import sqlite3
import shutil
import glob
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# Bump this when adding a migration. Stored per-DB in PRAGMA user_version.
TARGET_SCHEMA_VERSION = 1


# --- introspection helpers (idempotent, no exceptions for control flow) ---

def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _indexes(conn: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _user_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


# --- a migration is a named, version-tagged set of ops that return SQL/text
#     describing exactly what it WILL do (so dry-run can report it precisely). ---

@dataclass
class Migration:
    version: int
    name: str
    # plan(conn) -> list of human-readable op descriptions for ops still pending.
    plan: Callable[[sqlite3.Connection], List[str]]
    # apply(conn) -> performs the ops. Must be idempotent.
    apply: Callable[[sqlite3.Connection], None]


def _ensure_columns(conn, table, specs):
    """specs: list of (col_name, ddl_type_default). Returns pending op strings."""
    have = _columns(conn, table)
    pending = []
    for col, ddl in specs:
        if col not in have:
            pending.append(f"ADD COLUMN {table}.{col} {ddl}")
    return pending


# Declarative desired state for shards. Adding a column here + bumping
# TARGET_SCHEMA_VERSION is all a future column needs — the runner backfills
# and stamps the version. NULL-safe defaults required.
_SHARD_COLUMNS = [
    ("embedding", "BLOB"),
    ("domain_key", "TEXT DEFAULT 'global'"),
    ("density_score", "REAL DEFAULT 1.0"),
    ("consolidated", "INTEGER DEFAULT 0"),
    ("schema_version", "INTEGER DEFAULT 0"),  # per-row provenance for staged backfills
]

_SHARD_INDEXES = [
    ("idx_shards_domain_utility", "CREATE INDEX IF NOT EXISTS idx_shards_domain_utility ON shards (domain_key, utility_score DESC)"),
    ("idx_shards_consolidated", "CREATE INDEX IF NOT EXISTS idx_shards_consolidated ON shards (consolidated)"),
    ("idx_shards_embedding_present", "CREATE INDEX IF NOT EXISTS idx_shards_embedding_present ON shards (id) WHERE embedding IS NOT NULL"),
]


def _plan_v1(conn) -> List[str]:
    ops: List[str] = []
    if not _table_exists(conn, "shards"):
        return ["CREATE TABLE shards (full base schema)"]
    ops += _ensure_columns(conn, "shards", _SHARD_COLUMNS)
    have_idx = _indexes(conn, "shards")
    for name, _ddl in _SHARD_INDEXES:
        if name not in have_idx:
            ops.append(f"CREATE INDEX {name}")
    return ops


def _apply_v1(conn) -> None:
    have = _columns(conn, "shards")
    for col, ddl in _SHARD_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE shards ADD COLUMN {col} {ddl}")
    for _name, ddl in _SHARD_INDEXES:
        conn.execute(ddl)


MIGRATIONS: List[Migration] = [
    Migration(1, "baseline-columns-indexes-versioning", _plan_v1, _apply_v1),
]


# --- per-DB + per-vault drivers ---

@dataclass
class DbPlan:
    path: str
    from_version: int
    to_version: int
    pending: List[str] = field(default_factory=list)


def plan_db(path: str) -> DbPlan:
    conn = sqlite3.connect(path)
    try:
        cur = _user_version(conn)
        p = DbPlan(path=path, from_version=cur, to_version=TARGET_SCHEMA_VERSION)
        for m in MIGRATIONS:
            if m.version > cur:
                p.pending.extend(f"[v{m.version}] {op}" for op in m.plan(conn))
        return p
    finally:
        conn.close()


def apply_db(path: str, backup: bool = True) -> DbPlan:
    p = plan_db(path)
    if p.from_version >= TARGET_SCHEMA_VERSION:
        return p  # already current
    if backup:
        shutil.copy2(path, path + ".bak")
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA busy_timeout=15000;")
        conn.execute("BEGIN")
        for m in MIGRATIONS:
            if m.version > p.from_version:
                m.apply(conn)
        conn.execute(f"PRAGMA user_version = {TARGET_SCHEMA_VERSION}")
        conn.execute("COMMIT")
    except Exception:
        # Close the sqlite handle BEFORE restoring the backup file: copying over
        # an open db can corrupt/lock it (notably on Windows).
        try:
            conn.execute("ROLLBACK")
        finally:
            conn.close()
        if backup:
            shutil.copy2(path + ".bak", path)  # restore
        raise
    finally:
        conn.close()
    return plan_db(path)  # re-read to confirm


def _vault_dbs(vault_dir: str) -> List[str]:
    return sorted(glob.glob(os.path.join(vault_dir, "nougen_shards_*.db")))


def plan_vault(vault_dir: str) -> List[DbPlan]:
    return [plan_db(db) for db in _vault_dbs(vault_dir)]


def migrate_vault(vault_dir: str, execute: bool = False, backup: bool = True) -> List[DbPlan]:
    if not execute:
        return plan_vault(vault_dir)
    return [apply_db(db, backup=backup) for db in _vault_dbs(vault_dir)]


def _main(argv=None):
    import argparse, sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Dynamic versioned schema migration for the shard cluster.")
    ap.add_argument("--vault", default=os.environ.get("NOUGEN_VAULT_DIR"), required=False)
    ap.add_argument("--execute", action="store_true", help="apply migrations (backs up each DB to .bak first)")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args(argv)
    if not args.vault:
        ap.error("--vault or NOUGEN_VAULT_DIR required")

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== schema migration [{mode}] target=v{TARGET_SCHEMA_VERSION} vault={args.vault} ===")
    plans = migrate_vault(args.vault, execute=args.execute, backup=not args.no_backup)
    total_pending = 0
    for p in plans:
        name = os.path.basename(p.path)
        if p.pending:
            total_pending += len(p.pending)
            print(f"\n{name}: v{p.from_version} -> v{p.to_version}")
            for op in p.pending:
                print(f"   - {op}")
        else:
            print(f"{name}: v{p.from_version} (current, no changes)")
    if not args.execute and total_pending:
        print(f"\n{total_pending} pending ops across {len(plans)} DBs. Re-run with --execute to apply (each DB backed up to .bak).")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
