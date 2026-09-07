"""Unified vector index over the sharded vault — fast semantic recall.

Replaces the O(n) *Python-loop* dot-product scan in core._vector_retrieve (which
deserializes and np.dot's 47k+ blobs and fetches 47k+ SQLite rows on every query)
with: a single memmapped float32 matrix + one BLAS matmul, then top-k row fetches.

Why a matmul and not HNSW: real `hnswlib` needs a C++ toolchain (no Windows wheel
for this interpreter), and `chroma-hnswlib`'s persistence is broken (save writes a
4KB stub, load errors "corrupted"). The matmul path is EXACT (no recall loss),
needs no compiler, persists as a plain .npy, and removes the true bottleneck. The
embeddings are L2-normalized, so M @ q == cosine similarity. A true ANN
(faiss/hnswlib) is a drop-in upgrade behind this same interface once it's
installable / the corpus reaches many millions.

Opt-in via NOUGEN_ANN=1; callers fall back to the linear scan if the index is
absent/stale/unreadable. Build/refresh:  python -m nougen_shards.ann_index build
"""
from __future__ import annotations
import os
import json
import sqlite3
import numpy as np

DIM = int(os.environ.get("NOUGEN_EMBED_DIM", "768"))
_CACHE = {}  # vault_str -> (matrix(np.memmap), labels list, dim) | None


def _paths(base):
    return (os.path.join(str(base), "ann_matrix.npy"),
            os.path.join(str(base), "ann_labels.json"))


def build(vault=None) -> dict:
    """Read every embedding from the 9 DBs into one contiguous float32 matrix and
    persist it (+ a label->(db,id) sidecar). Returns a small report dict."""
    from .core import GLOBAL_DIR, get_db_path, MAX_DB_COUNT

    base = vault if vault is not None else GLOBAL_DIR
    vecs = []
    labels = []  # label_int -> [db_index, shard_id]
    for i in range(1, MAX_DB_COUNT + 1):
        db = get_db_path(i) if vault is None else os.path.join(str(base), f"nougen_shards_{i}.db")
        if not os.path.exists(str(db)):
            continue
        # Read-only + busy timeout so a concurrent backfill/WAL writer can't fail
        # the build; skip (don't crash on) a DB that still errors.
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30.0)
        except sqlite3.Error:
            continue
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            cur = conn.execute("SELECT id, embedding FROM shards WHERE embedding IS NOT NULL")
            for sid, blob in cur:
                if not blob or (isinstance(blob, (bytes, bytearray)) and bytes(blob[:1]) == b"["):
                    continue  # skip legacy JSON embeddings
                arr = np.frombuffer(blob, dtype=np.float32)
                if arr.shape[0] != DIM:
                    continue
                vecs.append(arr)
                labels.append([i, int(sid)])
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    if not vecs:
        return {"status": "empty", "count": 0}

    matrix = np.vstack(vecs).astype(np.float32)  # (N, DIM), C-contiguous
    mat_path, lbl_path = _paths(base)
    np.save(mat_path, matrix)
    with open(lbl_path, "w", encoding="utf-8") as fh:
        json.dump({"dim": DIM, "count": matrix.shape[0], "labels": labels}, fh)
    _CACHE.pop(str(base), None)
    # clean up any legacy hnswlib stub
    for stale in ("ann_index.bin",):
        sp = os.path.join(str(base), stale)
        if os.path.exists(sp):
            try: os.remove(sp)
            except OSError: pass
    return {"status": "ok", "count": matrix.shape[0], "dim": DIM,
            "matrix": mat_path, "labels": lbl_path,
            "size_mb": round(os.path.getsize(mat_path) / 1048576, 1)}


def _load(vault=None):
    """Lazy-load (and cache) the memmapped matrix + labels. Returns
    (matrix, labels, dim) or None -> caller falls back to the linear scan."""
    from .core import GLOBAL_DIR
    base = str(vault if vault is not None else GLOBAL_DIR)
    if base in _CACHE:
        return _CACHE[base]
    mat_path, lbl_path = _paths(base)
    if not (os.path.exists(mat_path) and os.path.exists(lbl_path)):
        _CACHE[base] = None
        return None
    try:
        with open(lbl_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        labels = meta["labels"]
        dim = int(meta.get("dim", DIM))
        matrix = np.load(mat_path, mmap_mode="r")  # memmap: not all in RAM
        if matrix.shape[0] != len(labels):
            _CACHE[base] = None
            return None
        _CACHE[base] = (matrix, labels, dim)
        return _CACHE[base]
    except Exception:
        _CACHE[base] = None
        return None


def query(query_embedding, top_n: int = 200, vault=None):
    """Return up to top_n candidate (db_index, shard_id) tuples ranked by cosine,
    or None if the index is unavailable (caller falls back to linear scan)."""
    loaded = _load(vault)
    if loaded is None:
        return None
    matrix, labels, dim = loaded
    try:
        q = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        if q.shape[0] != dim:
            return None
        scores = matrix @ q                      # (N,) one BLAS matmul == cosine
        k = min(top_n, scores.shape[0])
        # top-k without full sort, then order the k by score desc
        part = np.argpartition(-scores, k - 1)[:k]
        order = part[np.argsort(-scores[part])]
        return [tuple(labels[int(i)]) for i in order]
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        v = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(build(vault=v), indent=2))
    else:
        print("usage: python -m nougen_shards.ann_index build [vault_dir]")
