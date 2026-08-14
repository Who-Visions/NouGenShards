"""
Valerion Core — NouGenShards Memory Substrate.
Logic: SQLite + FTS5 + BM25 + Trigram (n-gram) + Vector Embeddings + Weighted Relevance Reranking.
Architecture: Valerion 21-step cognitive loop. Weighted multi-signal relevance blend (BM25 + semantic + usefulness prior).
"""
# pylint: disable=duplicate-code
import hashlib
import json
import logging
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

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

    # Sensitivity classification (schema v2): 'normal' bodies stay plaintext,
    # 'private'/'secret' bodies are AES-GCM encrypted by private_vault before
    # they are written. enc=1 marks a row whose content column is ciphertext.
    try:
        cursor.execute("ALTER TABLE shards ADD COLUMN sensitivity TEXT DEFAULT 'normal';")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE shards ADD COLUMN enc INTEGER DEFAULT 0;")
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


def compression_density(content: str) -> float:
    """Local, offline density estimate: gzip ratio as a proxy for surprisal.

    Exposed separately from `calculate_contrastive_perplexity` so bulk callers
    can opt out of the per-item LLM round trip. Scoring an import of six
    figures of records through a model is not viable — each unreachable
    provider costs a connection timeout, and even a live local model would
    serialize the whole ingest behind inference.
    """
    if not content:
        return 1.0
    import zlib
    try:
        compressed_len = len(zlib.compress(content.encode('utf-8')))
        raw_len = len(content.encode('utf-8'))
        compression_ratio = compressed_len / max(1, raw_len)
        return float(min(1.0, max(0.1, compression_ratio * 1.5)))
    except Exception:
        return 0.5


