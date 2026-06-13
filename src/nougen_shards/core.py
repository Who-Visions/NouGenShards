"""
NouGenShards: Advanced Memory-Core Substrate.
Logic: SQLite + FTS5 + BM25 + Trigram (n-gram) + Vector Embeddings + Weighted Relevance Reranking.
Architecture: weighted multi-signal relevance blend (BM25 + semantic + usefulness prior).
"""
# pylint: disable=duplicate-code
import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Configuration (Module 10: Integrate Constraints)
MAX_DB_SIZE = 1 * 1024 * 1024 * 1024  # 1GB Safety Limit per DB
MAX_DB_COUNT = 9

_vault_dir = os.environ.get("NOUGEN_VAULT_DIR")
if not _vault_dir:
    local_vault = Path(".vault")
    if local_vault.exists() and local_vault.is_dir():
        _vault_dir = str(local_vault)
    else:
        _vault_dir = str(Path.home() / ".nougen" / "shards")

GLOBAL_DIR = Path(_vault_dir)



def get_db_path(index: int) -> Path:
    """Returns the path for a specific database index (Module 11: Transform Architecture)."""
    local_name = f"shards_{index}.db" if index > 1 else "shards.db"
    local_path = Path(local_name)
    if local_path.exists():
        return local_path

    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    return GLOBAL_DIR / f"nougen_shards_{index}.db"


def is_db_full(index: int) -> bool:
    """Checks if a database file has reached its 1GB constraint."""
    path = get_db_path(index)
    if not path.exists():
        return False
    try:
        return path.stat().st_size >= MAX_DB_SIZE
    except OSError:
        return True


def get_routing_index(fhash: str) -> int:
    """
    Module 4: Surface Leverage (Intelligent Scaling).
    Deterministic Hash-Based Routing ensures O(1) deduplication and uniform distribution.
    Distributes load evenly across the 9-DB cluster.
    """
    return (int(fhash, 16) % MAX_DB_COUNT) + 1


def get_write_index(fhash: str) -> int:
    """
    Resolves the destination DB for a new shard (Module 4: Surface Leverage).
    Routes deterministically by content hash for uniform O(1) distribution across
    the 9-DB cluster, then skips any database that has hit its 1GB constraint.
    """
    start = get_routing_index(fhash)
    for offset in range(MAX_DB_COUNT):
        idx = ((start - 1 + offset) % MAX_DB_COUNT) + 1
        if not is_db_full(idx):
            return idx
    return start  # All databases full; fall back to the hash target.


def get_active_db_index() -> int:
    """Legacy alias, preserved for cli.py compatibility."""
    return get_routing_index(hashlib.md5(b"default").hexdigest())


def get_connection(index: int):
    """Establishes an SQLite connection with WAL enabled (Module 19: Stabilize Reasoning)."""
    path = get_db_path(index)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


_INITIALIZED_DBS = set()


