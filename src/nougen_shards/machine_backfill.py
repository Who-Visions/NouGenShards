"""
Machine-tag backfill: stamp every shard in a vault with ``machine:<host>`` so scope
filters (distill.scope_matches, recall --machine) work on this node's own memory.

Why: a node's shards get their machine identity at federation read time, not in the
row. Local scope filtering and cross-node provenance need it stored. GM order
2026-09-15: every machine backfills its own vault natively through the CLI.

Design (mirrors embedding_backfill):
  * DYNAMIC: the host name is discovered at run time (NOUGEN_MACHINE_ID env first,
    then socket.gethostname()); never typed into a script.
  * IDEMPOTENT: rows that already carry any ``machine:`` tag are left alone unless
    --force rewrites a different host's tag to this host (off by default).
  * SQL-SIDE: json_insert on the tags array, one UPDATE per DB, no Python row loop.
  * MUTATION-GATED: dry-run by default; writes only with execute=True.
  * LOCK-AWARE: busy timeout from NOUGEN_SQLITE_TIMEOUT_S (fallback logged).

Usage:
    nougen backfill machine                 # dry run: counts per DB
    nougen backfill machine --execute       # write
    python -m nougen_shards.machine_backfill --vault <dir> --execute
"""
from __future__ import annotations

import glob
import json
import logging
import os
import socket
import sqlite3
import time
from typing import Optional

_log = logging.getLogger(__name__)


def machine_id() -> str:
    """NOUGEN_MACHINE_ID wins; otherwise the live host name, lower-cased."""
    raw = os.environ.get("NOUGEN_MACHINE_ID", "").strip().lower()
    if raw:
        return raw
    host = socket.gethostname().strip().lower()
    _log.debug("NOUGEN_MACHINE_ID unset; using live hostname %r", host)
    return host


def _sqlite_timeout() -> float:
    raw = os.environ.get("NOUGEN_SQLITE_TIMEOUT_S", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            _log.warning("NOUGEN_SQLITE_TIMEOUT_S=%r is not a number; using fallback 30", raw)
    else:
        _log.debug("NOUGEN_SQLITE_TIMEOUT_S unset; using fallback 30")
    return 30.0


def vault_dir(explicit: Optional[str] = None) -> str:
    v = explicit or os.environ.get("NOUGEN_VAULT_DIR", "").strip()
    if not v:
        v = os.path.expanduser(os.path.join("~", ".nougen", "shards"))
        _log.debug("NOUGEN_VAULT_DIR unset; using fallback %s", v)
    return v


def vault_dbs(vault: str) -> list[str]:
    return sorted(glob.glob(os.path.join(vault, "nougen_shards_*.db")))


def _connect(db: str) -> sqlite3.Connection:
    tmo = _sqlite_timeout()
    c = sqlite3.connect(db, timeout=tmo)
    c.execute("PRAGMA busy_timeout=%d" % int(tmo * 1000))
    return c


def count_db(db: str, tag: str) -> dict:
    """Rows: total, already tagged with THIS host, tagged with another host, untagged."""
    c = _connect(db)
    try:
        total = c.execute("select count(*) from shards").fetchone()[0]
        mine = c.execute("select count(*) from shards where tags like ?", (f'%"{tag}"%',)).fetchone()[0]
        other = c.execute(
            "select count(*) from shards where tags like '%\"machine:%' and tags not like ?", (f'%"{tag}"%',)
        ).fetchone()[0]
        return {"db": os.path.basename(db), "total": total, "mine": mine, "other_host": other,
                "untagged": total - mine - other}
    finally:
        c.close()


def backfill_db(db: str, tag: str, execute: bool, force: bool = False) -> dict:
    """Stamp `tag` on every row lacking a machine tag. Returns counts; writes only if execute."""
    before = count_db(db, tag)
    if not execute:
        return before | {"written": 0, "dry_run": True}
    c = _connect(db)
    try:
        with c:
            n_arr = c.execute(
                "update shards set tags=json_insert(tags,'$[#]',?) "
                "where json_valid(tags) and json_type(tags)='array' "
                "and tags not like '%\"machine:%'", (tag,)).rowcount
            n_bad = c.execute(
                "update shards set tags=json_array(?) "
                "where tags is null or not json_valid(tags) or json_type(tags)<>'array'", (tag,)).rowcount
            n_force = 0
            if force:
                # replace any other host's machine tag with this host's (rare: migrated vaults)
                rows = c.execute(
                    "select id, tags from shards where tags like '%\"machine:%' and tags not like ?",
                    (f'%"{tag}"%',)).fetchall()
                for sid, raw in rows:
                    tags = [t for t in json.loads(raw) if not str(t).startswith("machine:")] + [tag]
                    c.execute("update shards set tags=? where id=?", (json.dumps(tags), sid))
                n_force = len(rows)
    finally:
        c.close()
    after = count_db(db, tag)
    return after | {"written": n_arr + n_bad + n_force, "dry_run": False}


def run(vault: Optional[str] = None, execute: bool = False, force: bool = False,
        tag: Optional[str] = None) -> dict:
    v = vault_dir(vault)
    t = tag or f"machine:{machine_id()}"
    t0 = time.time()
    per_db = [backfill_db(db, t, execute, force) for db in vault_dbs(v)]
    return {
        "vault": v, "tag": t, "execute": execute, "force": force,
        "dbs": per_db,
        "total": sum(d["total"] for d in per_db),
        "mine": sum(d["mine"] for d in per_db),
        "untagged": sum(d["untagged"] for d in per_db),
        "written": sum(d["written"] for d in per_db),
        "seconds": round(time.time() - t0, 1),
    }


def _main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Stamp machine:<host> on every shard in a vault.")
    ap.add_argument("--vault", help="vault dir (default NOUGEN_VAULT_DIR, then ~/.nougen/shards)")
    ap.add_argument("--execute", action="store_true", help="write; default is a dry run")
    ap.add_argument("--force", action="store_true", help="also rewrite another host's machine tag to this host")
    ap.add_argument("--tag", help="override the tag (default machine:<discovered host>)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    r = run(a.vault, a.execute, a.force, a.tag)
    if a.json:
        print(json.dumps(r, indent=1))
    else:
        for d in r["dbs"]:
            print(f'{d["db"]}: total {d["total"]} mine {d["mine"]} other {d["other_host"]} '
                  f'untagged {d["untagged"]} written {d["written"]}')
        mode = "WROTE" if r["execute"] else "DRY RUN"
        print(f'{mode} {r["tag"]}: {r["written"]} written, {r["untagged"]} still untagged of {r["total"]} '
              f'in {r["seconds"]}s ({r["vault"]})')
    return 0 if r["untagged"] == 0 or not r["execute"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