def _llm_scoring_enabled() -> bool:
    """Whether to spend a model call scoring density. Off unless asked.

    A named function rather than an inline check because the test-environment
    guard used to be inline, which made the opt-in path impossible to exercise:
    "pytest" is always in sys.modules under a test run, so the function
    returned the fallback before reaching anything worth testing. A guard that
    makes its own feature untestable is a guard nobody can verify.
    """
    import sys
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return (os.environ.get("NOUGEN_DENSITY_LLM") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def calculate_contrastive_perplexity(content: str) -> float:
    """Estimates information density / contrastive perplexity using local Ollama or OpenRouter."""
    if not content:
        return 1.0

    # Heuristic compression-based fallback: ratio of gzip size to raw size.
    # (A Lidstone bigram SELF-perplexity per docs/theory/n-gram-topologies.md
    # §9 was evaluated and rejected here: without a reference corpus to fit,
    # self-perplexity is degenerate - both boilerplate AND short novel text
    # have near-deterministic self-transitions and score ~1. The doc's metric
    # needs a fitted reference model; revisit if a vault-wide corpus model is
    # ever built.)
    fallback_score = compression_density(content)

    if not _llm_scoring_enabled():
        return fallback_score

    # LLM scoring is OPT-IN, because it was costing 48 seconds per capture.
    #
    # Measured on this box: the SQLite write is 0.03s and compression_density
    # above is 0.0000s; the whole 48s was one local Ollama inference to produce
    # a single float. Nine shards took six minutes of wall time for nine local
    # writes, and it never failed — it just waited, which is why nobody caught
    # it. A memory system that takes a minute to remember something does not
    # get used at the moment it matters.
    #
    # Nothing is lost by defaulting off. The fallback already fires on every
    # box without Ollama running, so the vault ALREADY holds a mix of
    # LLM-derived and gzip-derived scores depending on which machine happened
    # to capture — the metric was never comparable across records. Deterministic
    # and instant everywhere is strictly better than slow and inconsistent.
    #
    # Set NOUGEN_DENSITY_LLM=1 to restore model scoring; it is then bounded by
    # NOUGEN_DENSITY_TIMEOUT seconds (default 5) so it can degrade rather than
    # hang. The bound is enforced by running the scorer on a daemon thread and
    # abandoning it — no chat() in models_client takes a timeout argument, so a
    # deadline checked only between attempts would gate whether a call STARTS
    # while doing nothing about one already in flight. That version was written
    # first and measured at 48s with the budget set to 3.
    try:
        _budget = float(os.environ.get("NOUGEN_DENSITY_TIMEOUT") or 5.0)
    except ValueError:
        _budget = 5.0

    import threading
    _result: list = []

    def _score() -> None:
        try:
            _result.append(_llm_density(content))
        except Exception:
            pass

    _worker = threading.Thread(target=_score, daemon=True)
    _worker.start()
    _worker.join(_budget)
    return _result[0] if _result else fallback_score


def _llm_density(content: str) -> Optional[float]:
    """Ask a model for a density score. Returns None if no provider answers.

    Split out of calculate_contrastive_perplexity so the caller can abandon it
    on a deadline: it runs on a daemon thread, and a thread that outlives its
    budget is dropped rather than waited on.
    """

    # Try local Ollama first
    try:
        from .models_client import get_best_available_client
        client = get_best_available_client()
        if client and client.is_alive():
            models = client.list_models()
            # Preference order is configuration, not a constant: take the first
            # preferred tag the daemon actually reports, else whatever it has.
            preferred = [
                m.strip()
                for m in os.getenv(
                    "NOUGEN_DENSITY_MODELS", "gemma4:e2b,gemma4:e4b,gemma4:31b-cloud"
                ).split(",")
                if m.strip()
            ]
            best_model = next(
                (p for p in preferred if p in models),
                models[0] if models else None,
            )
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

    # No provider answered; the caller substitutes its own fallback.
    return None


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


#: Count of shards written without an embedding since process start. Read by
#: tooling that wants to assert the "born recallable" invariant actually held.
EMBED_AT_CAPTURE_MISSES = 0


def _embed_at_capture_enabled() -> bool:
    return os.environ.get("NOUGEN_EMBED_AT_CAPTURE", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _embed_for_capture(title: str, content: str) -> Optional[List[float]]:
    """Embed at write time so a shard is recallable the moment it exists.

    This closes the gap that let ~46% of the vault accumulate embedding=NULL:
    embedding only ever happened if a caller passed a vector in or if the
    backfill tool was run later, so coverage tracked ollama's uptime rather than
    anything about the shards. A miss here is NON-FATAL -- losing the shard
    would be worse than losing its vector -- but it is counted and logged rather
    than swallowed, because silent degradation is what hid this for two months.
    """
    global EMBED_AT_CAPTURE_MISSES  # pylint: disable=global-statement
    model = os.environ.get("NOUGEN_EMBED_MODEL", "nomic-embed-text")
    try:
        timeout = int(os.environ.get("NOUGEN_EMBED_TIMEOUT", "10"))
    except ValueError:
        timeout = 10
    try:
        from .embedding_backfill import embed as _embed  # local import: optional dep path
        vec = _embed(((title or "") + "\n" + (content or ""))[:4000], model, timeout=timeout)
    except Exception as exc:  # pylint: disable=broad-except
        vec = None
        logger.debug("embed-at-capture raised: %s", exc)
    if not vec:
        EMBED_AT_CAPTURE_MISSES += 1
        logger.warning(
            "shard written WITHOUT embedding (model=%s, miss #%d) -- semantic recall "
            "will not see it until backfill runs; is ollama up?",
            model, EMBED_AT_CAPTURE_MISSES,
        )
        return None
    return vec


def capture(event_type: str, title: str, content: str,
            tags: Optional[List[str]] = None, embedding: Optional[List[float]] = None,
            domain_key: Optional[str] = None, density_score: Optional[float] = None,
            sensitivity: Optional[str] = None) -> bool:
    """Saves a unit of experience (Module 5: Extract Invariants).

    `sensitivity` is 'normal' (default, plaintext -- the existing corpus),
    'private', or 'secret'. Private and secret bodies are AES-256-GCM encrypted
    by private_vault before they reach SQLite, so personal-scope material
    (finances, health, identity documents) is not readable from the DB file.
    Titles and tags stay plaintext: they are the only handle recall has on an
    encrypted shard, so keep identifying detail out of them.
    """
    from . import private_vault as _pv  # pylint: disable=import-outside-toplevel
    sensitivity = _pv.normalize_sensitivity(sensitivity)
    if not domain_key:
        domain_key = resolve_domain_from_path()

    if density_score is None:
        density_score = calculate_contrastive_perplexity(content)

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

        # Born recallable: if the caller did not supply a vector, make one now.
        if embedding is None and _embed_at_capture_enabled():
            embedding = _embed_for_capture(title, content)

        emb_blob = None
        if embedding:
            arr = np.array(embedding, dtype=np.float32)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            emb_blob = sqlite3.Binary(arr.tobytes())

        tags_str = json.dumps(tags or [])
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Encrypt LAST, immediately before the write: the dedup hash, the blob
        # gate, the redactor and the embedder all need the real text, and the
        # AFTER INSERT trigger that feeds shards_fts reads new.content -- so
        # encrypting here is also what keeps the plaintext body out of the
        # full-text index. Private shards are therefore findable by title and
        # tag, not by body text. That tradeoff is the point.
        stored_content = content
        enc_flag = 0
        if _pv.should_encrypt(sensitivity):
            stored_content = _pv.encrypt_text(content)
            enc_flag = 1

        conn = get_connection(target_idx)
        try:
            cursor = conn.execute("""
                INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash, embedding, domain_key, density_score, sensitivity, enc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, event_type, title, stored_content, tags_str, fhash, emb_blob, domain_key, density_score, sensitivity, enc_flag))
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

# Stage-2 cross-encoder reranker (Tier-1 elevation). 2026 SOTA: a hybrid->rerank
# two-stage pipeline lifts Recall@5 ~+17% / MRR ~+40% over RRF alone. Off by
# default and lazy-loaded, so this is a no-op (zero new deps) until activated:
#   NOUGEN_RERANK=1   pip install FlagEmbedding   (bge-reranker-v2-m3 ~2.27GB)
RERANK_ENABLED = os.environ.get("NOUGEN_RERANK", "0") == "1"
RERANK_MODEL = os.environ.get("NOUGEN_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_CANDIDATES = int(os.environ.get("NOUGEN_RERANK_CANDIDATES", "60"))
_RERANKER = None  # process-cached reranker handle

#: Per-DB ceiling on rows the fuzzy lane will n-gram (see _keyword_retrieve).
#: The lane has no index to lean on — it scores rows in Python — so on a large
#: vault its cost is the whole vault, per query, per retrieval pass. The bound
#: takes the highest-utility rows first, which is the same ordering the LIKE
#: lane already prefers. Raise it to trade latency for fuzzy recall; set 0 for
#: the old unbounded behavior.
FUZZY_MAX_ROWS = int(os.environ.get("NOUGEN_FUZZY_MAX_ROWS", "4000")) or (1 << 62)

#: When the fuzzy lane is allowed to run at all.
#:   "empty"       - only when the exact lanes found NOTHING anywhere (default)
#:   "underfilled" - whenever the exact lanes returned fewer than `limit`
#: "underfilled" is what the lane did originally. On a small vault the two agree,
#: because a query with few shards to find usually finds none. On a large one they
#: diverge hard: most queries return *some* exact hits but nowhere near `limit`
#: (candidate_limit is 20), so "underfilled" fired on nearly every query and paid
#: a Python n-gram sweep to produce rows the exact/fuzzy tiering then dropped.
#: "empty" targets what the lane is actually for — a query whose spelling missed.
FUZZY_TRIGGER = os.environ.get("NOUGEN_FUZZY_TRIGGER", "empty").strip().lower()


def _fuzzy_should_run(results: list, limit: int) -> bool:
    """Whether the deferred fuzzy lane runs, per FUZZY_TRIGGER."""
    if FUZZY_TRIGGER == "underfilled":
        return len(results) < limit
    return not results

def _temporal_decay(ts_str: Optional[str], now: datetime) -> float:
    """Half-life decay (30 days) of a shard timestamp against a fixed reference
    clock, floored at 0.1.

    `now` MUST be captured once per ranking pass and shared by every item in
    that pass. Calling datetime.now() per item made ranking sensitive to I/O
    stalls mid-scan: a slow history write between scoring two items aged the
    later one by the stall duration, nondeterministically flipping the order
    of shards captured milliseconds apart (flaky on fast CI runners).
    """
    if not ts_str:
        return 1.0
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (now - dt).total_seconds() / 86400.0
        return max(0.1, 0.5 ** (age_days / 30.0))
    except Exception:
        return 1.0


def _process_fts_result(row, db_index, query_embedding, now: datetime):
    """Helper to score a single FTS result via the weighted relevance blend."""
    item = hydrate(dict(row))
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
    decayed_utility = item["utility_score"] * _temporal_decay(item.get("timestamp"), now)

    # 4. Final relevance: a weighted blend of the likelihood signal and the decayed utility score
    item["final_score"] = (likelihood * WEIGHT_LIKELIHOOD) + (decayed_utility * WEIGHT_PRIOR)
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

    return " ".join('"' + t.replace('"', '""') + '"' for t in tokens)


def _keyword_retrieve(query: str, limit: int = 20, query_embedding: Optional[List[float]] = None,
                      domain_key: str = "global") -> list:
    """Scans for keyword matches using FTS5 (with LIKE fallback)."""
    from . import history, ngram  # pylint: disable=import-outside-toplevel

    # One reference clock for the whole scan (see _temporal_decay).
    query_now = datetime.now(timezone.utc)
    results = []
    missed_dbs = []  # DBs where both exact lanes missed; fed to the fuzzy pass below
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            fts_worked = False
            db_hits = 0
            fts_query = _build_fts_match_query(query)
            if fts_query is not None:
                # The try guards ONLY the SQL: sqlite3.OperationalError here
                # means "FTS unavailable, use the LIKE fallback". Row processing
                # happens outside it so an unrelated error can't leave partially
                # appended FTS rows in `results` and then double-append the same
                # shards via the fallback (which scrambled retrieval ordering).
                res = None
                try:
                    # domain_key None/"*" => search ALL domains (whole brain), not one bucket.
                    dom_clause = "" if domain_key in (None, "*") else "s.domain_key = ? AND "
                    dom_params = () if domain_key in (None, "*") else (domain_key,)
                    cursor = conn.execute(f"""
                        SELECT s.id, s.timestamp, s.title, s.content, s.utility_score,
                               s.embedding, s.tags, s.domain_key, s.density_score, bm25(shards_fts) as bm25_score
                        FROM shards s JOIN shards_fts ON s.id = shards_fts.rowid
                        WHERE {dom_clause}shards_fts MATCH ?
                        ORDER BY bm25_score ASC, s.id ASC LIMIT ?
                    """, (*dom_params, fts_query, limit))
                    res = cursor.fetchall()
                except sqlite3.OperationalError:
                    res = None
                if res:
                    for row in res:
                        history.log_event(row["id"], i, "ACCESSED")
                        results.append(_process_fts_result(row, i, query_embedding, query_now))
                    fts_worked = True

            if not fts_worked:
                history.log_event(0, i, "SEARCH_FALLBACK", metadata={"query": query})
                
                like_query = f"%{query}%"
                dom_clause = "" if domain_key in (None, "*") else "domain_key = ? AND "
                dom_params = () if domain_key in (None, "*") else (domain_key,)
                cursor = conn.execute(f"""
                    SELECT id, timestamp, title, content, utility_score, embedding, tags, domain_key, density_score
                    FROM shards
                    WHERE {dom_clause}(title LIKE ? OR content LIKE ?)
                    ORDER BY utility_score DESC, id ASC LIMIT ?
                """, (*dom_params, like_query, like_query, limit))
                for row in cursor:
                    item = hydrate(dict(row))
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

                    decayed_utility = item["utility_score"] * _temporal_decay(item.get("timestamp"), query_now)
                    item["final_score"] = (likelihood * 0.5) + (decayed_utility * 0.5)
                    results.append(item)
                    db_hits += 1

            # Fuzzy lane is DEFERRED, not run here: note the miss and move on.
            # See the second pass below for why.
            if not fts_worked and db_hits == 0:
                missed_dbs.append(i)
        finally:
            conn.close()

    # Fuzzy lane (docs/theory/n-gram-topologies.md §8.2): for DBs where BOTH
    # exact lanes missed, retry with fastText-style character trigram Dice
    # similarity. Substring matchers (LIKE, trigram FTS) can't bridge typos or
    # morphological variants ("automaton" vs "automation"); set similarity can.
    # Fuzzy likelihood is scaled by the Dice score (< exact's 0.5) so exact hits
    # always outrank it.
    #
    # This runs AFTER every DB has been scanned, and only when the exact lanes
    # came up short, because the final sort tiers every exact hit above every
    # fuzzy hit and then truncates to `limit`. Once `limit` exact hits exist,
    # each fuzzy hit is computed and then discarded by that truncation — the
    # output is bit-identical either way.
    #
    # It was previously inline, per DB, on the per-DB miss path. That reasoned
    # about a miss as if it were rare, but a query is only ever "exact" in the
    # DBs that happen to hold its shards: a term living in 1 of 9 DBs sent the
    # other 8 into an unbounded `SELECT ... FROM shards` (no LIMIT), hydrating
    # and n-gramming ~134k rows in Python. That was 40s of a 50s federated
    # /search — spent, then thrown away, on every query that matched anything.
    if _fuzzy_should_run(results, limit) and missed_dbs:
        q_grams = ngram.char_ngrams(query)
        if q_grams:
            dom_params = () if domain_key in (None, "*") else (domain_key,)
            where = "WHERE domain_key = ?" if dom_params else ""
            for i in missed_dbs:
                conn = get_connection(i)
                try:
                    # Score against a cheap projection: the similarity probe only
                    # ever reads title + the first 256 chars of content, so there
                    # is no reason to pull full content and embedding blobs for
                    # every row. Survivors are re-fetched in full below.
                    cursor = conn.execute(f"""
                        SELECT id, substr(content, 1, 256) AS probe_content, title
                        FROM shards {where}
                        ORDER BY utility_score DESC, id ASC
                        LIMIT ?
                    """, (*dom_params, FUZZY_MAX_ROWS))
                    scored = []
                    scanned = 0
                    for row in cursor:
                        scanned += 1
                        probe = f"{row['title'] or ''} {row['probe_content'] or ''}"
                        sim = ngram.overlap_coefficient(q_grams, ngram.char_ngrams(probe))
                        if sim >= ngram.FUZZY_MIN_OVERLAP:
                            scored.append((sim, row["id"]))
                    # No silent caps: say so when the bound actually bit, so a
                    # thin fuzzy result is never mistaken for "nothing similar".
                    if scanned >= FUZZY_MAX_ROWS:
                        logger.info(
                            "fuzzy lane capped on db%d: scanned %d of its shards "
                            "(highest utility_score first); raise NOUGEN_FUZZY_MAX_ROWS to widen",
                            i, scanned)
                    if not scored:
                        continue
                    # Rank on (sim, id) exactly as the old code did before its
                    # own [:limit], so the same rows survive; only then pay for
                    # the full rows.
                    scored.sort(key=lambda t: (-t[0], t[1]))
                    keep = scored[:limit]
                    sim_by_id = {rid: sim for sim, rid in keep}
                    placeholders = ",".join("?" * len(keep))
                    full = conn.execute(f"""
                        SELECT id, timestamp, title, content, utility_score, embedding, tags, domain_key, density_score
                        FROM shards WHERE id IN ({placeholders})
                    """, tuple(rid for _, rid in keep)).fetchall()
                    fuzzy = []
                    for row in full:
                        item = hydrate(dict(row))
                        sim = sim_by_id[item["id"]]
                        item["_db_index"] = i
                        item["_fuzzy"] = True
                        decayed_utility = item["utility_score"] * _temporal_decay(item.get("timestamp"), query_now)
                        item["final_score"] = (sim * 0.5) + (decayed_utility * 0.5) * sim
                        fuzzy.append(item)
                    # `IN (...)` does not preserve order; restore the ranking the
                    # old inline sort produced before appending.
                    fuzzy.sort(key=lambda x: (-x["final_score"], x["id"]))
                    for item in fuzzy:
                        history.log_event(item["id"], i, "ACCESSED")
                        results.append(item)
                finally:
                    conn.close()

    # Tiered ordering: every exact hit (FTS/LIKE) outranks every fuzzy hit,
    # regardless of raw score - the lanes' score scales are not comparable
    # (trigram-FTS bm25 magnitudes are tiny, so a weighted exact score can sit
    # below a strong fuzzy similarity). Score is rounded so sub-epsilon
    # temporal-decay jitter can't reorder near-ties; then (_db_index, id) ASC
    # pins true ties so identical queries never reorder run-to-run.
    results.sort(key=lambda x: (1 if x.get("_fuzzy") else 0,
                                -round(x.get("final_score", 0.0), 6),
                                x.get("_db_index", 0),
                                x.get("id", 0)))
    return results[:limit]


def _vector_retrieve(query_embedding: Optional[List[float]], limit: int = 20,
                     domain_key: str = "global") -> list:
    """Scans for semantic vector matches independent of FTS."""
    if query_embedding is None:
        return []

    from . import history # pylint: disable=import-outside-toplevel

    # One reference clock for the whole scan (see _temporal_decay).
    query_now = datetime.now(timezone.utc)
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
                item = hydrate(dict(row))
                item["_db_index"] = i
                
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

                decayed_utility = item["utility_score"] * _temporal_decay(item.get("timestamp"), query_now)
                item["final_score"] = (sem_score * WEIGHT_LIKELIHOOD) + (decayed_utility * WEIGHT_PRIOR)
                results.append(item)
        finally:
            conn.close()

    # Deterministic order: score DESC (rounded so sub-epsilon temporal-decay
    # jitter doesn't reorder near-ties run-to-run), then (_db_index, id) ASC.
    results.sort(key=lambda x: (-round(x.get("final_score", 0.0), 6), x.get("_db_index", 0), x.get("id", 0)))
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
    # One reference clock for the whole merge (see _temporal_decay).
    merge_now = datetime.now(timezone.utc)
    for key, item in item_map.items():
        consensus_score = rrf_scores[key]
        decayed_utility = item.get("utility_score", 1.0) * _temporal_decay(item.get("timestamp"), merge_now)
        item["final_score"] = consensus_score * (0.7 + (decayed_utility * 0.3))
        merged.append(item)

    merged.sort(key=lambda x: (-round(x["final_score"], 6), x.get("_db_index", 0), x.get("id", 0)))
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

    candidate_limit = max(limit * 2, 20)

    def run_parallel_retrieval(active_domain: str) -> list:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_keyword = executor.submit(
                _keyword_retrieve, query, candidate_limit, query_embedding, active_domain
            )
            future_vector = executor.submit(
                _vector_retrieve, query_embedding, candidate_limit, active_domain
            )
            
            keyword_results = future_keyword.result()
            vector_results = future_vector.result()
            
        return reciprocal_rank_fusion([keyword_results, vector_results], k=60)

    all_results = run_parallel_retrieval(domain_key)
    
    # Fallback: if the domain-scoped pass found nothing, sweep the ENTIRE brain
    # (all domain_keys). Without this, recall stays siloed to one bucket
    # (e.g. 'global' = <2% of shards) and misses the other 47k+ shards.
    if not all_results and domain_key != "*":
        all_results = run_parallel_retrieval("*")

    # Stage 2: cross-encoder rerank the top RRF candidates (no-op unless enabled).
    if RERANK_ENABLED:
        all_results = rerank(query, all_results[:RERANK_CANDIDATES], len(all_results))

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

    # One reference clock for the whole scoring pass (see _temporal_decay).
    score_now = datetime.now(timezone.utc)
    for item in all_results:
        raw_rel = item.get("rerank_score", item.get("final_score", 0.5))
        if rel_span > 0:
            relevance = 0.1 + 0.9 * ((raw_rel - min_rel) / rel_span)
        else:
            relevance = 1.0 if raw_rel > 0 else 0.5

        decay = _temporal_decay(item.get("timestamp"), score_now)
        density = item.get("density_score", 1.0)

        u_shard = (1.0 * relevance) * decay * density
        item["utility_score_tripartite"] = u_shard
        scored_results.append(item)
    
    # Sort candidates by the tripartite score. Round the score so sub-epsilon
    # temporal-decay jitter can't reorder near-ties run-to-run; exact ties then
    # break deterministically by (_db_index, id).
    scored_results.sort(
        key=lambda x: (-round(x["utility_score_tripartite"], 6), x.get("_db_index", 0), x.get("id", 0)))
    
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
        
    # Lost in the Middle Mitigation (interleave)
    reordered = lost_in_the_middle_reorder(surviving[:limit])
    return reordered


def hydrate(item: Optional[dict]) -> Optional[dict]:
    """Decrypt an encrypted shard body on the way out of the DB.

    Applied at every row->dict boundary so callers never have to know whether a
    shard was stored private. Plaintext passes straight through, which keeps a
    mixed corpus working. If the key is unavailable (wrong Windows profile, no
    recovery key set) the row is returned with a placeholder body rather than
    raising: one unreadable shard must not take down a whole recall.
    """
    if not item:
        return item
    body = item.get("content")
    if not isinstance(body, str):
        return item
    try:
        from . import private_vault as _pv  # pylint: disable=import-outside-toplevel
        if _pv.is_encrypted(body):
            item["content"] = _pv.decrypt_text(body)
    except Exception as exc:  # key missing or tampered ciphertext
        item["content"] = f"[encrypted shard -- unavailable: {type(exc).__name__}]"
    return item


def get_shard_by_id(shard_id: int, db_index: int):
    """Retrieves a specific shard by ID from a specific DB index."""
    if not get_db_path(db_index).exists(): return None
    conn = get_connection(db_index)
    try:
        row = conn.execute("SELECT * FROM shards WHERE id = ?", (shard_id,)).fetchone()
        return hydrate(dict(row)) if row else None
    finally:
        conn.close()

def locate_shard(shard_id: int) -> List[int]:
    """Returns every cluster DB index holding a shard with this id.

    Ids are per-DB AUTOINCREMENT, so an id is only unique together with its
    database. A caller that wants to mutate a shard must resolve the ambiguity
    before writing, not after — see mark_shard's db_index parameter.
    """
    found = []
    for i in range(1, MAX_DB_COUNT + 1):
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            if conn.execute("SELECT 1 FROM shards WHERE id = ?", (shard_id,)).fetchone():
                found.append(i)
        except sqlite3.Error:
            continue
        finally:
            conn.close()
    return found


def get_shard_title(shard_id: int, db_index: int) -> Optional[str]:
    """Title of one shard, for disambiguating an id that spans several DBs."""
    if not get_db_path(db_index).exists():
        return None
    conn = get_connection(db_index)
    try:
        row = conn.execute("SELECT title FROM shards WHERE id = ?", (shard_id,)).fetchone()
        return row["title"] if row else None
    except sqlite3.Error:
        return None
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


def compile_recall_packet(shards: list) -> str:
    """Synthesis of retrieved experience into a coherent context packet (Module 18)."""
    if not shards:
        return "<!-- NO RELEVANT MEMORY RECALLED -->"
    output = ["=== NOUGENSHARDS RECALL PACKET [BAYESIAN SYNTHESIS] ==="]
    for s in shards:
        # Surface the source DB so callers can target this exact shard in the
        # 9-DB grid (mark_utility / link_shards / recall_related take db_index).
        db_idx = s.get("_db_index")
        db_tag = f" (db {db_idx})" if db_idx is not None else ""
        # Federated results come from external DBs and remote cloud nodes whose
        # records may be missing fields; degrade gracefully instead of crashing
        # the whole recall on one malformed shard.
        shard_id = s.get("id", "?")
        try:
            score = f"{float(s['final_score']):.2f}" if s.get("final_score") is not None else "n/a"
        except (TypeError, ValueError):
            score = "n/a"
        output.append(f"--- RECORD #{shard_id}{db_tag} [Score: {score}] ---")
        output.append(f"When: {format_shard_when(s.get('timestamp'))}")
        output.append(f"Title: {s.get('title', '(untitled)')}\n{s.get('content', '')}\n")
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
                    ORDER BY confidence_score DESC, id ASC
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
        return "<!-- NO RELEVANT MEMORY RECALLED -->"
        
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