def init_db(index: int = 1):
    """Initializes the substrate schema (Module 6: Copy Successful Topology).

    Idempotent, but re-running CREATE TABLE / DROP+CREATE TRIGGER on every
    capture dominates bulk-ingestion cost — so each (vault, index) pair is
    initialized once per process. Keyed by vault dir because tests and tools
    repoint NOUGEN_VAULT_DIR/GLOBAL_DIR mid-process.
    """
    key = (str(GLOBAL_DIR), index)
    if key in _INITIALIZED_DBS:
        return
    conn = get_connection(index)
    cursor = conn.cursor()

    # Main table for shards (Module 3: Deep Grep Latent Structure)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            utility_score REAL DEFAULT 1.0, -- usefulness prior: weight term in the relevance blend (Module 20)
            access_count INTEGER DEFAULT 0,
            file_hash TEXT UNIQUE NOT NULL
        );
    """)

    # Add embedding column if missing (Module 11: Transform Architecture)
    try:
        cursor.execute("ALTER TABLE shards ADD COLUMN embedding BLOB;")
    except sqlite3.OperationalError:
        pass

    # FTS5 with Trigram for fuzzy recall (Module 1: Metamers)
    try:
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS shards_fts USING fts5(
                title,
                content,
                content='shards',
                content_rowid='id',
                tokenize='trigram'
            );
        """)
    except sqlite3.OperationalError:
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS shards_fts USING fts5(
                title,
                content,
                content='shards',
                content_rowid='id'
            );
        """)

    # Sync triggers (Module 18: Reconstruct Coherence).
    # The FTS index must stay coherent on every write, not just inserts. Without
    # the delete/update triggers, edited or removed shards leave stale rows that
    # keep matching searches. External-content FTS5 needs the special 'delete'
    # command rows to retract a row before re-indexing it.
    cursor.execute("DROP TRIGGER IF EXISTS shards_ai")
    cursor.execute("DROP TRIGGER IF EXISTS shards_ad")
    cursor.execute("DROP TRIGGER IF EXISTS shards_au")
    cursor.execute("""
        CREATE TRIGGER shards_ai AFTER INSERT ON shards BEGIN
            INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END;
    """)
    cursor.execute("""
        CREATE TRIGGER shards_ad AFTER DELETE ON shards BEGIN
            INSERT INTO shards_fts(shards_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END;
    """)
    cursor.execute("""
        CREATE TRIGGER shards_au AFTER UPDATE ON shards BEGIN
            INSERT INTO shards_fts(shards_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END;
    """)

    conn.commit()
    conn.close()
    _INITIALIZED_DBS.add(key)


def get_dedup_path():
    """Path to the central dedup index (Module 12: Refactor Complexity)."""
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    return GLOBAL_DIR / "dedup_index.db"


def _get_dedup_connection():
    """
    Connection to the central file_hash -> db_index map that makes global
    deduplication O(1): one indexed lookup instead of opening all 9 cluster
    databases per capture. The per-DB UNIQUE(file_hash) constraint remains
    the authority; this index is a router/cache in front of it.
    """
    conn = sqlite3.connect(str(get_dedup_path()), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hashes (
            file_hash TEXT PRIMARY KEY,
            db_index INTEGER NOT NULL
        ) WITHOUT ROWID;
    """)
    return conn


def _ensure_dedup_index(conn) -> None:
    """
    Lazy one-time backfill: an empty index alongside populated shard DBs
    means we predate the index (or it was deleted) — rebuild it with one
    scan so legacy hashes in overflow DBs keep deduplicating correctly.
    """
    if conn.execute("SELECT 1 FROM hashes LIMIT 1").fetchone():
        return
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        src = get_connection(i)
        try:
            rows = src.execute("SELECT file_hash FROM shards").fetchall()
            conn.executemany(
                "INSERT OR IGNORE INTO hashes (file_hash, db_index) VALUES (?, ?)",
                [(r["file_hash"], i) for r in rows])
        finally:
            src.close()
    conn.commit()


def cosine_similarity(vec1: list, vec2: list) -> float:
    """Measures semantic alignment (Module 7: Transpose Patterns)."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))
    if not mag1 or not mag2:
        return 0.0
    return dot_product / (mag1 * mag2)


def capture(event_type: str, title: str, content: str,
            tags: Optional[List[str]] = None, embedding: Optional[List[float]] = None) -> bool:
    """Saves a unit of experience (Module 5: Extract Invariants)."""
    fhash = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()

    # Global Deduplication (Module 12): one indexed lookup in the central
    # hash index — O(1) — instead of scanning all 9 cluster databases.
    # The index also covers legacy hashes living in overflow DBs (a shard's
    # home shifts off its routing target when that DB was full at write time).
    dconn = _get_dedup_connection()
    try:
        _ensure_dedup_index(dconn)
        if dconn.execute("SELECT 1 FROM hashes WHERE file_hash = ?",
                         (fhash,)).fetchone():
            return False

        target_idx = get_write_index(fhash)
        init_db(target_idx)

        emb_blob = sqlite3.Binary(json.dumps(embedding).encode()) if embedding else None
        tags_str = json.dumps(tags or [])
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        conn = get_connection(target_idx)
        try:
            cursor = conn.execute("""
                INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, event_type, title, content, tags_str, fhash, emb_blob))
            conn.commit()

            # Log CREATED event
            from . import history # pylint: disable=import-outside-toplevel
            history.log_event(cursor.lastrowid or 0, target_idx, "CREATED", new_score=1.0)
        except sqlite3.IntegrityError:
            # Target DB already holds the hash (index was stale) — repair the
            # index so the next lookup short-circuits without touching shards.
            dconn.execute(
                "INSERT OR IGNORE INTO hashes (file_hash, db_index) VALUES (?, ?)",
                (fhash, target_idx))
            dconn.commit()
            return False
        finally:
            conn.close()

        dconn.execute(
            "INSERT OR IGNORE INTO hashes (file_hash, db_index) VALUES (?, ?)",
            (fhash, target_idx))
        dconn.commit()
        return True
    finally:
        dconn.close()


