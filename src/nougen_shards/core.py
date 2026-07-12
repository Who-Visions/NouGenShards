"""
Valerion Core — NouGenShards Memory Substrate.
Logic: SQLite + FTS5 + BM25 + Trigram (n-gram) + Vector Embeddings + Weighted Relevance Reranking.
Architecture: Valerion 21-step cognitive loop. Weighted multi-signal relevance blend (BM25 + semantic + usefulness prior).
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

import numpy as np

# Configuration (Module 10: Integrate Constraints)
# Rule 0.2 line-level mandate: environment-shaped values resolve from env with a
# logged constant as fallback only, never a bare inline literal.
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


# Per-DB byte ceiling and cluster count: overridable for constrained hosts or
# larger grids without editing code.
MAX_DB_SIZE = _env_int("NOUGEN_MAX_DB_SIZE", 1 * 1024 * 1024 * 1024)  # default 1GB
MAX_DB_COUNT = _env_int("NOUGEN_MAX_DB_COUNT", 9)
# SQLite busy timeout (s); embed clamp + timeout for the at-ingest embedder.
DB_TIMEOUT = _env_float("NOUGEN_DB_TIMEOUT", 10.0)
# Recency half-life for recall scoring. 30d rots month-old doctrine shards to
# the floor while fresh high-volume domains (arXiv) score ~1.0 and swamp recall.
RECALL_DECAY_HALFLIFE_DAYS = _env_float("NOUGEN_RECALL_DECAY_HALFLIFE_DAYS", 30.0)
ARXIV_RECALL_WEIGHT = _env_float("NOUGEN_RECALL_ARXIV_WEIGHT", 1.0)
RECALL_LANE_CHAMPIONS = _env_int("NOUGEN_RECALL_LANE_CHAMPIONS", 0)
EMBED_MAX_CHARS = _env_int("NOUGEN_EMBED_MAX_CHARS", 8000)
EMBED_TIMEOUT = _env_int("NOUGEN_EMBED_TIMEOUT", 10)

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
    conn = sqlite3.connect(str(path), timeout=DB_TIMEOUT)
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
            file_hash TEXT UNIQUE NOT NULL,
            domain_key TEXT DEFAULT 'global'
        );
    """)

    # Add embedding column if missing (Module 11: Transform Architecture)
    try:
        cursor.execute("ALTER TABLE shards ADD COLUMN embedding BLOB;")
    except sqlite3.OperationalError:
        pass

    # Add domain_key column if missing (Sub-Graph Context Isolation)
    try:
        cursor.execute("ALTER TABLE shards ADD COLUMN domain_key TEXT DEFAULT 'global';")
    except sqlite3.OperationalError:
        pass

    # Add density_score column if missing
    try:
        cursor.execute("ALTER TABLE shards ADD COLUMN density_score REAL DEFAULT 1.0;")
    except sqlite3.OperationalError:
        pass

    # Add consolidated column if missing
    try:
        cursor.execute("ALTER TABLE shards ADD COLUMN consolidated INTEGER DEFAULT 0;")
    except sqlite3.OperationalError:
        pass

    # Create semantic_knowledge table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS semantic_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            confidence_score REAL DEFAULT 1.0,
            domain_key TEXT DEFAULT 'global',
            updated_at TEXT NOT NULL,
            UNIQUE(subject, predicate)
        );
    """)

    # Create index for semantic domain lookup
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_semantic_domain_subject 
        ON semantic_knowledge (domain_key, subject);
    """)

    # Create composite index for domain-bound retrieval
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_shards_domain_utility 
        ON shards (domain_key, utility_score DESC);
    """)


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
    conn = sqlite3.connect(str(get_dedup_path()), timeout=DB_TIMEOUT)
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
    return float(np.dot(vec1, vec2))


def resolve_domain_from_path(target_path: Optional[str] = None) -> str:
    """
    Dynamically resolve the domain key by walking up the directory tree
    to find a project indicator (.git, pyproject.toml, package.json, or .nougen_vault).
    """
    if not target_path:
        target_path = os.getcwd()
    
    current = Path(target_path).resolve()
    if current.is_file():
        current = current.parent
        
    for parent in [current] + list(current.parents):
        # Look for project indicators
        indicators = [".git", ".nougen_vault", "pyproject.toml", "package.json"]
        if any((parent / ind).exists() for ind in indicators):
            parts = parent.parts
            if len(parts) >= 2:
                if parts[-2].lower() in ["watchtower", "nougen", "agents"]:
                    return f"{parts[-2]}/{parts[-1]}"
            return parts[-1]
            
    return "global"


_BASE64_HEX_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


def _looks_like_blob(content: str) -> bool:
    """High-confidence junk detector for the substrate landfill (invariant 7).

    Fires only on the pollution class — lockfiles, base64/hex dumps, minified
    bundles, whole encoder.json vocabs — identified structurally: a single
    whitespace-free run longer than NOUGEN_JUNK_MAX_TOKEN whose characters are
    overwhelmingly the base64/hex alphabet. Prose and real source code wrap and
    carry whitespace + diverse punctuation, so they pass. All thresholds are
    env-discovered (Rule 0.2); conservative defaults keep false positives ~0.
    """
    if not content:
        return False
    max_token = _env_int("NOUGEN_JUNK_MAX_TOKEN", 2000)
    ratio_floor = _env_float("NOUGEN_JUNK_ALPHABET_RATIO", 0.95)
    longest = ""
    for run in content.split():
        if len(run) > len(longest):
            longest = run
    if len(longest) <= max_token:
        return False
    alpha_hits = sum(1 for c in longest if c in _BASE64_HEX_CHARS)
    return (alpha_hits / len(longest)) >= ratio_floor


def calculate_contrastive_perplexity(content: str) -> float:
    """Estimates information density / contrastive perplexity using local Ollama or OpenRouter."""
    if not content:
        return 1.0
    
    # Heuristic compression-based fallback: ratio of gzip size to raw size
    import zlib
    try:
        compressed_len = len(zlib.compress(content.encode('utf-8')))
        raw_len = len(content.encode('utf-8'))
        compression_ratio = compressed_len / max(1, raw_len)
        fallback_score = float(min(1.0, max(0.1, compression_ratio * 1.5)))
    except Exception:
        fallback_score = 0.5

    # Check if we are running in a test environment to prevent local LLM/OpenRouter calls
    import sys
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return fallback_score

    # Try local Ollama first
    try:
        from .models_client import get_best_available_client
        client = get_best_available_client()
        if client and client.is_alive():
            models = client.list_models()
            # Local-player preference: custom NouGen fine-tunes (Sol-Ai is the designated
            # Player) outrank generic gemma4, which is only the floor — never below it.
            # Override with NOUGEN_DENSITY_MODEL. Within a family, largest tag wins on sort.
            override = os.environ.get("NOUGEN_DENSITY_MODEL")
            if override and override in models:
                best_model = override
            else:
                # FREE is highest priority: free cloud tags (e.g. gemma4:31b-cloud) cost $0
                # and are the most capable, so they win first; then custom NouGen fine-tunes
                # (Sol-Ai is the Player); then local gemma4 floor — never below it.
                _cloud = sorted((m for m in models if "cloud" in m.lower()), reverse=True)
                _pref_order = ["sol-ai", "iris-ai", "dav1d", "griot",
                               "kaedra", "rhea-noir", "davos", "gemma4"]
                best_model = (
                    _cloud[0] if _cloud
                    else next((m for pref in _pref_order
                               for m in sorted(models, reverse=True)
                               if m.lower().startswith(pref)),
                              (models[0] if models else None)))
            if best_model:
                prompt = (
                    "Analyze the following text and estimate its information density / contrastive perplexity score "
                    "between 0.0 (generic filler, boilerplate, highly redundant) and 1.0 (extremely dense, novel, high surprisal). "
                    "Provide ONLY the float number in your response, nothing else.\n\n"
                    f"Text: {content[:1000]}"
                )
                res_str = client.chat(best_model, [{"role": "user", "content": prompt}])
                import re
                match = re.search(r"\d+\.\d+", res_str)
                if match:
                    return float(match.group(0))
    except Exception:
        pass

    # Try OpenRouter free model
    try:
        from openrouter_guard import call_openrouter
        from .models_client import OpenRouterClient
        prompt = (
            "Analyze the following text and estimate its information density / contrastive perplexity score "
            "between 0.0 (generic filler, boilerplate, highly redundant) and 1.0 (extremely dense, novel, high surprisal). "
            "Provide ONLY the float number in your response, nothing else.\n\n"
            f"Text: {content[:1000]}"
        )
        # Resolve the free model dynamically from the live roster — never hardcoded.
        res_str = call_openrouter(prompt=prompt, model=OpenRouterClient().preferred_free_model(), temperature=0.1)
        import re
        match = re.search(r"\d+\.\d+", res_str)
        if match:
            return float(match.group(0))
    except Exception:
        pass

    return fallback_score


def lost_in_the_middle_reorder(shards: list) -> list:
    """Place highest utility shards at the absolute beginning and end of the retrieval packet."""
    if not shards:
        return []
    reordered = [None] * len(shards)
    left = 0
    right = len(shards) - 1
    for i, shard in enumerate(shards):
        if i % 2 == 0:
            reordered[left] = shard
            left += 1
        else:
            reordered[right] = shard
            right -= 1
    return reordered


def capture(event_type: str, title: str, content: str,
            tags: Optional[List[str]] = None, embedding: Optional[List[float]] = None,
            domain_key: Optional[str] = None, density_score: Optional[float] = None) -> bool:
    """Saves a unit of experience (Module 5: Extract Invariants)."""
    # Structural secret guard (HARDENING invariant 8): redact known credential
    # shapes from title/content/tags before anything is hashed, embedded, or
    # written. Shards may hold key names + fingerprints, never plaintext values
    # (Atibon/Keymaker doctrine). Redacting before the dedup hash means the
    # shard identity is the clean text and the hash never encodes a secret.
    # Best-effort: the redactor is stdlib-re only, but a failure must never
    # block capture.
    try:
        from .brain_scan.redaction import redact_content as _redact
        title = _redact(title)
        content = _redact(content)
        if tags:
            tags = [_redact(t) for t in tags]
    except Exception:
        pass

    # Ingest junk gate (HARDENING invariant 7): reject the low-signal blob class
    # (lockfiles, base64/hex dumps, minified/SVG-JSON) before it pollutes recall
    # or burns an embedding. Same skip contract as a dedup hit (returns False).
    if _looks_like_blob(content):
        return False

    if not domain_key:
        domain_key = resolve_domain_from_path()

    if density_score is None:
        density_score = calculate_contrastive_perplexity(content)

    # Opt-in density floor (invariant 7): operators can reject low-information
    # content below NOUGEN_MIN_DENSITY. Default 0.0 = disabled, so borderline
    # prose is never silently dropped unless someone opts into stricter filtering.
    _min_density = _env_float("NOUGEN_MIN_DENSITY", 0.0)
    if _min_density > 0.0 and density_score is not None and density_score < _min_density:
        return False

    # Clean the content for O(1) deduplication hashing to exclude injected recall packets or static context.
    clean_content = content
    if "=== NOUGENSHARDS RECALL PACKET" in content:
        clean_content = content.split("=== NOUGENSHARDS RECALL PACKET")[0].strip()

    fhash = hashlib.md5(clean_content.encode("utf-8", errors="ignore")).hexdigest()

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

        if embedding is None:
            # Embed at ingest so shards are born recallable — NULL embeddings
            # killed the semantic lane once (27k-shard backfill); never again.
            # Best-effort: a down/absent embed model degrades to keyword-only
            # recall for this shard (backfill sweeps it later), never blocks
            # capture.
            try:
                from .embedding_backfill import embed as _embed
                embedding = _embed(
                    clean_content[:EMBED_MAX_CHARS],
                    os.environ.get("NOUGEN_EMBED_MODEL", "nomic-embed-text"),
                    timeout=EMBED_TIMEOUT)
            except Exception:
                embedding = None

        emb_blob = None
        if embedding:
            arr = np.array(embedding, dtype=np.float32)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            emb_blob = sqlite3.Binary(arr.tobytes())

        tags_str = json.dumps(tags or [])
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        conn = get_connection(target_idx)
        try:
            cursor = conn.execute("""
                INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash, embedding, domain_key, density_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, event_type, title, content, tags_str, fhash, emb_blob, domain_key, density_score))
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
WEIGHT_BM25 = _env_float("NOUGEN_RECALL_WEIGHT_BM25", 0.4)
WEIGHT_SEMANTIC = _env_float("NOUGEN_RECALL_WEIGHT_SEMANTIC", 0.6)
WEIGHT_LIKELIHOOD = _env_float("NOUGEN_RECALL_WEIGHT_LIKELIHOOD", 0.7)
WEIGHT_PRIOR = _env_float("NOUGEN_RECALL_WEIGHT_PRIOR", 0.3)


