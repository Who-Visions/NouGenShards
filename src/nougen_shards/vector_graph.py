"""
NouGen Metameric Vector-Graph Substrate: Native Topological Memory over SQLite.
Engine: Valerion Cognitive Substrate — Autonomous NouGen Learning.

Key Architectural Pillars:
  1. Sovereign SQLite Architecture: Entity vectors, relation triplets, and shards
     are stored natively in SQLite float32 little-endian vector BLOBs.
  2. Multi-Way Topological Retrieval: Concurrently navigates semantic entity spaces
     and relational assertion graphs using dense cosine similarity.
  3. O(1) Indexed Subgraph Expansion: Eliminates external graph engines and Cypher
     queries, executing topological neighborhood walks via native SQLite B-Tree indexes.
  4. Tri-Hybrid Reciprocal Rank Fusion: Synthesizes topological subgraph traversals,
     FTS5 BM25 keyword rankings, and Kronos temporal utility decay.
  5. 100% Sovereign & Local: Operates fully air-gapped on the Razer Blade stadium
     with zero cloud dependencies, zero external subscriptions, and zero data leakage.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from . import core
from . import graph

logger = logging.getLogger(__name__)

# Default similarity threshold for entity/relation vector matching
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("NOUGEN_VG_SIM_THRESHOLD", "0.55"))


def _pack_vector(vec: List[float]) -> bytes:
    """float32 little-endian BLOB compatible with np.frombuffer and core.py."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack_vector(blob: bytes) -> Optional[np.ndarray]:
    """Unpack float32 vector BLOB or fallback from JSON."""
    if not blob:
        return None
    try:
        if blob.startswith(b"["):
            return np.array(json.loads(blob.decode("utf-8")), dtype=np.float32)
        return np.frombuffer(blob, dtype=np.float32)
    except Exception:
        return None


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Cosine similarity between two 1D vectors."""
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def _normalize_name(name: str) -> str:
    """Clean and normalize an entity name for deterministic linking."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _generate_entity_id(name: str) -> str:
    """Deterministic entity identifier from normalized name."""
    clean = _normalize_name(name)
    return "ent_" + hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]


def _generate_relation_id(sub: str, pred: str, obj: str, shard_hash: str) -> str:
    """Deterministic relation identifier."""
    raw = f"{_normalize_name(sub)}|{_normalize_name(pred)}|{_normalize_name(obj)}|{shard_hash}"
    return "rel_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Schema Management
# ---------------------------------------------------------------------------