# Relevance blend weights (Module 20)
WEIGHT_BM25 = 0.4
WEIGHT_SEMANTIC = 0.6
WEIGHT_LIKELIHOOD = 0.7
WEIGHT_PRIOR = 0.3

def _process_fts_result(row, db_index, query_embedding):
    """Helper to score a single FTS result via the weighted relevance blend."""
    item = dict(row)
    item["_db_index"] = db_index
    # 1. Likelihood Part A: BM25 (The Adjacency Score)
    norm_bm25 = 1.0 / (1.0 + abs(item["bm25_score"]))

    # 2. Likelihood Part B: Semantic (The Latent Score)
    sem_score = 0.0
    if query_embedding and item["embedding"]:
        sem_score = cosine_similarity(query_embedding, json.loads(item["embedding"].decode()))

    # Synthesize Coherent Likelihood (Module 9)
    likelihood = (norm_bm25 * WEIGHT_BM25) + (sem_score * WEIGHT_SEMANTIC)

    # 3. Final relevance: a weighted blend of the likelihood signal and the
    #    shard's usefulness prior. This is a linear combination of two scores,
    #    not a true Bayesian posterior (no normalization over a likelihood model).
    item["final_score"] = (likelihood * WEIGHT_LIKELIHOOD) + (item["utility_score"] * WEIGHT_PRIOR)
    return item


def _build_fts_match_query(query: str) -> Optional[str]:
    """
    Build a safe FTS5 MATCH expression from arbitrary user input.

    Every word is treated as a literal phrase: each token is double-quoted (any
    embedded quote doubled, per FTS5 escaping), so query text can never be parsed
    as FTS5 operators (AND/OR/NOT/NEAR/*, bare quotes, parentheses). Without this,
    inputs like `c++`, `foo"bar`, or a lone `AND` raise OperationalError and the
    search silently degrades to a LIKE substring scan. Tokens shorter than 3 chars
    are dropped because the trigram tokenizer cannot index them. Returns None when
    nothing matchable remains (caller then uses the LIKE fallback).
    """
    tokens = [t for t in query.split() if len(t) >= 3]
    if not tokens:
        return None
    return " ".join('"' + t.replace('"', '""') + '"' for t in tokens)


def retrieve(query: str, limit: int = 3, query_embedding: Optional[List[float]] = None) -> list:
    """
    Advanced Retrieval (Module 21): weighted blend of BM25 (Adjacency) and
    Semantic (Latent) signals with the shard's usefulness prior.
    """
    all_results = []
    from . import history # pylint: disable=import-outside-toplevel
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            fts_worked = False
            fts_query = _build_fts_match_query(query)
            if fts_query is not None:
                try:
                    cursor = conn.execute("""
                        SELECT s.id, s.timestamp, s.title, s.content, s.utility_score,
                               s.embedding, s.tags, bm25(shards_fts) as bm25_score
                        FROM shards s JOIN shards_fts ON s.id = shards_fts.rowid
                        WHERE shards_fts MATCH ?
                        ORDER BY bm25_score ASC LIMIT 20
                    """, (fts_query,))
                    res = cursor.fetchall()
                    if res:
                        for row in res:
                            # Log ACCESSED event
                            history.log_event(row["id"], i, "ACCESSED")
                            all_results.append(_process_fts_result(row, i, query_embedding))
                        fts_worked = True
                except sqlite3.OperationalError:
                    pass

            if not fts_worked:
                # Fallback to LIKE (Module 1: Resolving Metamers for small query strings)
                # Audit visibility: Log fallback event.
                from . import history # pylint: disable=import-outside-toplevel
                history.log_event(0, i, "SEARCH_FALLBACK", metadata={"query": query})
                
                like_query = f"%{query}%"
                cursor = conn.execute("""
                    SELECT id, timestamp, title, content, utility_score, embedding, tags
                    FROM shards
                    WHERE title LIKE ? OR content LIKE ?
                    ORDER BY utility_score DESC LIMIT 20
                """, (like_query, like_query))
                for row in cursor:
                    item = dict(row)
                    item["_db_index"] = i
                    history.log_event(item["id"], i, "ACCESSED")
                    sem_score = 0.0
                    if query_embedding and item["embedding"]:
                        sem_score = cosine_similarity(
                            query_embedding, json.loads(item["embedding"].decode()))
                    likelihood = sem_score if query_embedding else 0.5
                    item["final_score"] = (likelihood * 0.5) + (item["utility_score"] * 0.5)
                    all_results.append(item)
        finally:
            conn.close()

    all_results.sort(key=lambda x: x["final_score"], reverse=True)
    return all_results[:limit]


