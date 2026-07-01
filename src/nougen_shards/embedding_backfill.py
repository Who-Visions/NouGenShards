"""
Embedding backfill for the shard cluster — revives the dead semantic recall lane.

All 47k+ shards currently have embedding=NULL, so _vector_retrieve (WHERE
embedding IS NOT NULL) returns nothing and recall is keyword-only. This tool
generates an embedding per shard via a local ollama embed model and stores it as
a float32 BLOB (the format _vector_retrieve expects: np.frombuffer(dtype=float32)).

Design:
  * LOCAL + FREE: embeds via ollama /api/embed on 127.0.0.1 (no cloud, no exfil).
  * RESUMABLE: only touches rows where embedding IS NULL, so it can stop/restart
    without redoing work. Stamps schema_version=1 per backfilled row when present.
  * VRAM-AWARE: checks nvidia-smi before each batch; pauses if the GPU is hot.
  * MUTATION-GATED: dry-run by default. Writes to the vault only with execute=True.

Prereq: ollama must be running with embeddings enabled (`ollama serve` started
with --embeddings) and an embed-capable model pulled (e.g. nomic-embed-text).

Usage:
    python -m nougen_shards.embedding_backfill --vault <dir> --model nomic-embed-text
    python -m nougen_shards.embedding_backfill --vault <dir> --model nomic-embed-text --execute
"""
from __future__ import annotations

import os
import json
import glob
import time
import struct
import sqlite3
import urllib.request
from typing import List, Optional

def _normalize_host(h: str) -> str:
    """ollama client target. Handles missing scheme/port and 0.0.0.0 bind addr."""
    from urllib.parse import urlparse
    h = (h or "").strip() or "http://127.0.0.1:11434"
    if "://" not in h:
        h = "http://" + h
    h = h.replace("0.0.0.0", "127.0.0.1")  # bind-all is not a connectable target
    if not urlparse(h).port:
        h = h.rstrip("/") + ":11434"
    return h.rstrip("/")


OLLAMA_HOST = _normalize_host(os.environ.get("OLLAMA_HOST"))
VRAM_CEILING_MIB = int(os.environ.get("NOUGEN_VRAM_CEILING", "6800"))  # pause above this


def _vram_used_mib() -> Optional[int]:
    import subprocess
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        return int(out[0]) if out else None
    except Exception:
        return None


def embed(text: str, model: str, timeout: int = 60) -> Optional[List[float]]:
    """Single embedding via ollama /api/embed. Returns None on failure."""
    body = json.dumps({"model": model, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/embed", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        vec = data.get("embeddings") or data.get("embedding")
        if vec and isinstance(vec[0], list):
            vec = vec[0]
        return vec
    except Exception:
        return None


def _pack(vec: List[float]) -> bytes:
    """float32 little-endian BLOB — matches np.frombuffer(dtype=np.float32)."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _has_col(conn, table, col) -> bool:
    return col in {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _vault_dbs(vault_dir: str) -> List[str]:
    return sorted(glob.glob(os.path.join(vault_dir, "nougen_shards_*.db")))


def count_pending(vault_dir: str) -> dict:
    out = {}
    for db in _vault_dbs(vault_dir):
        conn = sqlite3.connect(db)
        try:
            total = conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM shards WHERE embedding IS NULL").fetchone()[0]
            out[os.path.basename(db)] = (pending, total)
        finally:
            conn.close()
    return out


def backfill_db(db: str, model: str, execute: bool, batch: int = 64, probe: bool = True) -> dict:
    conn = sqlite3.connect(db)
    done = 0
    failed = 0
    try:
        has_ver = _has_col(conn, "shards", "schema_version")
        conn.execute("PRAGMA busy_timeout=30000;")
        rows = conn.execute(
            "SELECT id, title, content FROM shards WHERE embedding IS NULL"
        ).fetchall()
        if probe and rows:
            # Smoke-test one embedding before committing to the whole DB.
            test = embed((rows[0][1] or "") + "\n" + (rows[0][2] or "")[:512], model)
            if not test:
                return {"db": os.path.basename(db), "error": "embed endpoint unavailable (start ollama with --embeddings + valid model)"}
        if not execute:
            return {"db": os.path.basename(db), "pending": len(rows), "would_write": True}

        pending_batch = []
        for rid, title, content in rows:
            used = _vram_used_mib()
            if used is not None and used > VRAM_CEILING_MIB:
                time.sleep(3)  # GPU hot — let it cool before continuing
            text = ((title or "") + "\n" + (content or ""))[:4000]
            vec = embed(text, model)
            if not vec:
                failed += 1
                continue
            pending_batch.append((sqlite3.Binary(_pack(vec)), rid))
            if len(pending_batch) >= batch:
                _flush(conn, pending_batch, has_ver)
                done += len(pending_batch)
                pending_batch = []
        if pending_batch:
            _flush(conn, pending_batch, has_ver)
            done += len(pending_batch)
    finally:
        conn.close()
    return {"db": os.path.basename(db), "embedded": done, "failed": failed}


def _flush(conn, batch, has_ver, retries=15):
    # Vault DBs are shared with the live MCP; retry on transient lock contention.
    sql = ("UPDATE shards SET embedding=?, schema_version=1 WHERE id=?" if has_ver
           else "UPDATE shards SET embedding=? WHERE id=?")
    for attempt in range(retries):
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(sql, batch)
            conn.execute("COMMIT")
            return
        except sqlite3.OperationalError as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            if "locked" in str(e).lower() and attempt < retries - 1:
                sleep_time = 2 * (1.5 ** attempt)
                print(f"[*] Database locked, retrying in {sleep_time:.1f}s (attempt {attempt+1}/{retries})...")
                time.sleep(sleep_time)
                continue
            raise


def _main(argv=None):
    import argparse, sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Backfill shard embeddings via local ollama (revives semantic recall).")
    ap.add_argument("--vault", default=os.environ.get("NOUGEN_VAULT_DIR"))
    ap.add_argument("--model", default=os.environ.get("NOUGEN_EMBED_MODEL", "nomic-embed-text"))
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args(argv)
    if not args.vault:
        ap.error("--vault or NOUGEN_VAULT_DIR required")

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== embedding backfill [{mode}] model={args.model} vault={args.vault} ===")
    pend = count_pending(args.vault)
    tot_p = sum(p for p, _ in pend.values())
    tot_t = sum(t for _, t in pend.values())
    print(f"pending (embedding IS NULL): {tot_p}/{tot_t} shards across {len(pend)} DBs")
    for db in _vault_dbs(args.vault):
        try:
            res = backfill_db(db, args.model, execute=args.execute, batch=args.batch)
            print(" ", res)
            if res.get("error"):
                print("\nABORT:", res["error"]); return 2
        except Exception as e:
            print(f"  [ERROR] Database {os.path.basename(db)} failed: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
