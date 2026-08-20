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
VRAM_CHECK_EVERY = int(os.environ.get("NOUGEN_VRAM_CHECK_EVERY", "64"))  # rows between probes


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


def embed(text: str, model: str, timeout: float = 60.0) -> Optional[List[float]]:
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


def embed_many(texts: List[str], model: str, timeout: float = 180.0) -> Optional[List[List[float]]]:
    """Embed a list of texts in ONE ollama call.

    /api/embed accepts an array for `input` and returns one vector per item, so a
    per-text round-trip is pure overhead. Measured on this vault: one-at-a-time
    ran ~1 embed/sec (~18h for 70k shards) because HTTP round-trip and request
    scheduling dominated the ~10-30ms of actual compute.

    Returns None on failure so the caller can fall back to per-text embedding
    rather than dropping the whole batch.
    """
    body = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/embed", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        vecs = data.get("embeddings")
        if not vecs or len(vecs) != len(texts):
            return None
        return vecs
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


def backfill_db(db: str, model: str, execute: bool, batch: int = 64, probe: bool = True,
                progress: bool = True) -> dict:
    conn = sqlite3.connect(db)
    done = 0
    failed = 0
    try:
        has_ver = _has_col(conn, "shards", "schema_version")
        conn.execute("PRAGMA busy_timeout=15000;")
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

        # VRAM is polled per batch, not per row: nvidia-smi is a subprocess spawn
        # (~50-100ms), and at one spawn per shard the probe costs more wall-clock
        # than the embedding it guards. Interval is env-tunable.
        for start in range(0, len(rows), batch):
            chunk = rows[start:start + batch]
            if (start // max(batch, 1)) % max(VRAM_CHECK_EVERY // max(batch, 1), 1) == 0:
                used = _vram_used_mib()
                if used is not None and used > VRAM_CEILING_MIB:
                    time.sleep(3)  # GPU hot — let it cool before continuing

            texts = [((t or "") + "\n" + (c or ""))[:4000] for _, t, c in chunk]
            vecs = embed_many(texts, model)

            pending_batch = []
            if vecs is None:
                # Batch endpoint failed (oversized payload, transient error) --
                # fall back per text so one bad row cannot drop the whole chunk.
                for (rid, title, content), text in zip(chunk, texts):
                    vec = embed(text, model)
                    if not vec:
                        failed += 1
                        continue
                    pending_batch.append((sqlite3.Binary(_pack(vec)), rid))
            else:
                for (rid, _t, _c), vec in zip(chunk, vecs):
                    if not vec:
                        failed += 1
                        continue
                    pending_batch.append((sqlite3.Binary(_pack(vec)), rid))

            if pending_batch:
                _flush(conn, pending_batch, has_ver)
                done += len(pending_batch)
            if progress and done and (start // max(batch, 1)) % 20 == 0:
                print(f"    {os.path.basename(db)}: {done}/{len(rows)} embedded, {failed} failed", flush=True)
    finally:
        conn.close()
    return {"db": os.path.basename(db), "embedded": done, "failed": failed}


def _flush(conn, batch, has_ver):
    conn.execute("BEGIN")
    if has_ver:
        conn.executemany("UPDATE shards SET embedding=?, schema_version=1 WHERE id=?", batch)
    else:
        conn.executemany("UPDATE shards SET embedding=? WHERE id=?", batch)
    conn.execute("COMMIT")


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
        res = backfill_db(db, args.model, execute=args.execute, batch=args.batch)
        print(" ", res)
        if res.get("error"):
            print("\nABORT:", res["error"]); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
