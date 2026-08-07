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

from .ollama_host import sanitize_ollama_url as _normalize_host  # noqa: E402

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


# Name fragments that identify an embedding-capable model in an ollama tag list.
# Configurable because the roster changes faster than this file does.
EMBED_MODEL_HINTS = [
    h.strip().lower() for h in os.environ.get(
        "NOUGEN_EMBED_MODEL_HINTS", "embed;embedding;bge;gte;minilm;e5").split(";")
    if h.strip()
]
# Logged fallback ONLY — never the source of truth (Rule 0.2).
FALLBACK_EMBED_MODEL = "nomic-embed-text"
_RESOLVED_EMBED_MODEL: Optional[str] = None


def list_models(timeout: int = 5) -> List[str]:
    """Live ollama roster via /api/tags. Empty list when unreachable."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def resolve_embed_model(explicit: Optional[str] = None, timeout: int = 5) -> str:
    """Discover the embedding model at runtime instead of trusting a constant.

    Resolution order (Rule 0.2 — probe before you trust):
      1. explicit argument / NOUGEN_EMBED_MODEL, but only honoured as-is; if the
         pinned tag is absent from the live roster we still return it so the
         operator's intent is never silently overridden — the miss surfaces as
         an embed failure, which is now observable.
      2. live /api/tags probe, first tag matching an embed hint (exact tag,
         including its ':latest' suffix — a name that does not exist on the host
         is the classic stale-hardcode failure).
      3. FALLBACK_EMBED_MODEL constant, as a logged fallback.
    Cached per process; pass explicit= to bypass the cache.
    """
    global _RESOLVED_EMBED_MODEL
    pinned = explicit or os.environ.get("NOUGEN_EMBED_MODEL")
    if pinned:
        return pinned
    if _RESOLVED_EMBED_MODEL:
        return _RESOLVED_EMBED_MODEL
    for name in list_models(timeout=timeout):
        low = name.lower()
        if any(h in low for h in EMBED_MODEL_HINTS):
            _RESOLVED_EMBED_MODEL = name
            return name
    _RESOLVED_EMBED_MODEL = FALLBACK_EMBED_MODEL
    return FALLBACK_EMBED_MODEL


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


def backfill_exclude_globs() -> List[str]:
    """Title globs this backfill must NOT embed.

    Defaults to the SAME canonical backlog globs the ingest and drift lanes use
    (core.DEFAULT_BACKLOG_GLOBS), so "forward-only backlog" means one thing
    across the codebase instead of three. The arXiv backlog is ~18k files on a
    single 8GB-VRAM GPU: embedding it is a deliberate, separately-authorised
    campaign, never a side effect of a repair sweep.
    """
    raw = os.environ.get("NOUGEN_EMBED_BACKFILL_EXCLUDE_GLOBS")
    if raw is None:
        try:
            from .core import DEFAULT_BACKLOG_GLOBS as raw  # canonical source
        except Exception:
            raw = "arxiv_*.md;intelligence_shard_arxiv_*.md"  # logged fallback
    return [g.strip() for g in str(raw).split(";") if g.strip()]


def _scope_sql(globs: List[str]) -> tuple:
    """(where_fragment, params) excluding titles matching any backlog glob."""
    if not globs:
        return "", []
    return " AND " + " AND ".join(["title NOT GLOB ?"] * len(globs)), list(globs)


def count_pending(vault_dir: str, respect_scope: bool = True) -> dict:
    """Per-DB (in_scope_pending, total). Also reports what scope excluded."""
    out = {}
    globs = backfill_exclude_globs() if respect_scope else []
    clause, params = _scope_sql(globs)
    for db in _vault_dbs(vault_dir):
        conn = sqlite3.connect(db)
        try:
            total = conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            all_pending = conn.execute(
                "SELECT COUNT(*) FROM shards WHERE embedding IS NULL").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM shards WHERE embedding IS NULL" + clause,
                params).fetchone()[0]
            out[os.path.basename(db)] = (pending, total)
            out.setdefault("_skipped_out_of_scope", 0)
            out["_skipped_out_of_scope"] += all_pending - pending
        finally:
            conn.close()
    out["_exclude_globs"] = globs
    return out


def backfill_db(db: str, model: str, execute: bool, batch: int = 64, probe: bool = True) -> dict:
    conn = sqlite3.connect(db)
    done = 0
    failed = 0
    try:
        has_ver = _has_col(conn, "shards", "schema_version")
        conn.execute("PRAGMA busy_timeout=30000;")
        clause, params = _scope_sql(backfill_exclude_globs())
        rows = conn.execute(
            "SELECT id, title, content FROM shards WHERE embedding IS NULL" + clause,
            params).fetchall()
        skipped = conn.execute(
            "SELECT COUNT(*) FROM shards WHERE embedding IS NULL").fetchone()[0] - len(rows)
        if probe and rows:
            # Smoke-test one embedding before committing to the whole DB.
            test = embed((rows[0][1] or "") + "\n" + (rows[0][2] or "")[:512], model)
            if not test:
                return {"db": os.path.basename(db), "error": "embed endpoint unavailable (start ollama with --embeddings + valid model)"}
        if not execute:
            return {"db": os.path.basename(db), "pending": len(rows),
                    "skipped_out_of_scope": skipped, "would_write": True}

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
    return {"db": os.path.basename(db), "embedded": done, "failed": failed,
            "skipped_out_of_scope": skipped}


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


def pending_tag() -> str:
    """The marker capture() stamps on a shard it could not embed.

    Resolved env -> core -> logged constant (Rule 0.2) so this repair lane and
    the ingest lane can never disagree about what "pending" is spelled as.
    """
    raw = os.environ.get("NOUGEN_EMBED_PENDING_TAG")
    if raw:
        return raw
    try:
        from .core import EMBED_PENDING_TAG as raw  # canonical source
        return raw
    except Exception:
        return "embedding:pending"  # logged fallback ONLY


def _ingest_parity_text(title: str, content: str) -> str:
    """The SAME text capture() embeds: canonical_content(content), truncated.

    NOT title+content like the bulk sweep — a repair of rows the ingest lane
    dropped must reproduce the ingest recipe, or the repaired vector lands in a
    different place in the space than an identical shard captured today.
    """
    try:
        from .core import canonical_content, EMBED_MAX_CHARS
        return canonical_content(content or "")[:EMBED_MAX_CHARS]
    except Exception:
        cap = int(os.environ.get("NOUGEN_EMBED_MAX_CHARS", "8000"))
        return ((title or "") + "\n" + (content or ""))[:cap]


def _unit_blob(vec: List[float]):
    """float32 BLOB, L2-normalized — byte-identical to what capture() stores."""
    import numpy as np
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return sqlite3.Binary(arr.tobytes())


def _is_healthy_vector(blob, expected_dim: Optional[int] = None) -> bool:
    """True when an existing embedding is already what capture() would write."""
    if not blob:
        return False
    try:
        import numpy as np
        arr = np.frombuffer(blob, dtype=np.float32)
    except Exception:
        return False
    if arr.size == 0 or (expected_dim and arr.size != expected_dim):
        return False
    tol = float(os.environ.get("NOUGEN_EMBED_NORM_TOL", "1e-3"))
    import numpy as np
    return abs(float(np.linalg.norm(arr)) - 1.0) <= tol


def _write_row(conn, blob, tags_json: str, rid: int, retries: int = 15) -> None:
    """Embedding + tags for ONE row, atomically. Touches no other column —
    content/title/timestamp/file_hash are never in this UPDATE."""
    for attempt in range(retries):
        try:
            conn.execute("BEGIN IMMEDIATE")
            if blob is None:
                conn.execute("UPDATE shards SET tags=? WHERE id=?", (tags_json, rid))
            else:
                conn.execute("UPDATE shards SET embedding=?, tags=? WHERE id=?",
                             (blob, tags_json, rid))
            conn.execute("COMMIT")
            return
        except sqlite3.OperationalError as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            if "locked" in str(e).lower() and attempt < retries - 1:
                time.sleep(2 * (1.5 ** attempt))
                continue
            raise


def backfill_pending_tagged(vault_dir: str, model: Optional[str] = None,
                            execute: bool = False, timeout: int = 60) -> List[dict]:
    """Repair ONLY the rows capture() marked `embedding:pending`.

    Deliberately scoped by the marker, never by `embedding IS NULL`: the NULL
    population also contains the forward-only arXiv backlog, which is a
    separately-authorised GPU campaign (see backfill_exclude_globs). A row is
    touched here only because the ingest lane admitted it failed on that row.

    On success the marker is cleared. On ANY failure the marker stays, so the
    row remains visible to the drift detector instead of going quietly dark.
    """
    tag = pending_tag()
    model = resolve_embed_model(model)
    results: List[dict] = []
    for db in _vault_dbs(vault_dir):
        conn = sqlite3.connect(db)
        try:
            conn.execute("PRAGMA busy_timeout=30000;")
            rows = conn.execute(
                "SELECT id, title, content, tags, embedding FROM shards WHERE tags LIKE ?",
                (f"%{tag}%",)).fetchall()
            for rid, title, content, tags_raw, blob in rows:
                try:
                    tag_list = json.loads(tags_raw) if tags_raw else []
                except Exception:
                    tag_list = []
                if tag not in tag_list:
                    continue  # LIKE is a prefilter; membership is the real test
                rec = {"db": os.path.basename(db), "id": rid, "action": None}
                if content is None or not str(content).strip():
                    rec["action"] = "skipped_no_content"  # never fabricate a vector
                    results.append(rec)
                    continue
                if _is_healthy_vector(blob):
                    rec.update(action="tag_only_already_embedded")
                else:
                    vec = embed(_ingest_parity_text(title, content), model, timeout=timeout)
                    if not vec:
                        rec["action"] = "failed_embed_tag_retained"
                        results.append(rec)
                        continue
                    rec.update(action="embedded", dim=len(vec))
                    blob = _unit_blob(vec)
                if not execute:
                    rec["action"] = "dry_run_" + rec["action"]
                    results.append(rec)
                    continue
                remaining = json.dumps([t for t in tag_list if t != tag])
                _write_row(conn, None if rec["action"] == "tag_only_already_embedded" else blob,
                           remaining, rid)
                results.append(rec)
        finally:
            conn.close()
    return results


def _main(argv=None):
    import argparse, sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Backfill shard embeddings via local ollama (revives semantic recall).")
    ap.add_argument("--vault", default=os.environ.get("NOUGEN_VAULT_DIR"))
    # No hardcoded default (Rule 0.2): unset means "ask the live /api/tags
    # roster at run time", which also pins the exact tag instead of a bare name.
    ap.add_argument("--model", default=None)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args(argv)
    if not args.vault:
        ap.error("--vault or NOUGEN_VAULT_DIR required")

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    model = resolve_embed_model(args.model)
    print(f"=== embedding backfill [{mode}] model={model} vault={args.vault} ===")
    pend = count_pending(args.vault)
    # count_pending() also returns scope metadata under underscore-prefixed keys
    # ('_skipped_out_of_scope', '_exclude_globs'); only the per-DB entries are
    # (pending, total) pairs, so the totals must not sweep the whole dict.
    per_db = {k: v for k, v in pend.items() if not k.startswith("_")}
    tot_p = sum(p for p, _ in per_db.values())
    tot_t = sum(t for _, t in per_db.values())
    print(f"pending (embedding IS NULL, in scope): {tot_p}/{tot_t} shards "
          f"across {len(per_db)} DBs")
    print(f"deliberately out of scope (forward-only backlog "
          f"{pend.get('_exclude_globs')}): {pend.get('_skipped_out_of_scope', 0)}")
    for db in _vault_dbs(args.vault):
        try:
            res = backfill_db(db, model, execute=args.execute, batch=args.batch)
            print(" ", res)
            if res.get("error"):
                print("\nABORT:", res["error"]); return 2
        except Exception as e:
            print(f"  [ERROR] Database {os.path.basename(db)} failed: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