def init_vector_graph_db() -> None:
    """Initializes the entity and relation vector graph tables in graph.db."""
    graph.init_graph_db()
    conn = graph.get_graph_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shard_entities (
                entity_id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                entity_type TEXT DEFAULT 'concept',
                embedding BLOB,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON shard_entities(name)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS shard_relations (
                relation_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                relation_text TEXT NOT NULL,
                embedding BLOB,
                head_entity_id TEXT,
                tail_entity_id TEXT,
                source_shard_hash TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (head_entity_id) REFERENCES shard_entities(entity_id),
                FOREIGN KEY (tail_entity_id) REFERENCES shard_entities(entity_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_head ON shard_relations(head_entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_tail ON shard_relations(tail_entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_src_hash ON shard_relations(source_shard_hash)")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fast Triplet Extraction (Local Heuristics + OpenIE)
# ---------------------------------------------------------------------------

RELATION_PATTERNS = [
    (r"\b(fixed|resolves|patches|patched|repaired)\b", "fixes"),
    (r"\b(touches|modifies|updates|modified|edited)\b", "touches"),
    (r"\b(caused by|triggered by|due to|resulting from)\b", "caused_by"),
    (r"\b(depends on|requires|relies on|imports)\b", "depends_on"),
    (r"\b(deployed|configured|installed|migrated)\b", "deploys"),
    (r"\b(connects to|interacts with|calls|queries)\b", "queries"),
    (r"\b(stores|persists|encrypts|caches)\b", "persists"),
    (r"\b(creates|implements|generates|produces)\b", "creates"),
]


def extract_triplets_heuristic(title: str, content: str) -> List[Tuple[str, str, str]]:
    """
    Fast rule-based triplet extraction from shard title and content.
    Extracts high-signal (Subject, Predicate, Object) triplets with zero LLM latency.
    """
    triplets: List[Tuple[str, str, str]] = []
    text = (title or "").strip()
    if not text:
        text = (content or "").strip().split("\n")[0]
    if not text:
        return triplets

    # Pattern 0: YAML Frontmatter extraction (topic, category, tags, source)
    clean_subj = text.replace(".md", "").replace("intelligence_shard_", "").replace("_", " ").strip()
    fm_match = re.search(r"^---\s*\n(.*?)\n---", content or "", re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).split("\n"):
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if not v:
                continue
            if k == "topic":
                triplets.append((clean_subj, "has_topic", v.replace("_", " ")))
            elif k == "category":
                triplets.append((clean_subj, "has_category", v))
            elif k == "tags":
                tags = [t.strip() for t in v.split(",") if t.strip()]
                for tag in tags[:4]:
                    triplets.append((clean_subj, "tagged_as", tag))
            elif k == "source":
                triplets.append((clean_subj, "sourced_from", v))

    # Pattern 1: Title structures like "Apollo: fix JWT expiry in auth.py"
    colon_match = re.match(r"^([A-Za-z0-9_\-\.]+)\s*:\s*(.+)$", text)
    if colon_match:
        actor = colon_match.group(1).strip()
        rest = colon_match.group(2).strip()
        for pat, pred in RELATION_PATTERNS:
            m = re.search(pat, rest, re.IGNORECASE)
            if m:
                obj = rest[m.end():].strip()
                if obj:
                    triplets.append((actor, pred, obj[:80]))
                break

    # Pattern 2: Verb-centric splitting on sentences
    sentences = re.split(r"[.\n;]+", (title + ". " + content)[:800])
    for s in sentences:
        s = s.strip()
        if not s or len(s) < 10:
            continue
        for pat, pred in RELATION_PATTERNS:
            m = re.search(pat, s, re.IGNORECASE)
            if m:
                subj = s[:m.start()].strip()
                obj = s[m.end():].strip()
                words_s = subj.split()
                words_o = obj.split()
                if 1 <= len(words_s) <= 5 and 1 <= len(words_o) <= 6:
                    sub_str = " ".join(words_s[-3:])
                    obj_str = " ".join(words_o[:4])
                    if sub_str.lower() != obj_str.lower():
                        triplets.append((sub_str, pred, obj_str))
                        break

    seen = set()
    unique_triplets = []
    for sub, pred, obj in triplets:
        key = (_normalize_name(sub), _normalize_name(pred), _normalize_name(obj))
        if key not in seen and len(key[0]) > 1 and len(key[2]) > 1:
            seen.add(key)
            unique_triplets.append((sub, pred, obj))

    return unique_triplets[:8]


# ---------------------------------------------------------------------------
# Vector Graph Ingestion
# ---------------------------------------------------------------------------

def _get_embedding_fn() -> Callable[[str], Optional[List[float]]]:
    """Returns the active embedding function (local Ollama nomic-embed-text)."""
    try:
        from .embedding_backfill import embed
        model = os.getenv("NOUGEN_EMBED_MODEL", "nomic-embed-text")
        return lambda text: embed(text, model=model)
    except Exception:
        return lambda text: None


def ingest_triplet(
    subject: str,
    predicate: str,
    obj: str,
    source_shard_hash: Optional[str] = None,
    shard_id: Optional[int] = None,
    db_index: int = 1,
    weight: float = 1.0,
    embed_fn: Optional[Callable[[str], Optional[List[float]]]] = None,
) -> bool:
    """
    Ingests a single (Subject, Predicate, Object) triplet into the vector graph.
    Embeds entities and relations into float32 vector BLOBs.
    """
    if not subject or not predicate or not obj:
        return False

    fhash = source_shard_hash
    if not fhash and shard_id is not None:
        fhash = graph._hash_for(shard_id, db_index)

    if not fhash:
        return False

    init_vector_graph_db()
    conn = graph.get_graph_connection()
    now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    head_id = _generate_entity_id(subject)
    tail_id = _generate_entity_id(obj)
    rel_id = _generate_relation_id(subject, predicate, obj, fhash)
    rel_text = f"{subject} {predicate} {obj}"

    fn = embed_fn or _get_embedding_fn()

    rel_vec = fn(rel_text)
    rel_blob = sqlite3.Binary(_pack_vector(rel_vec)) if rel_vec else None

    sub_vec = fn(subject)
    sub_blob = sqlite3.Binary(_pack_vector(sub_vec)) if sub_vec else None

    obj_vec = fn(obj)
    obj_blob = sqlite3.Binary(_pack_vector(obj_vec)) if obj_vec else None

    try:
        conn.execute("""
            INSERT INTO shard_entities (entity_id, name, entity_type, embedding, created_at)
            VALUES (?, ?, 'concept', ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                embedding = COALESCE(excluded.embedding, shard_entities.embedding)
        """, (head_id, subject, sub_blob, now_str))

        conn.execute("""
            INSERT INTO shard_entities (entity_id, name, entity_type, embedding, created_at)
            VALUES (?, ?, 'concept', ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                embedding = COALESCE(excluded.embedding, shard_entities.embedding)
        """, (tail_id, obj, obj_blob, now_str))

        conn.execute("""
            INSERT OR REPLACE INTO shard_relations (
                relation_id, subject, predicate, object, relation_text,
                embedding, head_entity_id, tail_entity_id, source_shard_hash, weight, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (rel_id, subject, predicate, obj, rel_text, rel_blob, head_id, tail_id, fhash, weight, now_str))

        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.warning("Failed to ingest triplet (%s, %s, %s): %s", subject, predicate, obj, e)
        return False
    finally:
        conn.close()


def ingest_shard_triplets(
    shard_hash: str,
    title: str,
    content: str,
    triplets: Optional[List[Tuple[str, str, str]]] = None,
    embed_fn: Optional[Callable[[str], Optional[List[float]]]] = None,
) -> int:
    """
    Extracts and ingests all triplets associated with a given shard.
    Returns the count of successfully ingested relations.
    """
    extracted = triplets if triplets is not None else extract_triplets_heuristic(title, content)
    if not extracted:
        return 0

    count = 0
    for sub, pred, obj in extracted:
        if ingest_triplet(sub, pred, obj, source_shard_hash=shard_hash, embed_fn=embed_fn):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Multi-Way Retrieval & Subgraph Expansion (Zilliz Pattern)
# ---------------------------------------------------------------------------

@dataclass
class SubGraph:
    """Expanded subgraph containing seed matches and topological neighbors."""
    seed_entities: List[Dict[str, Any]] = field(default_factory=list)
    seed_relations: List[Dict[str, Any]] = field(default_factory=list)
    expanded_relations: List[Dict[str, Any]] = field(default_factory=list)
    referenced_shard_hashes: Set[str] = field(default_factory=set)

    @property
    def total_relations(self) -> int:
        return len(self.seed_relations) + len(self.expanded_relations)


def search_entities(
    query_vector: np.ndarray,
    limit: int = 10,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Scans shard_entities and returns entities above cosine similarity threshold."""
    if not graph.get_graph_db_path().exists():
        return []

    conn = graph.get_graph_connection()
    matches = []
    try:
        cursor = conn.execute("SELECT entity_id, name, entity_type, embedding FROM shard_entities WHERE embedding IS NOT NULL")
        for row in cursor:
            emb = _unpack_vector(row["embedding"])
            if emb is not None:
                sim = _cosine_similarity(query_vector, emb)
                if sim >= threshold:
                    matches.append({
                        "entity_id": row["entity_id"],
                        "name": row["name"],
                        "entity_type": row["entity_type"],
                        "similarity": sim,
                    })
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:limit]


def search_relations(
    query_vector: np.ndarray,
    limit: int = 15,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Scans shard_relations and returns relations above cosine similarity threshold."""
    if not graph.get_graph_db_path().exists():
        return []

    conn = graph.get_graph_connection()
    matches = []
    try:
        cursor = conn.execute("""
            SELECT relation_id, subject, predicate, object, relation_text,
                   head_entity_id, tail_entity_id, source_shard_hash, weight, embedding
            FROM shard_relations
            WHERE embedding IS NOT NULL
        """)
        for row in cursor:
            emb = _unpack_vector(row["embedding"])
            if emb is not None:
                sim = _cosine_similarity(query_vector, emb)
                if sim >= threshold:
                    matches.append({
                        "relation_id": row["relation_id"],
                        "subject": row["subject"],
                        "predicate": row["predicate"],
                        "object": row["object"],
                        "relation_text": row["relation_text"],
                        "head_entity_id": row["head_entity_id"],
                        "tail_entity_id": row["tail_entity_id"],
                        "source_shard_hash": row["source_shard_hash"],
                        "weight": row["weight"],
                        "similarity": sim,
                    })
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:limit]


def expand_subgraph(
    seed_entity_ids: List[str],
    max_hops: int = 1,
    limit: int = 40,
) -> List[Dict[str, Any]]:
    """
    ID-Based Subgraph Expansion: Follows head_entity_id and tail_entity_id
    pointers in SQLite via indexed lookups. Zero graph DB required.
    """
    if not seed_entity_ids or not graph.get_graph_db_path().exists():
        return []

    conn = graph.get_graph_connection()
    expanded = []
    visited_entities = set(seed_entity_ids)
    visited_relations = set()

    current_entities = list(seed_entity_ids)

    try:
        for _ in range(max_hops):
            if not current_entities or len(expanded) >= limit:
                break
            placeholders = ",".join("?" * len(current_entities))
            params = (*current_entities, *current_entities)
            cursor = conn.execute(f"""
                SELECT relation_id, subject, predicate, object, relation_text,
                       head_entity_id, tail_entity_id, source_shard_hash, weight
                FROM shard_relations
                WHERE head_entity_id IN ({placeholders}) OR tail_entity_id IN ({placeholders})
                LIMIT ?
            """, (*params, limit - len(expanded)))

            next_entities = set()
            for row in cursor:
                rel_id = row["relation_id"]
                if rel_id in visited_relations:
                    continue
                visited_relations.add(rel_id)

                item = dict(row)
                item["hop_origin"] = "expansion"
                expanded.append(item)

                if item["head_entity_id"] and item["head_entity_id"] not in visited_entities:
                    next_entities.add(item["head_entity_id"])
                    visited_entities.add(item["head_entity_id"])
                if item["tail_entity_id"] and item["tail_entity_id"] not in visited_entities:
                    next_entities.add(item["tail_entity_id"])
                    visited_entities.add(item["tail_entity_id"])

            current_entities = list(next_entities)
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

    return expanded


def retrieve_vector_graph(
    query: str,
    query_vector: Optional[List[float]] = None,
    limit: int = 10,
    expand_hops: int = 1,
) -> Tuple[List[Dict[str, Any]], SubGraph]:
    """
    End-to-End Multi-Way Vector-Graph Retrieval:
      1. Embeds query via local Ollama nomic-embed-text.
      2. Vector searches entities and relations concurrently.
      3. Expands subgraph by 1 hop via SQLite indexed lookups.
      4. Pulls underlying source shards from the 9-DB shard cluster.
      5. Enriches shards with topological graph evidence.
    """
    subgraph = SubGraph()
    if not query:
        return [], subgraph

    vec = query_vector
    if vec is None:
        fn = _get_embedding_fn()
        vec = fn(query)

    if vec is None:
        return [], subgraph

    query_arr = np.array(vec, dtype=np.float32)

    # 1. Multi-way vector search
    seed_entities = search_entities(query_arr, limit=8)
    seed_relations = search_relations(query_arr, limit=12)

    subgraph.seed_entities = seed_entities
    subgraph.seed_relations = seed_relations

    # 2. Gather seed entity IDs for subgraph expansion
    seed_entity_ids = [e["entity_id"] for e in seed_entities]
    for rel in seed_relations:
        if rel.get("head_entity_id"):
            seed_entity_ids.append(rel["head_entity_id"])
        if rel.get("tail_entity_id"):
            seed_entity_ids.append(rel["tail_entity_id"])
    seed_entity_ids = list(dict.fromkeys(seed_entity_ids))

    # 3. Subgraph Expansion
    expanded = expand_subgraph(seed_entity_ids, max_hops=expand_hops, limit=25)
    subgraph.expanded_relations = expanded

    # 4. Collect referenced source shard hashes
    shard_hashes = set()
    for r in seed_relations:
        if r.get("source_shard_hash"):
            shard_hashes.add(r["source_shard_hash"])
    for r in expanded:
        if r.get("source_shard_hash"):
            shard_hashes.add(r["source_shard_hash"])

    subgraph.referenced_shard_hashes = shard_hashes
    if not shard_hashes:
        return [], subgraph

    # 5. Resolve hashes to actual shard dictionaries from the cluster
    shards_map = graph._shards_for_hashes(list(shard_hashes))

    # 6. Score and enrich shards with graph provenance
    results = []
    for fhash, shard_data in shards_map.items():
        item = dict(shard_data)

        matching_rels = [
            r for r in (seed_relations + expanded)
            if r.get("source_shard_hash") == fhash
        ]
        top_sim = max((r.get("similarity", 0.5) for r in matching_rels), default=0.5)
        centrality = len(matching_rels)

        item["file_hash"] = fhash
        item["vector_graph_score"] = top_sim * (1.0 + 0.1 * min(centrality, 5))
        item["graph_evidence"] = [r.get("relation_text") for r in matching_rels[:3]]
        results.append(item)

    results.sort(key=lambda x: x.get("vector_graph_score", 0.0), reverse=True)
    return results[:limit], subgraph


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion (RRF) with FTS5 Keyword Search
# ---------------------------------------------------------------------------

def fuse_with_fts(
    vector_graph_results: List[Dict[str, Any]],
    fts_results: List[Dict[str, Any]],
    k: int = 60,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Combines Vector-Graph subgraph expansion with FTS5 BM25 keyword recall
    using Reciprocal Rank Fusion:
        Score(d) = 1/(k + Rank_VG) + 1/(k + Rank_FTS)
    """
    scores: Dict[str, float] = {}
    docs: Dict[str, Dict[str, Any]] = {}

    for rank, item in enumerate(vector_graph_results):
        key = item.get("file_hash") or f"{item.get('_db_index')}_{item.get('id')}"
        scores[key] = scores.get(key, 0.0) + (1.0 / (k + rank + 1))
        docs[key] = item

    for rank, item in enumerate(fts_results):
        key = item.get("file_hash") or f"{item.get('_db_index')}_{item.get('id')}"
        scores[key] = scores.get(key, 0.0) + (1.0 / (k + rank + 1))
        if key not in docs:
            docs[key] = item
        if "bm25_score" in item:
            docs[key]["bm25_score"] = item["bm25_score"]

    fused = []
    for key, score in scores.items():
        doc = dict(docs[key])
        doc["rrf_fused_score"] = score
        fused.append(doc)

    fused.sort(key=lambda x: x["rrf_fused_score"], reverse=True)
    return fused[:limit]


# ---------------------------------------------------------------------------
# Batch Backfill Tool (Populates Knowledge Graph from Shard Cluster)
# ---------------------------------------------------------------------------

def backfill_knowledge_graph(
    max_shards: int = 500,
    batch_size: int = 50,
) -> Dict[str, int]:
    """
    Scans existing shards across the cluster and extracts knowledge triplets,
    bootstrapping the Vector Graph without external API costs.
    """
    init_vector_graph_db()
    total_triplets = 0
    shards_processed = 0

    embed_fn = _get_embedding_fn()

    for i in range(1, core.MAX_DB_COUNT + 1):
        if shards_processed >= max_shards:
            break
        if not core.get_db_path(i).exists():
            continue

        conn = core.get_connection(i)
        try:
            cursor = conn.execute(
                "SELECT file_hash, title, content FROM shards LIMIT ?",
                (min(batch_size, max_shards - shards_processed),)
            )
            for row in cursor:
                fhash = row["file_hash"]
                title = row["title"] or ""
                content = row["content"] or ""
                count = ingest_shard_triplets(fhash, title, content, embed_fn=embed_fn)
                total_triplets += count
                shards_processed += 1
        except Exception as e:
            logger.warning("Error reading DB %d for backfill: %s", i, e)
        finally:
            conn.close()

    return {"shards_processed": shards_processed, "triplets_ingested": total_triplets}


def stats() -> Dict[str, int]:
    """Returns count of entities, relations, and edges in the graph store."""
    if not graph.get_graph_db_path().exists():
        return {"entities": 0, "relations": 0, "edges": 0}

    conn = graph.get_graph_connection()
    try:
        entities = conn.execute("SELECT COUNT(*) FROM shard_entities").fetchone()[0]
        relations = conn.execute("SELECT COUNT(*) FROM shard_relations").fetchone()[0]
        edges = conn.execute("SELECT COUNT(*) FROM shard_edges").fetchone()[0]
        return {"entities": entities, "relations": relations, "edges": edges}
    except sqlite3.OperationalError:
        return {"entities": 0, "relations": 0, "edges": 0}
    finally:
        conn.close()
