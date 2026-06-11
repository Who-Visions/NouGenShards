"""
NouGenShards: Advanced Memory-Core Substrate.
Logic: SQLite + FTS5 + BM25 + Trigram (n-gram) + Vector Embeddings + Bayesian Reranking.
Architecture: Reverse Epistemics (Manifesto of Bayesian Orchestration).
"""
# pylint: disable=duplicate-code
import hashlib
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path

# Configuration (Module 10: Integrate Constraints)
MAX_DB_SIZE = 1 * 1024 * 1024 * 1024  # 1GB Safety Limit per DB
MAX_DB_COUNT = 9
GLOBAL_DIR = Path.home() / ".nougen" / "shards"


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


def get_active_db_index() -> int:
    """Finds an available database under the 1GB limit (Module 4: Surface Leverage)."""
    for i in range(1, MAX_DB_COUNT + 1):
        if not is_db_full(i):
            return i
    return MAX_DB_COUNT


def get_connection(index: int):
    """Establishes an SQLite connection with WAL enabled (Module 19: Stabilize Reasoning)."""
    path = get_db_path(index)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(index: int = 1):
    """Initializes the substrate schema (Module 6: Copy Successful Topology)."""
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
            utility_score REAL DEFAULT 1.0, -- Bayesian Prior (Module 20)
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

    # Sync triggers (Module 18: Reconstruct Coherence)
    cursor.execute("DROP TRIGGER IF EXISTS shards_ai")
    cursor.execute("""
        CREATE TRIGGER shards_ai AFTER INSERT ON shards BEGIN
            INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END;
    """)

    conn.commit()
    conn.close()


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
            tags: list = None, embedding: list = None) -> bool:
    """Saves a unit of experience (Module 5: Extract Invariants)."""
    fhash = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()

    # Global Deduplication (The Invariant Check)
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            row = conn.execute("SELECT id FROM shards WHERE file_hash = ?", (fhash,)).fetchone()
            if row:
                conn.close()
                return False
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    target_idx = get_active_db_index()
    init_db(target_idx)

    emb_blob = sqlite3.Binary(json.dumps(embedding).encode()) if embedding else None
    tags_str = json.dumps(tags or [])
    timestamp = datetime.utcnow().isoformat() + "Z"

    conn = get_connection(target_idx)
    try:
        cursor = conn.execute("""
            INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, event_type, title, content, tags_str, fhash, emb_blob))
        conn.commit()

        # Log CREATED event
        from . import history # pylint: disable=import-outside-toplevel
        history.log_event(cursor.lastrowid, target_idx, "CREATED", new_score=1.0)

        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


# Bayesian Ranking Config (Module 20)
WEIGHT_BM25 = 0.4
WEIGHT_SEMANTIC = 0.6
WEIGHT_LIKELIHOOD = 0.7
WEIGHT_PRIOR = 0.3

def _process_fts_result(row, db_index, query_embedding):
    """Helper to process a single FTS result with Bayesian math."""
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

    # 3. Bayesian Posterior = Likelihood * Prior (utility_score)
    item["final_score"] = (likelihood * WEIGHT_LIKELIHOOD) + (item["utility_score"] * WEIGHT_PRIOR)
    return item


def retrieve(query: str, limit: int = 3, query_embedding: list = None) -> list:
    """
    Advanced Retrieval and Bayesian Orchestration (Module 21).
    Synthesizes BM25 (Adjacency) and Semantic (Latent) signals.
    """
    all_results = []
    from . import history # pylint: disable=import-outside-toplevel
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            fts_worked = False
            if len(query) >= 2:
                try:
                    cursor = conn.execute("""
                        SELECT s.id, s.title, s.content, s.utility_score, s.embedding,
                               s.tags, bm25(f) as bm25_score
                        FROM shards s JOIN shards_fts f ON s.id = f.rowid
                        WHERE shards_fts MATCH ?
                        ORDER BY bm25_score ASC LIMIT 20
                    """, (query,))
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
                like_query = f"%{query}%"
                cursor = conn.execute("""
                    SELECT id, title, content, utility_score, embedding, tags
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
    """Bayesian Inversion: Updates the Prior (utility_score) based on outcome evidence."""
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


def compile_recall_packet(shards: list) -> str:
    """Synthesis of retrieved experience into a coherent context packet (Module 18)."""
    if not shards:
        return "<!-- NO RELEVANT MEMORY RECALLED -->"
    output = ["=== NOUGENSHARDS RECALL PACKET [BAYESIAN SYNTHESIS] ==="]
    for s in shards:
        output.append(f"--- RECORD #{s['id']} [Posterior: {s['final_score']:.2f}] ---")
        output.append(f"Title: {s['title']}\n{s['content']}\n")
    return "\n".join(output)
