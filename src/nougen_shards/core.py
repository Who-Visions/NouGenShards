"""
NouGenShards: Advanced Memory-Core Substrate.
Substrate: SQLite + FTS5 + BM25 + Trigram (n-gram) + Vector Embeddings + Bayesian Reranking.
"""
# pylint: disable=duplicate-code
from pathlib import Path
import os
import sqlite3
import hashlib
import json
import math
from datetime import datetime
import sys

# Configuration
MAX_DB_SIZE = 1 * 1024 * 1024 * 1024  # 1GB protection
MAX_DB_COUNT = 9
GLOBAL_DIR = Path.home() / ".nougen" / "shards"

def get_db_path(index: int) -> Path:
    local_name = f"shards_{index}.db" if index > 1 else "shards.db"
    local_path = Path(local_name)
    if local_path.exists(): return local_path
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    return GLOBAL_DIR / f"nougen_shards_{index}.db"

def get_connection(index: int):
    path = get_db_path(index)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db(index: int = 1):
    """Initializes the advanced substrate schema."""
    conn = get_connection(index)
    cursor = conn.cursor()

    # 1. Main Shards Table with Vector Storage
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            utility_score REAL DEFAULT 1.0, -- Bayesian Prior
            access_count INTEGER DEFAULT 0,
            file_hash TEXT UNIQUE NOT NULL,
            embedding BLOB -- Vector Substrate
        );
    """)

    # 2. FTS5 with Trigram (n-gram) Tokenizer
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

    # 3. Synchronization Triggers
    cursor.execute("DROP TRIGGER IF EXISTS shards_ai")
    cursor.execute("""
        CREATE TRIGGER shards_ai AFTER INSERT ON shards BEGIN
            INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END;
    """)

    conn.commit()
    conn.close()

def cosine_similarity(v1: list, v2: list) -> float:
    """Calculates similarity between two vectors."""
    if not v1 or not v2 or len(v1) != len(v2): return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    magnitude1 = math.sqrt(sum(a * a for a in v1))
    magnitude2 = math.sqrt(sum(b * b for b in v2))
    if not magnitude1 or not magnitude2: return 0.0
    return dot_product / (magnitude1 * magnitude2)

def capture(event_type: str, title: str, content: str, tags: list = None, embedding: list = None) -> bool:
    """Stores experience into the substrate with optional vector embedding."""
    fhash = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()
    target_idx = (int(fhash, 16) % MAX_DB_COUNT) + 1
    init_db(target_idx)
    
    emb_blob = sqlite3.Binary(json.dumps(embedding).encode()) if embedding else None
    tags_str = json.dumps(tags or [])
    timestamp = datetime.utcnow().isoformat() + "Z"

    conn = get_connection(target_idx)
    try:
        conn.execute("""
            INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, event_type, title, content, tags_str, fhash, emb_blob))
        conn.commit()
        return True
    except sqlite3.IntegrityError: return False
    finally: conn.close()

def retrieve(query: str, limit: int = 3, query_embedding: list = None) -> list:
    """
    Advanced Retrieval with Bayesian Reranking.
    """
    all_results = []
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists(): continue
        conn = get_connection(i)
        try:
            # BM25 Keyword Search
            cursor = conn.execute("""
                SELECT s.id, s.title, s.content, s.utility_score, s.embedding, s.tags, bm25(f) as bm25_score
                FROM shards s JOIN shards_fts f ON s.id = f.rowid
                WHERE shards_fts MATCH ?
                ORDER BY bm25_score ASC LIMIT 20
            """, (query,))
            
            for row in cursor:
                item = dict(row)
                item["_db_index"] = i
                
                semantic_score = 0.0
                if query_embedding and item["embedding"]:
                    stored_v = json.loads(item["embedding"].decode())
                    semantic_score = cosine_similarity(query_embedding, stored_v)
                
                # Normalize BM25
                norm_bm25 = 1.0 / (1.0 + abs(item["bm25_score"]))
                relevance = (norm_bm25 * 0.4) + (semantic_score * 0.6)
                
                # Bayesian Update
                item["final_score"] = (relevance * 0.7) + (item["utility_score"] * 0.3)
                all_results.append(item)
        except sqlite3.OperationalError:
            # Fallback to LIKE
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
                item["bm25_score"] = 0.0
                item["final_score"] = item["utility_score"] * 0.5 # Weak relevance
                all_results.append(item)
        finally:
            conn.close()

    all_results.sort(key=lambda x: x["final_score"], reverse=True)
    return all_results[:limit]

def mark_shard(shard_id: int, worked: bool):
    """Updates the utility score (The Bayesian Prior)."""
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists(): continue
        conn = get_connection(i)
        row = conn.execute("SELECT id FROM shards WHERE id = ?", (shard_id,)).fetchone()
        if row:
            adjustment = 1.0 if worked else -0.5
            conn.execute("UPDATE shards SET utility_score = utility_score + ? WHERE id = ?", (adjustment, shard_id))
            conn.commit(); conn.close(); return True
        conn.close()
    return False

def compile_recall_packet(shards: list) -> str:
    if not shards: return "<!-- NO RELEVANT MEMORY RECALLED -->"
    output = ["=== NOUGENSHARDS ADVANCED RECALL ==="]
    for s in shards:
        output.append(f"--- RECORD #{s['id']} [Score: {s['final_score']:.2f}] ---")
        output.append(f"Title: {s['title']}\n{s['content']}\n")
    return "\n".join(output)