def _squash_utility(u: float) -> float:
    """Map unbounded utility (grows via ACCESSED feedback, observed up to ~4.3)
    into [0,1) so the prior can never drown the bounded semantic likelihood —
    unbounded priors made incumbents win over perfect semantic matches
    (rich-get-richer, diagnosed 2026-07-11 via the recall probe)."""
    return u / (1.0 + u) if u > 0 else 0.0

# Stage-2 cross-encoder reranker (Tier-1 elevation). 2026 SOTA: a hybrid->rerank
# two-stage pipeline lifts Recall@5 ~+17% / MRR ~+40% over RRF alone. Off by
# default and lazy-loaded, so this is a no-op (zero new deps) until activated:
#   NOUGEN_RERANK=1   pip install FlagEmbedding   (bge-reranker-v2-m3 ~2.27GB)
RERANK_ENABLED = os.environ.get("NOUGEN_RERANK", "0") == "1"
RERANK_MODEL = os.environ.get("NOUGEN_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
# A near-verbatim doctrine match ranks >20 in the vector lane on arXiv-colliding
# paraphrases, so the default 20-candidate pool never lets it reach the
# cross-encoder. When rerank is on, pull a deeper pool AND lift the rerank-pool
# truncation to match, so strong matches get judged on merit; the reranker then
# sorts them correctly. This is the single lever that took the probe past its
# plateau — do not re-cap the rerank pool below the lane pool.
RERANK_POOL_CANDIDATES = int(os.environ.get("NOUGEN_RERANK_POOL_CANDIDATES", "200"))
RERANK_CANDIDATES = int(os.environ.get("NOUGEN_RERANK_CANDIDATES", str(RERANK_POOL_CANDIDATES)))
_RERANKER = None  # process-cached reranker handle

# Stage-3 MMR diversification. Near-duplicate shards (same fix captured across
# sessions, re-ingested docs) survive capture-time dedup because their hashes
# differ, then crowd the whole top-k with one story. MMR trades a little
# relevance for coverage: NOUGEN_MMR_LAMBDA=1.0 disables (pure relevance).
MMR_LAMBDA = float(os.environ.get("NOUGEN_MMR_LAMBDA", "0.75"))

def _process_fts_result(row, db_index, query_embedding):
    """Helper to score a single FTS result via the weighted relevance blend."""
    item = dict(row)
    item["_db_index"] = db_index
    # 1. Likelihood Part A: BM25 (The Adjacency Score)
    # FTS5 bm25() returns negative values where *more negative == stronger match*
    # (the query orders bm25_score ASC for exactly this reason). Taking abs() folds
    # strong and weak matches onto the same magnitude and inverts the signal — a
    # strong hit (-8 -> 0.11) scored *below* a weak one (-0.5 -> 0.67). Map it
    # through a logistic instead: monotonically decreasing in bm25 and bounded in
    # (0, 1), so stronger matches contribute more. Exponent clamped against the
    # rare positive score to avoid math.exp overflow.
    norm_bm25 = 1.0 / (1.0 + math.exp(max(-60.0, min(60.0, item["bm25_score"]))))

    # 2. Likelihood Part B: Semantic (The Latent Score)
    sem_score = 0.0
    if query_embedding is not None and item["embedding"]:
        try:
            if item["embedding"].startswith(b'['):
                raise ValueError("Legacy JSON embedding detected")
            emb_array = np.frombuffer(item["embedding"], dtype=np.float32)
            sem_score = float(np.dot(query_embedding, emb_array))
        except Exception:
            try:
                emb_array = np.array(json.loads(item["embedding"].decode()), dtype=np.float32)
                sem_score = float(np.dot(query_embedding, emb_array))
            except Exception:
                sem_score = 0.0

    # Synthesize Coherent Likelihood (Module 9)
    likelihood = (norm_bm25 * WEIGHT_BM25) + (sem_score * WEIGHT_SEMANTIC)

    # 3. Temporal decay factor (half-life of 30 days) to prevent stale successful sessions from dominating results
    decay = 1.0
    ts_str = item.get("timestamp")
    if ts_str:
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
            decay = max(0.1, 0.5 ** (age_days / RECALL_DECAY_HALFLIFE_DAYS))
        except Exception:
            pass

    decayed_utility = item["utility_score"] * decay

    # 4. Final relevance: a weighted blend of the likelihood signal and the decayed utility score
    item["final_score"] = (likelihood * WEIGHT_LIKELIHOOD) + (_squash_utility(decayed_utility) * WEIGHT_PRIOR)
    return item


def _build_fts_match_query(query: str, joiner: str = " ") -> Optional[str]:
    """
    Build a safe FTS5 MATCH expression from arbitrary user input.

    Every word is treated as a literal phrase: each token is double-quoted (any
    embedded quote doubled, per FTS5 escaping), so query text can never be parsed
    as FTS5 operators (AND/OR/NOT/NEAR/*, bare quotes, parentheses). Without this,
    inputs like `c++`, `foo"bar`, or a lone `AND` raise OperationalError and the
    search silently degrades to a LIKE substring scan. Tokens shorter than 3 chars
    are dropped because the trigram tokenizer cannot index them. Returns None when
    nothing matchable remains (caller then uses the LIKE fallback).

    `joiner` controls the operator between phrases: the default single space is
    FTS5 implicit AND; callers pass '" OR "' with surrounding spaces via the
    ranked-OR retry so conversational queries where terms never co-occur still
    match (bm25 ranks fuller-coverage rows first).
    """
    tokens = [t for t in query.split() if len(t) >= 3]
    if not tokens:
        return None

    # Strip common agent boilerplate and stop-words to prevent BM25 inflation
    boilerplate = {
        "write", "python", "script", "code", "file", "fix", "error", "run", "test",
        "implement", "create", "add", "modify", "update", "delete", "change", "verify",
        "using", "with", "from", "that", "this", "here", "there", "what", "where", "how",
        "and", "the", "for", "you", "are", "not", "out", "but"
    }
    filtered_tokens = [t for t in tokens if t.lower() not in boilerplate]
    if filtered_tokens:
        tokens = filtered_tokens

    return joiner.join('"' + t.replace('"', '""') + '"' for t in tokens)


def _keyword_retrieve(query: str, limit: int = 20, query_embedding: Optional[List[float]] = None,
                      domain_key: str = "global") -> list:
    """Scans for keyword matches using FTS5 (with LIKE fallback)."""
    from . import history # pylint: disable=import-outside-toplevel

    results = []
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            fts_worked = False
            # Two-pass MATCH: implicit AND first (precision), then the same
            # safe-quoted tokens joined with OR (recall). Multi-term
            # conversational queries used to die here — "huggingface nougenai
            # token" returned 0 rows on AND semantics while "huggingface"
            # alone matched thousands, and the LIKE fallback (`%whole query%`)
            # is stricter still. bm25 ranking keeps fuller-coverage rows first
            # on the OR pass. (HARDENING invariant 5)
            match_attempts = []
            fts_query = _build_fts_match_query(query)
            if fts_query is not None:
                match_attempts.append(fts_query)
                or_query = _build_fts_match_query(query, joiner=" OR ")
                if or_query and or_query != fts_query:
                    match_attempts.append(or_query)
            for match_expr in match_attempts:
                try:
                    # domain_key None/"*" => search ALL domains (whole brain), not one bucket.
                    dom_clause = "" if domain_key in (None, "*") else "s.domain_key = ? AND "
                    dom_params = () if domain_key in (None, "*") else (domain_key,)
                    cursor = conn.execute(f"""
                        SELECT s.id, s.timestamp, s.title, s.content, s.utility_score,
                               s.embedding, s.tags, s.domain_key, s.density_score, bm25(shards_fts) as bm25_score
                        FROM shards s JOIN shards_fts ON s.id = shards_fts.rowid
                        WHERE {dom_clause}shards_fts MATCH ?
                        ORDER BY bm25_score ASC LIMIT ?
                    """, (*dom_params, match_expr, limit))
                    res = cursor.fetchall()
                    if res:
                        for row in res:
                            history.log_event(row["id"], i, "ACCESSED")
                            results.append(_process_fts_result(row, i, query_embedding))
                        fts_worked = True
                        break
                except sqlite3.OperationalError:
                    break

            if not fts_worked:
                history.log_event(0, i, "SEARCH_FALLBACK", metadata={"query": query})
                
                like_query = f"%{query}%"
                dom_clause = "" if domain_key in (None, "*") else "domain_key = ? AND "
                dom_params = () if domain_key in (None, "*") else (domain_key,)
                cursor = conn.execute(f"""
                    SELECT id, timestamp, title, content, utility_score, embedding, tags, domain_key, density_score
                    FROM shards
                    WHERE {dom_clause}(title LIKE ? OR content LIKE ?)
                    ORDER BY utility_score DESC LIMIT ?
                """, (*dom_params, like_query, like_query, limit))
                for row in cursor:
                    item = dict(row)
                    item["_db_index"] = i
                    history.log_event(item["id"], i, "ACCESSED")
                    sem_score = 0.0
                    if query_embedding is not None and item["embedding"]:
                        try:
                            if item["embedding"].startswith(b'['):
                                raise ValueError("Legacy JSON embedding")
                            emb_array = np.frombuffer(item["embedding"], dtype=np.float32)
                            sem_score = float(np.dot(query_embedding, emb_array))
                        except Exception:
                            try:
                                emb_array = np.array(json.loads(item["embedding"].decode()), dtype=np.float32)
                                sem_score = float(np.dot(query_embedding, emb_array))
                            except Exception:
                                sem_score = 0.0
                    likelihood = sem_score if query_embedding is not None else 0.5

                    decay = 1.0
                    ts_str = item.get("timestamp")
                    if ts_str:
                        try:
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
                            decay = max(0.1, 0.5 ** (age_days / RECALL_DECAY_HALFLIFE_DAYS))
                        except Exception:
                            pass

                    decayed_utility = item["utility_score"] * decay
                    item["final_score"] = (likelihood * 0.5) + (decayed_utility * 0.5)
                    results.append(item)
        finally:
            conn.close()

    results.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    return results[:limit]


def _vector_retrieve_ann(query_embedding: List[float], limit: int = 20,
                         domain_key: str = "global"):
    """ANN fast-path for _vector_retrieve (opt-in via NOUGEN_ANN=1).

    Uses the unified HNSW index to fetch candidate (db, id) pairs sub-linearly,
    then re-scores them with the SAME dot + temporal-decay + utility blend as the
    linear scan, so RRF fusion downstream is unchanged. Returns None if the index
    is unavailable -> the caller falls back to the verified linear scan.
    """
    from . import ann_index, history  # pylint: disable=import-outside-toplevel
    # Wide candidate pool: final ranking blends cosine with utility+recency, which
    # can promote items outside the pure-cosine top-k, so over-fetch to keep parity
    # with the full linear scan. Still tiny vs scanning all 47k rows.
    candidates = ann_index.query(query_embedding, top_n=max(limit * 50, 500))
    if candidates is None:
        return None  # no index -> signal fallback

    q = np.asarray(query_embedding, dtype=np.float32)
    by_db: dict = {}
    for db_idx, sid in candidates:
        by_db.setdefault(db_idx, []).append(sid)

    results = []
    for db_idx, ids in by_db.items():
        if not get_db_path(db_idx).exists():
            continue
        conn = get_connection(db_idx)
        try:
            placeholders = ",".join("?" * len(ids))
            dom_clause = "" if domain_key in (None, "*") else "AND domain_key = ? "
            params = list(ids) + ([] if domain_key in (None, "*") else [domain_key])
            cursor = conn.execute(f"""
                SELECT id, timestamp, title, content, utility_score, embedding, tags, domain_key
                FROM shards
                WHERE id IN ({placeholders}) {dom_clause}AND embedding IS NOT NULL
            """, params)
            for row in cursor:
                item = dict(row)
                item["_db_index"] = db_idx
                try:
                    emb_array = np.frombuffer(item["embedding"], dtype=np.float32)
                    sem_score = float(np.dot(q, emb_array))
                except Exception:
                    sem_score = 0.0
                decay = 1.0
                ts_str = item.get("timestamp")
                if ts_str:
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
                        decay = max(0.1, 0.5 ** (age_days / RECALL_DECAY_HALFLIFE_DAYS))
                    except Exception:
                        pass
                decayed_utility = item["utility_score"] * decay
                item["final_score"] = (sem_score * WEIGHT_LIKELIHOOD) + (_squash_utility(decayed_utility) * WEIGHT_PRIOR)
                results.append(item)
        finally:
            conn.close()

    results.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    top_results = results[:limit]
    for item in top_results:
        history.log_event(item["id"], item["_db_index"], "ACCESSED")
    return top_results


def _vector_retrieve(query_embedding: Optional[List[float]], limit: int = 20,
                     domain_key: str = "global") -> list:
    """Scans for semantic vector matches independent of FTS."""
    if query_embedding is None:
        return []

    # ANN fast-path (opt-in). Falls back to the linear scan below if the index
    # is missing/stale/unreadable, so correctness never depends on the index.
    if os.environ.get("NOUGEN_ANN") == "1":
        ann_results = _vector_retrieve_ann(query_embedding, limit, domain_key)
        if ann_results is not None:
            return ann_results

    from . import history # pylint: disable=import-outside-toplevel

    results = []
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            dom_clause = "" if domain_key in (None, "*") else "domain_key = ? AND "
            dom_params = () if domain_key in (None, "*") else (domain_key,)
            cursor = conn.execute(f"""
                SELECT id, timestamp, title, content, utility_score, embedding, tags, domain_key
                FROM shards
                WHERE {dom_clause}embedding IS NOT NULL
            """, dom_params)
            for row in cursor:
                item = dict(row)
                item["_db_index"] = i
                
                try:
                    if item["embedding"].startswith(b'['):
                        raise ValueError("Legacy JSON embedding")
                    emb_array = np.frombuffer(item["embedding"], dtype=np.float32)
                except Exception:
                    try:
                        emb_array = np.array(json.loads(item["embedding"].decode()), dtype=np.float32)
                    except Exception:
                        emb_array = None
                if emb_array is None:
                    sem_score = 0.0
                else:
                    # True cosine: stored embeddings are not guaranteed unit-norm,
                    # and an unnormalized dot silently rescales the likelihood
                    # term against the utility prior (diagnosed 2026-07-11).
                    e_norm = float(np.linalg.norm(emb_array))
                    sem_score = float(np.dot(query_embedding, emb_array)) / e_norm if e_norm > 0 else 0.0

                decay = 1.0
                ts_str = item.get("timestamp")
                if ts_str:
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
                        decay = max(0.1, 0.5 ** (age_days / RECALL_DECAY_HALFLIFE_DAYS))
                    except Exception:
                        pass

                decayed_utility = item["utility_score"] * decay
                item["final_score"] = (sem_score * WEIGHT_LIKELIHOOD) + (_squash_utility(decayed_utility) * WEIGHT_PRIOR)
                results.append(item)
        finally:
            conn.close()

    results.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    top_results = results[:limit]
    
    for item in top_results:
        history.log_event(item["id"], item["_db_index"], "ACCESSED")
        
    return top_results


def reciprocal_rank_fusion(result_lists: List[List[dict]], k: int = 60) -> List[dict]:
    """
    Module 8 / 21: Reciprocal Rank Fusion (RRF) to merge multiple ranked lists.
    """
    rrf_scores = {}  # key -> float
    item_map = {}    # key -> dict
    
    def get_rrf_key(item: dict) -> str:
        h = item.get("file_hash")
        if h:
            return f"hash_{h}"
        item_id = item.get("id")
        db_idx = item.get("_db_index")
        if item_id is not None and db_idx is not None:
            return f"id_{db_idx}_{item_id}"
        title = item.get("title", "")
        content = item.get("content", "")
        val = f"{title}|||{content}"
        return hashlib.sha256(val.encode("utf-8", errors="ignore")).hexdigest()

    for rank_list in result_lists:
        if not rank_list:
            continue
        for rank_idx, item in enumerate(rank_list):
            key = get_rrf_key(item)
            rank = rank_idx + 1
            score = 1.0 / (k + rank)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + score
            
            if key not in item_map:
                item_map[key] = item.copy()
            else:
                for key_name, val in item.items():
                    if item_map[key].get(key_name) is None and val is not None:
                        item_map[key][key_name] = val

    merged = []
    for key, item in item_map.items():
        consensus_score = rrf_scores[key]
        decay = 1.0
        ts_str = item.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
                decay = max(0.1, 0.5 ** (age_days / RECALL_DECAY_HALFLIFE_DAYS))
            except Exception:
                pass
        decayed_utility = item.get("utility_score", 1.0) * decay
        item["final_score"] = consensus_score * (0.7 + (decayed_utility * 0.3))
        merged.append(item)

    merged.sort(key=lambda x: x["final_score"], reverse=True)
    return merged


def _get_reranker():
    """Lazy-load and cache the cross-encoder reranker. Returns None if unavailable
    so callers degrade gracefully to the RRF ordering (no hard dependency)."""
    global _RERANKER
    if _RERANKER is not None:
        return _RERANKER
    try:
        from FlagEmbedding import FlagReranker  # pylint: disable=import-outside-toplevel
        _RERANKER = FlagReranker(RERANK_MODEL, use_fp16=True)
    except Exception:  # missing lib/model/VRAM — stay on RRF
        _RERANKER = False
    return _RERANKER


def rerank(query: str, items: List[dict], top_k: int) -> List[dict]:
    """Stage-2 cross-encoder reranking of RRF candidates.

    Scores each (query, title+content) pair with all-to-all attention and returns
    the top_k by that score. Any failure (no model, OOM) falls back to the input
    order, so retrieval never breaks because the reranker is unavailable.
    """
    if not items:
        return items[:top_k]
    reranker = _get_reranker()
    if not reranker:
        return items[:top_k]
    try:
        pairs = [[query, f"{it.get('title','')}\n{it.get('content','')}"[:2048]] for it in items]
        scores = reranker.compute_score(pairs, normalize=True)
        if not isinstance(scores, list):
            scores = [scores]
        for it, sc in zip(items, scores):
            it["rerank_score"] = float(sc)
        ranked = sorted(items, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        return ranked[:top_k]
    except Exception:
        return items[:top_k]


def _item_unit_embedding(item: dict) -> Optional[np.ndarray]:
    """Decode a shard's stored embedding to a unit vector; None if absent/legacy-JSON."""
    raw = item.get("embedding")
    if not raw or not isinstance(raw, (bytes, bytearray)):
        return None
    try:
        if bytes(raw).startswith(b'['):
            return None
        vec = np.frombuffer(raw, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else None
    except Exception:
        return None


def mmr_diversify(items: List[dict], limit: int, lambda_: float = MMR_LAMBDA) -> List[dict]:
    """
    Maximal Marginal Relevance over scored candidates: greedily pick the item
    with the best blend of relevance (utility_score_tripartite) and novelty
    (1 - max cosine similarity to anything already picked).

    Items without embeddings contribute zero similarity, so they compete on
    relevance alone and a vault with no embeddings degrades to the input order.
    """
    if lambda_ >= 1.0 or len(items) <= 1:
        return items[:limit]

    embs = [_item_unit_embedding(it) for it in items]
    # Relevance normalized to [0,1] so it shares a scale with cosine similarity.
    rels = [it.get("utility_score_tripartite", 0.0) for it in items]
    max_rel = max(rels) if rels else 1.0
    if max_rel > 0:
        rels = [r / max_rel for r in rels]

    selected: List[int] = [0]  # top candidate always survives
    remaining = list(range(1, len(items)))
    while remaining and len(selected) < limit:
        best_idx, best_score = remaining[0], -np.inf
        for idx in remaining:
            max_sim = 0.0
            if embs[idx] is not None:
                for sel in selected:
                    if embs[sel] is not None:
                        sim = float(np.dot(embs[idx], embs[sel]))
                        if sim > max_sim:
                            max_sim = sim
            score = lambda_ * rels[idx] - (1.0 - lambda_) * max_sim
            if score > best_score:
                best_idx, best_score = idx, score
        selected.append(best_idx)
        remaining.remove(best_idx)

    return [items[i] for i in selected]


def retrieve(query: str, limit: int = 3, query_embedding: Optional[List[float]] = None,
             domain_key: Optional[str] = None) -> list:
    """
    Advanced Retrieval (Module 21): Runs both keyword (FTS/LIKE) and vector (semantic)
    searches in parallel lanes and merges them using Reciprocal Rank Fusion (RRF).
    When NOUGEN_RERANK=1, a cross-encoder reranks the top RRF candidates (Stage 2).
    """
    import concurrent.futures

    # Ensure all existing shard databases are schema-upgraded to the current version before querying
    for i in range(1, MAX_DB_COUNT + 1):
        if get_db_path(i).exists():
            init_db(i)

    if not domain_key:
        domain_key = resolve_domain_from_path()
        
    if query_embedding is not None:
        arr = np.array(query_embedding, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            query_embedding = arr / norm

    # Pool size env-tunable (Rule 0.2): too small a pool lets high-volume domains
    # (e.g. 6.6K arXiv shards) crowd out sparse operational shards before fusion.
    # When rerank is on, pull a deeper pool (RERANK_POOL_CANDIDATES) so a strong
    # match ranked past 20 in a lane still reaches the cross-encoder to be judged.
    _base_candidates = int(os.environ.get("NOUGEN_RECALL_CANDIDATES", "20"))
    if RERANK_ENABLED:
        _base_candidates = max(_base_candidates, RERANK_POOL_CANDIDATES)
    candidate_limit = max(limit * 2, _base_candidates)

    def run_parallel_retrieval(active_domain: str):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_keyword = executor.submit(
                _keyword_retrieve, query, candidate_limit, query_embedding, active_domain
            )
            future_vector = executor.submit(
                _vector_retrieve, query_embedding, candidate_limit, active_domain
            )

            keyword_results = future_keyword.result()
            vector_results = future_vector.result()

        fused = reciprocal_rank_fusion([keyword_results, vector_results], k=60)
        return fused, keyword_results, vector_results

    all_results, kw_lane, vec_lane = run_parallel_retrieval(domain_key)

    # Fallback: if the domain-scoped pass found nothing, sweep the ENTIRE brain
    # (all domain_keys). Without this, recall stays siloed to one bucket
    # (e.g. 'global' = <2% of shards) and misses the other 47k+ shards.
    if not all_results and domain_key != "*":
        all_results, kw_lane, vec_lane = run_parallel_retrieval("*")

    def _champ_key(it):
        return (it.get("id"), (it.get("title") or "")[:80])

    # Stage 2: cross-encoder rerank the top RRF candidates (no-op unless enabled).
    if RERANK_ENABLED:
        pool = all_results[:RERANK_CANDIDATES]
        # Feed lane champions INTO the reranker instead of force-seating them
        # later: RRF consensus bias buries single-lane semantic winners, but the
        # cross-encoder can judge them on merit once they reach the pool.
        if RECALL_LANE_CHAMPIONS > 0:
            present = {_champ_key(it) for it in pool}
            for lane in (kw_lane, vec_lane):
                for it in lane[:RECALL_LANE_CHAMPIONS]:
                    if _champ_key(it) not in present:
                        pool.append(it)
                        present.add(_champ_key(it))
        all_results = rerank(query, pool, len(all_results))

    # Tripartite Utility Score & Eviction policy
    # Formula: U = (w_r * relevance) * (e^(-lambda * delta_t)) * density_score
    # (No random epsilon: jitter made identical queries return different rankings
    # run-to-run. Python's sort is stable, so true ties keep a deterministic order.)
    scored_results = []
    
    # Normalize relevance scores to a consistent [0.1, 1.0] scale to prevent scale mismatch
    # between RRF rank-based scores (max 0.016) and cross-encoder scores (max 1.0).
    raw_relevances = [item.get("rerank_score", item.get("final_score", 0.5)) for item in all_results]
    max_rel = max(raw_relevances) if raw_relevances else 1.0
    min_rel = min(raw_relevances) if raw_relevances else 0.0
    rel_span = max_rel - min_rel

    for item in all_results:
        raw_rel = item.get("rerank_score", item.get("final_score", 0.5))
        if rel_span > 0:
            relevance = 0.1 + 0.9 * ((raw_rel - min_rel) / rel_span)
        else:
            relevance = 1.0 if raw_rel > 0 else 0.5
            
        decay = 1.0
        ts_str = item.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
                decay = max(0.1, 0.5 ** (age_days / RECALL_DECAY_HALFLIFE_DAYS))
            except Exception:
                pass
        
        density = item.get("density_score", 1.0)

        u_shard = (1.0 * relevance) * decay * density
        # High-volume domain damper (Rule 0.2, default-neutral): ~6.6K sharp
        # single-topic arXiv abstracts outrank sparse operational doctrine on
        # paraphrase queries. Set NOUGEN_RECALL_ARXIV_WEIGHT<1 to rebalance.
        if ARXIV_RECALL_WEIGHT != 1.0 and "arxiv" in (item.get("title") or "").lower():
            u_shard *= ARXIV_RECALL_WEIGHT
        item["utility_score_tripartite"] = u_shard
        scored_results.append(item)
    
    # Sort candidates by the tripartite score
    scored_results.sort(key=lambda x: x["utility_score_tripartite"], reverse=True)
    
    # Dynamic Thresholding / Drop bottom 50% if we have many candidates
    if scored_results:
        if len(scored_results) > limit:
            cutoff = len(scored_results) // 2
            surviving = scored_results[:max(limit, cutoff)]
        else:
            surviving = scored_results
        # Filter anything below dynamic threshold (e.g. 0.05)
        surviving = [it for it in surviving if it["utility_score_tripartite"] >= 0.05]
        if not surviving and scored_results:
            surviving = [scored_results[0]]
    else:
        surviving = []
        
    # Stage 3: MMR diversification so near-duplicates don't crowd the packet
    diversified = mmr_diversify(surviving, limit)

    # Lane champions (Rule 0.2, default-neutral): RRF rewards cross-lane
    # consensus, so a vector-#1 that never ranks in the keyword lane (typical
    # for doctrine matched by meaning, not words) gets crowded out by mid-rank
    # items appearing in both lanes. Without a reranker to judge on merit,
    # guarantee each lane's top-N a forced seat. (When RERANK_ENABLED,
    # champions were already fed into the rerank pool above instead.)
    if RECALL_LANE_CHAMPIONS > 0 and not RERANK_ENABLED:
        present = {_champ_key(it) for it in diversified}
        champs = []
        for lane in (kw_lane, vec_lane):
            for it in lane[:RECALL_LANE_CHAMPIONS]:
                if _champ_key(it) not in present:
                    champs.append(it)
                    present.add(_champ_key(it))
        if champs:
            diversified = champs + diversified

    # Lost in the Middle Mitigation (interleave)
    reordered = lost_in_the_middle_reorder(diversified[:limit])
    return reordered


def get_shard_by_id(shard_id: int, db_index: int):
    """Retrieves a specific shard by ID from a specific DB index."""
    if not get_db_path(db_index).exists(): return None
    conn = get_connection(db_index)
    try:
        row = conn.execute("SELECT * FROM shards WHERE id = ?", (shard_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def mark_shard(shard_id: int, worked: bool, db_index: Optional[int] = None):
    """Updates the usefulness prior (utility_score) from outcome evidence (helpful / not).

    Shard ids are per-DB AUTOINCREMENT, so the same id exists in several of the
    9 cluster DBs. Pass db_index (a recall result's _db_index) to target the exact
    shard; without it we fall back to the first id match across the grid, which is
    ambiguous once ids collide and can update the wrong shard.
    """
    indices = [db_index] if db_index is not None else range(1, MAX_DB_COUNT + 1)
    for i in indices:
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            row = conn.execute("SELECT id, utility_score FROM shards WHERE id = ?", (shard_id,)).fetchone()
            if row:
                old_score = row["utility_score"]
                val = 1.0 if worked else -0.5
                new_score = old_score + val
                conn.execute("UPDATE shards SET utility_score = ? WHERE id = ?", (new_score, shard_id))
                conn.commit()
            else:
                continue
        finally:
            conn.close()

        # Log UTILITY_CHANGE event
        from . import history # pylint: disable=import-outside-toplevel
        history.log_event(shard_id, i, "UTILITY_CHANGE", old_score=old_score, new_score=new_score)

        return True
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


# Per-record body cap for recall packets. Whole-file CODE_SHARDs (e.g. a raw
# encoder.json vocab) can run to megabytes; a packet must stay readable by a
# small executor model. The truncation marker preserves the exact handle
# (id + db_index) so callers can re-query the full body when needed.
RECALL_SNIPPET_CHARS = _env_int("NOUGEN_RECALL_SNIPPET_CHARS", 1500)


def lane_health() -> dict:
    """Recall-lane health for the substrate (HARDENING invariant 4).

    Returns total shard count and embedding coverage % across the DB grid, so
    callers never assert "no match" from a degraded semantic lane (a dead
    embedding index once returned empty recall while 27k shards sat unembedded).
    Cheap: two COUNT(*) per existing DB. Best-effort — any error yields
    {"ok": False} rather than raising into a recall path.
    """
    try:
        total = 0
        embedded = 0
        for i in range(1, MAX_DB_COUNT + 1):
            if not get_db_path(i).exists():
                continue
            conn = get_connection(i)
            try:
                total += conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
                embedded += conn.execute(
                    "SELECT COUNT(*) FROM shards WHERE embedding IS NOT NULL").fetchone()[0]
            finally:
                conn.close()
        coverage = (embedded / total * 100.0) if total else 0.0
        return {"ok": True, "total_shards": total, "embedding_coverage_pct": round(coverage, 1)}
    except Exception:
        return {"ok": False}


def _empty_recall_notice() -> str:
    """Empty-recall marker annotated with lane health so absence isn't mistaken
    for a healthy 'no match' when the semantic lane is degraded (invariant 4)."""
    h = lane_health()
    if not h.get("ok"):
        return ("<!-- NO RELEVANT MEMORY RECALLED (lane health unknown — "
                "treat absence as unverified) -->")
    cov = h["embedding_coverage_pct"]
    # Threshold is discovered from env, not hardcoded (Rule 0.2). Default 50%:
    # below half-embedded, semantic recall is unreliable enough that an empty
    # result cannot be trusted as a true "no match".
    min_cov = _env_float("NOUGEN_MIN_COVERAGE_PCT", 50.0)
    warn = " DEGRADED SEMANTIC LANE — absence unverified" if cov < min_cov else ""
    return (f"<!-- NO RELEVANT MEMORY RECALLED "
            f"(vault: {h['total_shards']} shards, {cov}% embedded{warn}) -->")


def compile_recall_packet(shards: list) -> str:
    """Synthesis of retrieved experience into a coherent context packet (Module 18)."""
    if not shards:
        return _empty_recall_notice()
    output = ["=== NOUGENSHARDS RECALL PACKET [BAYESIAN SYNTHESIS] ==="]
    for s in shards:
        # Surface the source DB so callers can target this exact shard in the
        # 9-DB grid (mark_utility / link_shards / recall_related take db_index).
        db_idx = s.get("_db_index")
        db_tag = f" (db {db_idx})" if db_idx is not None else ""
        output.append(f"--- RECORD #{s['id']}{db_tag} [Score: {s['final_score']:.2f}] ---")
        output.append(f"When: {format_shard_when(s.get('timestamp'))}")
        content = s["content"] or ""
        if len(content) > RECALL_SNIPPET_CHARS:
            omitted = len(content) - RECALL_SNIPPET_CHARS
            content = (
                content[:RECALL_SNIPPET_CHARS]
                + f"\n[... truncated {omitted:,} chars — full body: shard_get(shard_id={s['id']}, db_index={db_idx}) ...]"
            )
        output.append(f"Title: {s['title']}\n{content}\n")
    # "Anghkooey" — "remember" (FROM). Spoken only when recall succeeds:
    # the engine's acknowledgment that a past life was actually surfaced.
    output.append("Anghkooey — NouGenShards remembers.")
    return "\n".join(output)


def retrieve_semantic_rules(query: str, limit: int = 5, domain_key: str = "global") -> List[dict]:
    """Retrieve top matching semantic rules using simple keyword containment matching."""
    words = [w.strip().lower() for w in query.split() if len(w.strip()) > 2]
    if not words:
        # Default to loading general rules if query is too generic or short
        words = ["rule", "system", "architecture"]
    
    rules = []
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            for word in words[:3]:
                cursor = conn.execute("""
                    SELECT id, subject, predicate, confidence_score, domain_key, updated_at, ? as _db_index
                    FROM semantic_knowledge
                    WHERE (domain_key = ? OR domain_key = 'global')
                      AND (subject LIKE ? OR predicate LIKE ?)
                    ORDER BY confidence_score DESC
                    LIMIT ?
                """, (i, domain_key, f"%{word}%", f"%{word}%", limit))
                for row in cursor:
                    rules.append(dict(row))
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
            
    # Deduplicate
    seen = set()
    unique_rules = []
    for r in rules:
        key = (r["subject"].lower(), r["predicate"].lower())
        if key not in seen:
            seen.add(key)
            unique_rules.append(r)
    
    unique_rules.sort(key=lambda x: x["confidence_score"], reverse=True)
    return unique_rules[:limit]


def retrieve_dual_system(query: str, limit_semantic: int = 5, limit_episodic: int = 3,
                         domain_key: Optional[str] = None) -> dict:
    """Run dual-system query retrieving both semantic rules and episodic logs."""
    if not domain_key:
        domain_key = resolve_domain_from_path()
        
    semantic_rules = retrieve_semantic_rules(query, limit=limit_semantic, domain_key=domain_key)
    episodic_shards = retrieve(query, limit=limit_episodic, domain_key=domain_key)
    
    return {
        "semantic_rules": semantic_rules,
        "episodic_shards": episodic_shards
    }


def compile_recall_packet_dual(result: dict) -> str:
    """Compile both semantic invariants and episodic memories into a unified context packet."""
    semantic_rules = result.get("semantic_rules", [])
    episodic_shards = result.get("episodic_shards", [])
    
    if not semantic_rules and not episodic_shards:
        return _empty_recall_notice()
        
    output = ["=== NOUGENSHARDS DUAL-SYSTEM RECALL PACKET ==="]
    
    if semantic_rules:
        output.append("\n-- SYSTEM 2: SEMANTIC INVARIANTS (GLOBAL RULES) --")
        for r in semantic_rules:
            db_tag = f" (db {r['_db_index']})" if r.get('_db_index') else ""
            output.append(f"* [{r['subject']}] {r['predicate']} [Confidence: {r['confidence_score']:.1f}]{db_tag}")
            
    if episodic_shards:
        output.append("\n-- SYSTEM 1: EPISODIC STORAGE (RECENT CONTEXT) --")
        for s in episodic_shards:
            db_idx = s.get("_db_index")
            db_tag = f" (db {db_idx})" if db_idx is not None else ""
            output.append(f"--- RECORD #{s['id']}{db_tag} [Score: {s.get('utility_score_tripartite', 0.0):.2f}] ---")
            output.append(f"When: {format_shard_when(s.get('timestamp'))}")
            output.append(f"Title: {s['title']}\n{s['content']}\n")
            
    output.append("\nAnghkooey — NouGenShards remembers.")
    return "\n".join(output)