def get_shard_by_id(shard_id: int, db_index: int):
    """Retrieves a specific shard by ID from a specific DB index."""
    if not get_db_path(db_index).exists(): return None
    conn = get_connection(db_index)
    try:
        row = conn.execute("SELECT * FROM shards WHERE id = ?", (shard_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def mark_shard(shard_id: int, worked: bool):
    """Updates the usefulness prior (utility_score) from outcome evidence (helpful / not)."""
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        row = conn.execute("SELECT id, utility_score FROM shards WHERE id = ?", (shard_id,)).fetchone()
        if row:
            old_score = row["utility_score"]
            val = 1.0 if worked else -0.5
            new_score = old_score + val
            conn.execute("UPDATE shards SET utility_score = ? WHERE id = ?", (new_score, shard_id))
            conn.commit()
            conn.close()

            # Log UTILITY_CHANGE event
            from . import history # pylint: disable=import-outside-toplevel
            history.log_event(shard_id, i, "UTILITY_CHANGE", old_score=old_score, new_score=new_score)

            return True
        conn.close()
    return False


def decay_utility_scores(factor: float = 0.95):
    """
    Module 19: Stabilize Reasoning.
    Applies a decay factor to all utility scores to prevent stale dominance.
    """
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            conn.execute("UPDATE shards SET utility_score = utility_score * ?", (factor,))
            conn.commit()
        finally:
            conn.close()
    return True


def format_shard_when(timestamp: Optional[str]) -> str:
    """
    Render a stored UTC ISO timestamp as local wall-clock time plus relative age,
    so recalled memories are grounded against *now* (e.g.
    '2026-06-12 04:28 PM EDT (2h ago)'). Returns 'unknown time' for missing or
    unparseable values (legacy shards predating the timestamp surfacing).
    """
    if not timestamp:
        return "unknown time"
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if dt.tzinfo is None:  # legacy naive rows were written as UTC
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return "unknown time"
    local = dt.astimezone()
    age = datetime.now(timezone.utc) - dt
    secs = age.total_seconds()
    if secs < 0:
        rel = "in the future?"
    elif secs < 3600:
        rel = f"{int(secs // 60)}m ago"
    elif secs < 86400:
        rel = f"{int(secs // 3600)}h ago"
    else:
        rel = f"{int(secs // 86400)}d ago"
    return f"{local.strftime('%Y-%m-%d %I:%M %p %Z').strip()} ({rel})"


def compile_recall_packet(shards: list) -> str:
    """Synthesis of retrieved experience into a coherent context packet (Module 18)."""
    if not shards:
        return "<!-- NO RELEVANT MEMORY RECALLED -->"
    output = ["=== NOUGENSHARDS RECALL PACKET [BAYESIAN SYNTHESIS] ==="]
    for s in shards:
        output.append(f"--- RECORD #{s['id']} [Score: {s['final_score']:.2f}] ---")
        output.append(f"When: {format_shard_when(s.get('timestamp'))}")
        output.append(f"Title: {s['title']}\n{s['content']}\n")
    # "Anghkooey" — "remember" (FROM). Spoken only when recall succeeds:
    # the engine's acknowledgment that a past life was actually surfaced.
    output.append("Anghkooey — NouGenShards remembers.")
    return "\n".join(output)
