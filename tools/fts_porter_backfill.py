"""Build an additive stemmed FTS5 lane (``shards_fts_porter``) beside the
existing trigram ``shards_fts`` table.

Trigram FTS matches 3-character substrings, so ``MATCH 'hang'`` also hits
*change*, *exchange* and *hanging*, and BM25 over trigrams carries little term
relevance. This tool adds a word-tokenized lane so ranking means something,
without touching the trigram table -- rollback is ``DROP TABLE shards_fts_porter``.

Idempotent: an already-populated lane is left alone unless ``--rebuild``.
Additive only: never modifies or drops ``shards`` or ``shards_fts``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

PORTER_TABLE = "shards_fts_porter"

# Tokenizer preference order. Probed against the live SQLite build rather than
# assumed -- older builds may lack the porter wrapper (Rule 0.2).
TOKENIZER_CANDIDATES = (
    os.environ.get("NOUGEN_FTS_TOKENIZER") or "porter unicode61",
    "unicode61",
)

DEFAULT_SCOPE_GLOB = "nougen_shards_*.db"

# Directory NAME (never a rooted path) of the workspace under $HOME that
# conventionally holds the vault. Joined onto the runtime `Path.home()` so the
# last-resort branch works for any operator instead of one machine's layout.
FALLBACK_WORKSPACE_DIR_NAME = "Watchtower"


def resolve_vault_dir() -> Path:
    """env -> ~/.nougen/config.json -> home-relative default, first hit wins."""
    env = os.environ.get("NOUGEN_VAULT_DIR")
    if env:
        return Path(env)
    cfg = Path.home() / ".nougen" / "config.json"
    if cfg.exists():
        try:
            value = json.loads(cfg.read_text(encoding="utf-8")).get("vault_dir")
            if value:
                return Path(value)
        except (OSError, ValueError):
            pass
    workspace = (os.environ.get("NOUGEN_WORKSPACE_DIR_NAME")
                 or FALLBACK_WORKSPACE_DIR_NAME)
    return Path.home() / workspace / "vault"


def resolve_scope_glob() -> str:
    return os.environ.get("NOUGEN_SCOPE_GLOB", DEFAULT_SCOPE_GLOB)


def _existing_tokenizer(con: sqlite3.Connection, table: str) -> str | None:
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row or not row[0]:
        return None
    match = re.search(r"tokenize\s*=\s*'([^']+)'", row[0])
    return match.group(1) if match else "?"


def _pick_tokenizer(con: sqlite3.Connection) -> str:
    """Probe candidates against this SQLite build; return the first that works."""
    for tok in TOKENIZER_CANDIDATES:
        probe = "_nougen_tok_probe"
        try:
            con.execute(
                f"CREATE VIRTUAL TABLE {probe} USING fts5(x, tokenize='{tok}')"
            )
            con.execute(f"DROP TABLE {probe}")
            return tok
        except sqlite3.OperationalError:
            try:
                con.execute(f"DROP TABLE IF EXISTS {probe}")
            except sqlite3.OperationalError:
                pass
    raise RuntimeError("no usable FTS5 tokenizer found")


def _row_count(con: sqlite3.Connection, table: str) -> int:
    try:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return -1


def process_db(path: Path, *, apply: bool, rebuild: bool, timeout: float) -> dict:
    out = {"db": path.name, "action": "skip", "shards": 0, "indexed": 0}
    con = sqlite3.connect(path, timeout=timeout)
    try:
        con.execute("PRAGMA busy_timeout = %d" % int(timeout * 1000))
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "shards" not in tables:
            out["action"] = "no-shards-table"
            return out

        out["shards"] = _row_count(con, "shards")
        out["trigram_tokenizer"] = _existing_tokenizer(con, "shards_fts")

        present = PORTER_TABLE in tables
        if present and not rebuild:
            count = _row_count(con, PORTER_TABLE)
            if count >= out["shards"] > 0:
                out.update(action="already-current", indexed=count)
                return out

        tok = _pick_tokenizer(con)
        out["tokenizer"] = tok

        if not apply:
            out["action"] = "would-rebuild" if present else "would-create"
            return out

        # Additive only. The trigram table is never touched.
        con.execute(f"DROP TABLE IF EXISTS {PORTER_TABLE}")
        con.execute(
            f"CREATE VIRTUAL TABLE {PORTER_TABLE} USING fts5("
            "    title, content, content='shards', content_rowid='id',"
            f"    tokenize='{tok}')"
        )
        con.execute(
            f"INSERT INTO {PORTER_TABLE}({PORTER_TABLE}) VALUES('rebuild')"
        )
        con.commit()
        out.update(action="rebuilt" if present else "created",
                   indexed=_row_count(con, PORTER_TABLE))
        return out
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default is a dry run)")
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild the lane even when it looks current")
    ap.add_argument("--vault", default=None, help="override vault dir")
    ap.add_argument("--timeout", type=float,
                    default=float(os.environ.get("NOUGEN_DB_TIMEOUT", "30")))
    args = ap.parse_args()

    vault = Path(args.vault) if args.vault else resolve_vault_dir()
    glob_pat = resolve_scope_glob()
    dbs = sorted(vault.glob(glob_pat))
    print(f"vault={vault}  scope={glob_pat}  dbs={len(dbs)}  "
          f"mode={'APPLY' if args.apply else 'DRY-RUN'}", flush=True)
    if not dbs:
        print("no in-scope databases found", file=sys.stderr)
        return 1

    results, failures = [], 0
    for db in dbs:
        try:
            res = process_db(db, apply=args.apply, rebuild=args.rebuild,
                             timeout=args.timeout)
        except Exception as exc:  # keep the rest of the set consistent
            res = {"db": db.name, "action": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
            failures += 1
        results.append(res)
        print(f"  {res['db']:22s} {res['action']:16s} "
              f"shards={res.get('shards', 0):6d} indexed={res.get('indexed', 0):6d}"
              + (f"  tok={res.get('tokenizer')}" if res.get("tokenizer") else "")
              + (f"  ERR={res['error']}" if res.get("error") else ""), flush=True)

    print(json.dumps({"vault": str(vault), "databases": len(dbs),
                      "failures": failures, "results": results}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
