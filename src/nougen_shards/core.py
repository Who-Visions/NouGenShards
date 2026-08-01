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
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np

# Ranking-policy modules. Both are leaf modules (provenance imports nothing from
# the package; attribution defers its history import into function bodies), so
# importing them here cannot create a cycle.
from . import attribution
from . import provenance

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
# Marker tag for a shard written without a vector. FTS insertion is enforced
# structurally (triggers), but embedding CANNOT be — it needs a reachable embed
# model — so the miss is recorded rather than silent: tagged here, counted by
# tools/vault_drift_detector.py, swept by embedding_backfill.
EMBED_PENDING_TAG = os.environ.get("NOUGEN_EMBED_PENDING_TAG", "embedding:pending")

# Vault location resolves env -> user config -> cwd-local -> home fallback
# (Rule 0.2). The config tier matters for long-lived hosts (the MCP server) that
# are launched by a supervisor whose environment nobody audits: without it, a
# stale or absent NOUGEN_VAULT_DIR silently points recall at an empty store and
# every miss looks like a healthy no-match. VAULT_SOURCE records which tier won
# so callers can report provenance instead of guessing.
NOUGEN_CONFIG_PATH = Path(
    os.environ.get("NOUGEN_CONFIG", str(Path.home() / ".nougen" / "config.json"))
)


def _config_vault_dir() -> Optional[str]:
    """Read vault_dir out of the user config, or None if unusable."""
    try:
        with open(NOUGEN_CONFIG_PATH, "r", encoding="utf-8") as handle:
            value = json.load(handle).get("vault_dir")
    except (OSError, ValueError, AttributeError):
        return None
    return str(value) if value else None


def _resolve_vault_dir() -> tuple[str, str]:
    """Returns (vault_dir, source_tier)."""
    env_dir = os.environ.get("NOUGEN_VAULT_DIR")
    if env_dir:
        return env_dir, "env:NOUGEN_VAULT_DIR"
    config_dir = _config_vault_dir()
    if config_dir:
        return config_dir, f"config:{NOUGEN_CONFIG_PATH}"
    local_vault = Path(".vault")
    if local_vault.exists() and local_vault.is_dir():
        return str(local_vault), "cwd:.vault"
    return str(Path.home() / ".nougen" / "shards"), "fallback:~/.nougen/shards"


_vault_dir, VAULT_SOURCE = _resolve_vault_dir()

GLOBAL_DIR = Path(_vault_dir)


def vault_report() -> dict:
    """Resolved vault provenance + population, for surfacing on every recall.

    HARDENING invariant 4: an empty result is not a healthy no-match. Any recall
    lane that can return nothing must also say which store it looked in and how
    populated that store is, so a misrouted vault can never fail silently.
    """
    dbs = sorted(GLOBAL_DIR.glob("nougen_shards_*.db")) if GLOBAL_DIR.exists() else []
    total = 0
    for db in dbs:
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=DB_TIMEOUT) as conn:
                total += conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
        except sqlite3.Error:
            continue
    return {
        "vault_dir": str(GLOBAL_DIR),
        "source": VAULT_SOURCE,
        "exists": GLOBAL_DIR.exists(),
        "db_count": len(dbs),
        "shard_count": total,
    }

# ---------------------------------------------------------------------------
# Canonical ingest-scope globs (single source of truth).
#
# The ingester (shard_vault_files.py) and the drift detector
# (tools/vault_drift_detector.py) MUST agree on what is out of scope. When they
# disagree, every file the ingester refuses but the detector still counts shows
# up as UNEXPECTED drift on every run, forever -- a cry-wolf alarm no operator
# can clear. Both tools resolve these names instead of restating the literals,
# so the invariant holds structurally:
#
#     ingest_exclude  ==  drift_exclude  UNION  drift_backlog
#
# Two distinct families, distinct semantics:
#
# NOISE  -- never memory, at all. Editor/tooling artifacts. The ingester skips
#   them and the drift detector drops them from its accounting entirely
#   (files_excluded), because they are not a backlog waiting to be drained.
#   `User/History` is VS Code's local-history store: autosave snapshots of files
#   already tracked elsewhere. Ingesting them floods recall with near-duplicate
#   revisions of the same source file, roughly one shard per autosave snapshot.
#   Matched by fnmatch against both the
#   basename and the vault-relative POSIX path, and fnmatch's `*` spans "/", so
#   the prefix form below covers the whole subtree at any depth.
#
# BACKLOG -- legitimately memory, deliberately deferred. The ingester skips
#   them under a forward-only policy when embedding capacity is the bottleneck,
#   but the detector classifies them as EXPECTED-missing
#   rather than ignoring them, so the backlog stays visible and countable.
#
# Env overrides (NOUGEN_SHARD_EXCLUDE_GLOBS / NOUGEN_DRIFT_EXCLUDE_GLOBS /
# NOUGEN_DRIFT_BACKLOG_GLOBS) still win; these are the logged fallbacks that
# make the safe behaviour hold with no env var set.
# ---------------------------------------------------------------------------
DEFAULT_NOISE_EXCLUDE_GLOBS = "User/History/*"
DEFAULT_BACKLOG_GLOBS = "arxiv_*.md;intelligence_shard_arxiv_*.md"
DEFAULT_INGEST_EXCLUDE_GLOBS = ";".join(
    (DEFAULT_NOISE_EXCLUDE_GLOBS, DEFAULT_BACKLOG_GLOBS)
)

# Read-only guard for federated reads of SIBLING vaults (see federation.py).
# When set, no schema work (init_db) and no journal-mode change may touch the
# store currently under GLOBAL_DIR — a secondary store is read in place and is
# never migrated, upgraded, or merged. Toggled only via
# federation.read_only_vault(); it is never persisted.
VAULT_READONLY = False


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
    # Never rewrite a foreign vault's journal mode while federating a read.
    if not VAULT_READONLY:
        conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


_INITIALIZED_DBS = set()

# init_db() is a check-then-act on _INITIALIZED_DBS followed by a
# DROP TRIGGER / CREATE TRIGGER pair. Without a lock, concurrent capture()
# threads all pass the membership check, then interleave: thread A's CREATE
# lands between thread B's DROP and CREATE, and B dies with
# "trigger shards_ai already exists".
# It is rare per file and certain at scale: any multi-threaded ingest run will
# hit it eventually, and a handful of failures is enough to pin the drift alarm
# permanently red.
_INIT_LOCK = threading.Lock()


def init_db(index: int = 1):
    """Initializes the substrate schema (Module 6: Copy Successful Topology).

    Idempotent, but re-running CREATE TABLE / DROP+CREATE TRIGGER on every
    capture dominates bulk-ingestion cost — so each (vault, index) pair is
    initialized once per process. Keyed by vault dir because tests and tools
    repoint NOUGEN_VAULT_DIR/GLOBAL_DIR mid-process.
    """
    if VAULT_READONLY:
        # Federated read of a sibling store: schema is whatever that store has.
        return
    key = (str(GLOBAL_DIR), index)
    if key in _INITIALIZED_DBS:
        return
    with _INIT_LOCK:
        # Double-checked: another thread may have finished while we waited.
        if key in _INITIALIZED_DBS:
            return
        _init_db_locked(index, key)


# The canonical FTS sync triggers — ONE definition, used both to install them
# and to decide whether an install is even needed.
#
# The index must stay coherent on every write, not just inserts: without the
# delete/update triggers, edited or removed shards leave stale rows that keep
# matching searches. External-content FTS5 needs the special 'delete' command
# rows to retract a row before re-indexing it.
_FTS_TRIGGER_SQL = {
    "shards_ai": (
        "CREATE TRIGGER shards_ai AFTER INSERT ON shards BEGIN "
        "INSERT INTO shards_fts(rowid, title, content) "
        "VALUES (new.id, new.title, new.content); END"
    ),
    "shards_ad": (
        "CREATE TRIGGER shards_ad AFTER DELETE ON shards BEGIN "
        "INSERT INTO shards_fts(shards_fts, rowid, title, content) "
        "VALUES ('delete', old.id, old.title, old.content); END"
    ),
    "shards_au": (
        "CREATE TRIGGER shards_au AFTER UPDATE ON shards BEGIN "
        "INSERT INTO shards_fts(shards_fts, rowid, title, content) "
        "VALUES ('delete', old.id, old.title, old.content); "
        "INSERT INTO shards_fts(rowid, title, content) "
        "VALUES (new.id, new.title, new.content); END"
    ),
}


def _norm_sql(sql: str) -> str:
    """Whitespace-insensitive comparison key for a stored trigger definition."""
    return " ".join((sql or "").split()).rstrip(";").strip()


def fts_triggers_current(conn) -> bool:
    """True when this DB already carries exactly the canonical FTS triggers."""
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND name IN "
        "('shards_ai', 'shards_ad', 'shards_au')"
    ).fetchall()
    have = {r[0]: _norm_sql(r[1]) for r in rows}
    return have == {n: _norm_sql(s) for n, s in _FTS_TRIGGER_SQL.items()}


def count_unindexed(conn) -> int:
    """Rows in `shards` that the FTS index does not actually contain.

    Read via the fts5 `_docsize` shadow table, which is the ONLY honest measure:
    `SELECT count(*) FROM shards_fts` on an external-content table is answered
    from the CONTENT table, so it always equals the row count and can never
    reveal a gap. Every "row count == FTS count, we're in sync" report built on
    that query is vacuous — which is exactly how this class of drift hides.
    Returns -1 when the shadow table is unavailable (schema older/other shape).
    """
    try:
        return int(conn.execute(
            "SELECT count(*) FROM shards s WHERE NOT EXISTS "
            "(SELECT 1 FROM shards_fts_docsize d WHERE d.id = s.id)"
        ).fetchone()[0])
    except sqlite3.Error:
        return -1


def _reindex_missing_rows(conn) -> int:
    """Re-index every row the FTS index is missing. Caller holds the write lock."""
    missing = count_unindexed(conn)
    if missing < 0:
        # No shadow table to diff against: fall back to the full FTS5 rebuild.
        conn.execute("INSERT INTO shards_fts(shards_fts) VALUES('rebuild')")
        return -1
    if missing:
        conn.execute(
            "INSERT INTO shards_fts(rowid, title, content) "
            "SELECT s.id, s.title, s.content FROM shards s WHERE NOT EXISTS "
            "(SELECT 1 FROM shards_fts_docsize d WHERE d.id = s.id)"
        )
    return missing


def _ensure_fts_triggers(conn) -> bool:
    """Install the FTS sync triggers without ever leaving them uninstalled.

    ROOT CAUSE this replaces (measured and reproduced): the previous
    implementation ran `DROP TRIGGER IF EXISTS` x3 followed by `CREATE TRIGGER`
    x3 as bare statements on every DB init. Python's sqlite3 executes DDL in
    AUTOCOMMIT — `conn.in_transaction` is False after the DROP — so each drop
    committed instantly and every other process saw a triggerless `shards`
    table until the CREATE landed. Any concurrent INSERT in that interval wrote
    a row that nothing ever indexed: present in `shards`, returned by
    recent_shards and by retrieve(), permanently invisible to keyword search.
    Every new process re-opened the window, so the more writers ran
    concurrently, the more rows silently fell out of the index.

    Two properties close the class, not just the instance:

      1. NO-OP ON THE COMMON PATH. If the triggers already match the canonical
         definitions, this changes nothing and therefore opens no window at all.
         Init stops being a periodic hazard.
      2. ATOMIC ON THE CHANGE PATH. When they genuinely must be rewritten, the
         drop + create + repair happen inside one BEGIN IMMEDIATE transaction,
         so concurrent writers block on the write lock instead of slipping
         through it, and any row orphaned by an earlier unguarded window is
         re-indexed before that lock is released.

    Consequence: FTS insertion is not something a write path can decide to skip.
    It is a property of the table, held by triggers that are never absent, so
    core.capture(), the fleet-registry MCP writer and the ingest CLI all index
    identically whether or not they know the index exists.
    """
    if fts_triggers_current(conn):
        return False
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for name in _FTS_TRIGGER_SQL:
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        for sql in _FTS_TRIGGER_SQL.values():
            conn.execute(sql)
        _reindex_missing_rows(conn)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return True


def repair_fts_index(db_index: Optional[int] = None) -> dict:
    """Public repair choke point: make every shard on disk searchable again.

    Prefer this over hand-written SQL — it holds the write lock while it works
    and uses the same canonical trigger definitions as init. Returns
    {db_index: rows_reindexed}; a -1 means that DB needed a full FTS5 rebuild.
    """
    out: dict = {}
    indices = [db_index] if db_index is not None else range(1, MAX_DB_COUNT + 1)
    for i in indices:
        if not get_db_path(i).exists():
            continue
        conn = get_connection(i)
        try:
            # Measure the gap BEFORE repairing anything. _ensure_fts_triggers()
            # re-indexes orphans itself when it has to rewrite the triggers, so
            # reading the count afterwards reports 0 for work this call just did
            # and makes a real repair look like a no-op to the caller.
            missing_before = count_unindexed(conn)
            _ensure_fts_triggers(conn)
            conn.execute("BEGIN IMMEDIATE")
            try:
                reindexed = _reindex_missing_rows(conn)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            # -1 (no shadow table -> full rebuild) propagates from whichever
            # step observed it; otherwise the honest total is the pre-repair gap.
            out[i] = reindexed if missing_before < 0 else missing_before
        finally:
            conn.close()
    return out


def _init_db_locked(index: int, key) -> None:
    """Schema creation for one (vault, index) pair. Callers hold _INIT_LOCK."""
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


    # FTS5 with Trigram for fuzzy recall (Module 1: Convergent Traces)
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

    # Sync triggers (Module 18: Reconstruct Coherence). Installed via
    # _ensure_fts_triggers so that installing them can never itself open a
    # window in which a concurrent write bypasses the index — see that
    # function for the root cause this replaces.
    conn.commit()
    _ensure_fts_triggers(conn)

    conn.commit()
    conn.close()
    _INITIALIZED_DBS.add(key)


RECALL_PACKET_MARKER = "=== NOUGENSHARDS RECALL PACKET"


def canonical_content(content: str) -> str:
    """THE one content normalization: redact secrets, then strip recall packets.

    Extracted 2026-07-24 because capture() needed the *same* normalized text for
    two purposes — the dedup hash and the ingest embedding — and reaching into
    compute_dedup_hash()'s locals for it (`clean_content`) raised NameError on
    every capture, silently swallowed. One function, two callers, no divergence:
    if the identity rule changes, what gets embedded changes with it.
    """
    try:
        from .brain_scan.redaction import redact_content as _redact
        content = _redact(content)
    except Exception:
        pass
    if RECALL_PACKET_MARKER in content:
        return content.split(RECALL_PACKET_MARKER)[0].strip()
    return content


def compute_dedup_hash(content: str) -> str:
    """Canonical shard identity used by the dedup index.

    THE one definition. capture() uses it, and so must any external tool that
    asks "is this file already sharded?" (ingesters, drift detectors). The order
    is load-bearing:

      1. redact secrets  - capture() redacts before hashing so a shard's identity
         is its clean text and the hash never encodes a plaintext credential
         (Atibon/Keymaker doctrine). redact_content is idempotent, so calling
         this on already-redacted content is safe.
      2. strip recall packet - injected recall packets are context, not identity.
      3. md5 of the result.

    Why this function exists (2026-07-24): shard_vault_files.py and the drift
    detector hashed RAW file content while capture() hashed REDACTED content.
    Any vault file containing a credential-shaped string therefore hashed
    differently on the two sides: it was re-captured on every ingest run and
    reported as permanent, uncloseable drift. Reimplementing the hash is how
    that bug happened; import this instead.
    """
    return hashlib.md5(
        canonical_content(content).encode("utf-8", errors="ignore")).hexdigest()


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

    # Canonical shard identity. Delegated to compute_dedup_hash() so external
    # tools (ingesters, drift detectors) can compute the SAME identity instead of
    # reimplementing it and silently diverging.
    fhash = compute_dedup_hash(content)

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
                from . import embedding_backfill as _eb
                # Model discovered from the live /api/tags roster, never a
                # hardcoded tag (Rule 0.2): a stale model name is silent here,
                # it just yields a keyword-only shard.
                #
                # Embed the SAME normalized text the dedup hash is computed
                # from — via canonical_content(), not a private local of
                # compute_dedup_hash(). Reaching for that local is exactly the
                # NameError that made capture() embed nothing at all.
                #
                # Resolved through the module object (not `from ... import
                # embed`) so a monkeypatch on embedding_backfill.embed is
                # actually observed here — a test that patches a name capture()
                # never consults proves nothing.
                embedding = _eb.embed(
                    canonical_content(content)[:EMBED_MAX_CHARS],
                    _eb.resolve_embed_model(timeout=EMBED_TIMEOUT),
                    timeout=EMBED_TIMEOUT)
            except (ImportError, OSError):
                # ONLY "the embedder is unreachable/absent" degrades quietly:
                # ImportError (optional module missing), OSError (socket,
                # timeout, urllib URLError/HTTPError — all OSError subclasses).
                # A broad `except Exception` here is what hid the NameError for
                # a full day: NameError/AttributeError/TypeError are programming
                # bugs, not outages, and MUST propagate loudly.
                embedding = None

        emb_blob = None
        if embedding:
            arr = np.array(embedding, dtype=np.float32)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            emb_blob = sqlite3.Binary(arr.tobytes())

        # Derive the provenance tier AT INGEST and stamp it as an explicit
        # `provenance:<tier>` tag, which classify() reads at precedence 2.
        #
        # Why a tag and not a new column: a mature grid spans several database
        # files that other lanes read concurrently. An ALTER on the shards table
        # would need a full backup of all of it to be safe, for a value the
        # classifier can already compute from fields that are ALREADY stored.
        # New rows therefore carry the tier explicitly, and pre-existing rows
        # are classified lazily at rank time — no re-index, no backfill,
        # no schema mutation of live memory.
        tag_list = list(tags or [])
        # An unembedded shard is invisible to the vector lane. That is allowed
        # (ollama may be down) but it is never allowed to be SILENT: record it
        # on the row so the gap is observable and sweepable.
        if emb_blob is None and EMBED_PENDING_TAG not in tag_list:
            tag_list.append(EMBED_PENDING_TAG)
        if provenance.ENABLED and not any(
                str(t).lower().startswith("provenance:") for t in tag_list):
            tag_list.append("provenance:" + provenance.classify({
                "title": title, "content": content, "tags": tag_list,
                "event_type": event_type}))
        tags_str = json.dumps(tag_list)
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

        # Cue-anchored delivery lane (additive, opt-in): derive trigger
        # conditions for the new shard so the harness can inject it later
        # without the agent having to remember to recall. No-op unless
        # NOUGEN_TRIGGERS_AUTODERIVE=1, and it can never fail a capture.
        try:
            from . import triggers as _triggers  # pylint: disable=import-outside-toplevel
            _triggers.on_capture(fhash, title, content)
        except Exception:
            pass
        return True
    finally:
        dconn.close()


# Relevance blend weights (Module 20)
WEIGHT_BM25 = _env_float("NOUGEN_RECALL_WEIGHT_BM25", 0.4)
WEIGHT_SEMANTIC = _env_float("NOUGEN_RECALL_WEIGHT_SEMANTIC", 0.6)
WEIGHT_LIKELIHOOD = _env_float("NOUGEN_RECALL_WEIGHT_LIKELIHOOD", 0.7)
WEIGHT_PRIOR = _env_float("NOUGEN_RECALL_WEIGHT_PRIOR", 0.3)
# LIKE-fallback lane has no BM25 term, so it carries its own likelihood/prior
# split rather than borrowing the FTS one (Rule 0.2: no bare literal in a
# shipped ranking line).
WEIGHT_LIKE_LIKELIHOOD = _env_float("NOUGEN_RECALL_WEIGHT_LIKE_LIKELIHOOD", 0.5)
WEIGHT_LIKE_PRIOR = _env_float("NOUGEN_RECALL_WEIGHT_LIKE_PRIOR", 0.5)
# RRF consensus is modulated by the prior as score * (base + prior * span).
# This is the exact term that let an inflated arXiv prior beat an exact-match
# first-party hit across stores, so it is now named and tunable.
RRF_PRIOR_BASE = _env_float("NOUGEN_RRF_PRIOR_BASE", 0.7)
RRF_PRIOR_SPAN = _env_float("NOUGEN_RRF_PRIOR_SPAN", 0.3)
# Default recall scope. `domain_key` is derived from the CURRENT WORKING
# DIRECTORY, so defaulting recall to it silently partitioned the vault into
# cwd-shaped buckets: measured 2026-07-28, nougen_shards_4.db held 8,922 shards
# under 'NouGen/NouGenShards-push-main', 4 under 'Watchtower/NouGen' and exactly
# ONE under 'global' -- a shard captured from one directory was invisible to a
# recall run from another. The vault only compounds if recall spans it, so the
# default is now whole-brain and the local domain becomes a ranking BOOST
# instead of a hard filter. Set NOUGEN_RECALL_SCOPE=domain to restore the old
# partitioned behaviour.
RECALL_SCOPE = os.environ.get("NOUGEN_RECALL_SCOPE", "all").strip().lower()
DOMAIN_AFFINITY_BOOST = _env_float("NOUGEN_RECALL_DOMAIN_BOOST", 1.15)
# Usage evidence. `access_count` is a RAW LIFETIME COUNT and is deliberately
# never decayed: how often a shard was surfaced is a fact, not a recency signal,
# and `utility_score` already carries decay (decay_utility_scores) -- decaying
# both would double-count recency.
#
# It is recorded but does NOT feed ranking by default, and that default is load
# bearing. `_record_access` increments on every retrieval, so scoring off it
# makes retrieval self-reinforcing: the same query run twice returns different
# scores (caught by test_retrieve_ranking_is_deterministic, measured drift 0.26)
# and frequently-surfaced shards climb purely for having been surfaced -- the
# rich-get-richer failure `_squash_utility` exists to stop. Being *returned* by a
# search is not evidence of usefulness; being *used* is, and that already flows
# through `attribution.observed_prior` via mark_shard(). Set
# NOUGEN_RECALL_WEIGHT_ACCESS>0 to opt in, accepting non-determinism.
WEIGHT_ACCESS = _env_float("NOUGEN_RECALL_WEIGHT_ACCESS", 0.0)
# Query-term coverage boost. Applied as (1 + span * coverage) so a shard
# containing every query term outranks one that matched a single term through
# the OR-retry. Set to 0 to disable.
COVERAGE_BOOST_SPAN = _env_float("NOUGEN_RECALL_COVERAGE_BOOST", 0.6)


def _squash_utility(u: float) -> float:
    """Map unbounded utility (grows via ACCESSED feedback, observed up to ~4.3)
    into [0,1) so the prior can never drown the bounded semantic likelihood —
    unbounded priors made incumbents win over perfect semantic matches
    (rich-get-richer, diagnosed 2026-07-11 via the recall probe)."""
    return u / (1.0 + u) if u > 0 else 0.0


def _saturate_access(count) -> float:
    """Log-saturate a raw lifetime `access_count` into a bounded contribution.

    log1p keeps the first few uses informative (0->0, 1->0.69, 10->2.4) while
    flattening the tail, so a shard that has been returned hundreds of times
    cannot ride usage alone past an exact match it has never competed with.
    """
    try:
        n = float(count or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return math.log1p(n) if n > 0 else 0.0


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _term_coverage(item: dict, query_tokens: frozenset) -> float:
    """Fraction of the query's distinct terms that actually appear in the shard.

    The OR-retry that keeps multi-term queries alive (HARDENING invariant 5)
    also admits shards matching a SINGLE term, and nothing downstream
    distinguished those from a shard matching every term: measured 2026-07-28,
    a one-term hit outranked an exact three-term match on "arxiv scanner hang".
    BM25 does not close this gap across lanes because RRF fuses ranks, not
    scores. Coverage restores the signal -- prefix matching so a stemmed index
    ("hang" vs "hangs") still counts.
    """
    if not query_tokens:
        return 0.0
    haystack = f"{item.get('title') or ''} {item.get('content') or ''}".lower()
    words = frozenset(_TOKEN_RE.findall(haystack))
    hits = 0
    for term in query_tokens:
        if term in words or any(w.startswith(term) or term.startswith(w)
                                for w in words if abs(len(w) - len(term)) <= 3):
            hits += 1
    return hits / len(query_tokens)


def _domain_affinity(item: dict, local_domain: Optional[str]) -> float:
    """Multiplier rewarding shards captured in the caller's own domain.

    Replaces the old hard `domain_key = ?` filter: local context still wins ties,
    but a shard from another directory is now merely ranked lower rather than
    made invisible.
    """
    if not local_domain:
        return 1.0
    return DOMAIN_AFFINITY_BOOST if item.get("domain_key") == local_domain else 1.0


def _effective_prior(item: dict, decay: float = 1.0) -> float:
    """The single chokepoint every ranking lane uses for the utility prior.

    Two corrections are applied here and NOWHERE else, so no lane can drift:

      1. `attribution.observed_prior` -- if a caller has actually declared this
         shard as used/cited, that observed contribution replaces the stored
         prior (AttriMem, arXiv 2607.21106). No usage recorded == unchanged.
      2. `provenance.adjust_prior` -- tier weight and cap, so a third-party
         (arXiv/RSS) shard cannot outrank a first-party shard on the prior
         alone (arXiv 2607.20891).

    The likelihood terms (BM25 / semantic / RRF consensus) are untouched by
    design: that is what keeps research queries able to surface arXiv shards on
    merit. Only the *prior* is de-privileged.
    """
    try:
        prior = float(item.get("utility_score", 1.0) or 0.0)
    except (TypeError, ValueError):
        prior = 1.0
    prior = attribution.observed_prior(item, prior)
    prior = provenance.adjust_prior(item, prior)
    prior += WEIGHT_ACCESS * _saturate_access(item.get("access_count"))
    return prior * decay


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

def _now_utc() -> datetime:
    """One reference instant for a whole ranking pass. See _temporal_decay."""
    return datetime.now(timezone.utc)


def _temporal_decay(ts_str, now: Optional[datetime] = None) -> float:
    """Recency decay for one candidate, measured against a SINGLE reference
    instant supplied by the caller.

    Every ranking lane used to inline this and call datetime.now() PER ROW, so a
    shard's score depended on when in the scan loop it happened to be processed.
    That is real ranking nondeterminism, not a rounding artefact: over the
    default 30-day half-life the microseconds between two rows move a score by
    ~1e-12, which is larger than the gap between shards captured a second apart.
    Measured 2026-07-24 on six near-identical shards -- consecutive retrieve()
    calls on an unchanged vault returned three different orderings (id order
    drifted in ~3 of 40 runs), because whichever row the loop reached first was
    scored against an earlier `now` and won.

    Sampling once per pass makes decay a pure function of the stored timestamp.
    Candidates that remain exactly equal are then separated by the stable
    (_db_index, id) tiebreak on each lane's sort, so the order is total.
    """
    if not ts_str:
        return 1.0
    if now is None:
        now = _now_utc()
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (now - dt).total_seconds() / 86400.0
        return max(0.1, 0.5 ** (age_days / RECALL_DECAY_HALFLIFE_DAYS))
    except Exception:
        return 1.0


def _rank_key(item: dict, score_field: str = "final_score"):
    """Total order for ranked candidates: score desc, then a STABLE identity.

    Relying on Python's stable sort alone only preserves *insertion* order, and
    insertion order here is 'whichever DB the scan reached first' — fine until
    two candidates tie, at which point the ranking is decided by scan order
    rather than by anything about the shards. (_db_index, id) is the shard's
    durable identity in the grid, so equal-scoring shards always rank the same
    way, in this process and the next.
    """
    return (-float(item.get(score_field, 0.0) or 0.0),
            int(item.get("_db_index", 0) or 0),
            int(item.get("id", 0) or 0))


def _process_fts_result(row, db_index, query_embedding, now: Optional[datetime] = None):
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
    decay = _temporal_decay(item.get("timestamp"), now)

    decayed_utility = _effective_prior(item, decay)

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


def _fts_lanes(conn) -> List[str]:
    """FTS tables to try, best-relevance first.

    ``shards_fts`` is tokenized with trigram, so it matches 3-character
    substrings: MATCH 'hang' also hits *change*/*exchange*, and bm25 over
    trigrams barely encodes term relevance. ``shards_fts_porter`` (built by
    ``tools/fts_porter_backfill.py``) is word-tokenized and stemmed, so it is
    preferred when present. Probed per-connection rather than assumed -- a
    store that never got the backfill degrades silently to trigram (Rule 0.2).
    """
    lanes = []
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('shards_fts_porter','shards_fts')"
        ).fetchall()
        present = {r[0] for r in rows}
    except sqlite3.OperationalError:
        return ["shards_fts"]
    if "shards_fts_porter" in present:
        lanes.append("shards_fts_porter")
    if "shards_fts" in present:
        lanes.append("shards_fts")
    return lanes or ["shards_fts"]


def _keyword_retrieve(query: str, limit: int = 20, query_embedding: Optional[List[float]] = None,
                      domain_key: str = "global", now: Optional[datetime] = None) -> list:
    """Scans for keyword matches using FTS5 (with LIKE fallback)."""
    from . import history # pylint: disable=import-outside-toplevel

    # ONE reference instant for every candidate this pass scores. Sampling the
    # clock per row made a shard's decay depend on its position in the scan.
    if now is None:
        now = _now_utc()
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
            # Stemmed lane first, trigram second. Each lane runs the full
            # AND-then-OR ladder before the next lane is tried, so a precise
            # word match always beats a substring match from the older index.
            for lane in _fts_lanes(conn):
                for match_expr in match_attempts:
                    try:
                        # domain_key None/"*" => search ALL domains (whole brain), not one bucket.
                        dom_clause = "" if domain_key in (None, "*") else "s.domain_key = ? AND "
                        dom_params = () if domain_key in (None, "*") else (domain_key,)
                        cursor = conn.execute(f"""
                            SELECT s.id, s.timestamp, s.title, s.content, s.utility_score, s.access_count,
                                   s.embedding, s.tags, s.domain_key, s.density_score, bm25({lane}) as bm25_score
                            FROM shards s JOIN {lane} ON s.id = {lane}.rowid
                            WHERE {dom_clause}{lane} MATCH ?
                            ORDER BY bm25_score ASC LIMIT ?
                        """, (*dom_params, match_expr, limit))
                        res = cursor.fetchall()
                        if res:
                            for row in res:
                                history.log_event(row["id"], i, "ACCESSED")
                                results.append(_process_fts_result(row, i, query_embedding, now))
                            fts_worked = True
                            break
                    except sqlite3.OperationalError:
                        break
                if fts_worked:
                    break

            if not fts_worked:
                history.log_event(0, i, "SEARCH_FALLBACK", metadata={"query": query})
                
                like_query = f"%{query}%"
                dom_clause = "" if domain_key in (None, "*") else "domain_key = ? AND "
                dom_params = () if domain_key in (None, "*") else (domain_key,)
                cursor = conn.execute(f"""
                    SELECT id, timestamp, title, content, utility_score, access_count, embedding, tags, domain_key, density_score
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

                    decay = _temporal_decay(item.get("timestamp"), now)

                    decayed_utility = _effective_prior(item, decay)
                    item["final_score"] = ((likelihood * WEIGHT_LIKE_LIKELIHOOD)
                                           + (decayed_utility * WEIGHT_LIKE_PRIOR))
                    results.append(item)
        finally:
            conn.close()

    results.sort(key=_rank_key)
    return results[:limit]


def _vector_retrieve_ann(query_embedding: List[float], limit: int = 20,
                         domain_key: str = "global", now: Optional[datetime] = None):
    """ANN fast-path for _vector_retrieve (opt-in via NOUGEN_ANN=1).

    Uses the unified HNSW index to fetch candidate (db, id) pairs sub-linearly,
    then re-scores them with the SAME dot + temporal-decay + utility blend as the
    linear scan, so RRF fusion downstream is unchanged. Returns None if the index
    is unavailable -> the caller falls back to the verified linear scan.
    """
    from . import ann_index, history  # pylint: disable=import-outside-toplevel
    if now is None:
        now = _now_utc()
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
                SELECT id, timestamp, title, content, utility_score, access_count, embedding, tags, domain_key
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
                decay = _temporal_decay(item.get("timestamp"), now)
                decayed_utility = _effective_prior(item, decay)
                item["final_score"] = (sem_score * WEIGHT_LIKELIHOOD) + (_squash_utility(decayed_utility) * WEIGHT_PRIOR)
                results.append(item)
        finally:
            conn.close()

    results.sort(key=_rank_key)
    top_results = results[:limit]
    for item in top_results:
        history.log_event(item["id"], item["_db_index"], "ACCESSED")
    return top_results


def _vector_retrieve(query_embedding: Optional[List[float]], limit: int = 20,
                     domain_key: str = "global", now: Optional[datetime] = None) -> list:
    """Scans for semantic vector matches independent of FTS."""
    if query_embedding is None:
        return []

    # ONE reference instant for every candidate this pass scores (see
    # _temporal_decay): per-row clock sampling reordered equal-scoring shards.
    if now is None:
        now = _now_utc()

    # ANN fast-path (opt-in). Falls back to the linear scan below if the index
    # is missing/stale/unreadable, so correctness never depends on the index.
    if os.environ.get("NOUGEN_ANN") == "1":
        ann_results = _vector_retrieve_ann(query_embedding, limit, domain_key, now)
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
                SELECT id, timestamp, title, content, utility_score, access_count, embedding, tags, domain_key
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

                decay = _temporal_decay(item.get("timestamp"), now)

                decayed_utility = _effective_prior(item, decay)
                item["final_score"] = (sem_score * WEIGHT_LIKELIHOOD) + (_squash_utility(decayed_utility) * WEIGHT_PRIOR)
                results.append(item)
        finally:
            conn.close()

    results.sort(key=_rank_key)
    top_results = results[:limit]
    
    for item in top_results:
        history.log_event(item["id"], item["_db_index"], "ACCESSED")
        
    return top_results


def reciprocal_rank_fusion(result_lists: List[List[dict]], k: int = 60,
                           now: Optional[datetime] = None) -> List[dict]:
    """
    Module 8 / 21: Reciprocal Rank Fusion (RRF) to merge multiple ranked lists.
    """
    if now is None:
        now = _now_utc()
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
        decay = _temporal_decay(item.get("timestamp"), now)
        # THE cross-store tiebreak. RRF consensus is modulated by the prior, so
        # before the provenance transform an inflated bulk-ingest utility (4.29
        # vs a curated 0.9) multiplied a third-party shard past an exact-match
        # first-party hit. _effective_prior applies the tier weight + cap here.
        decayed_utility = _effective_prior(item, decay)
        item["final_score"] = consensus_score * (RRF_PRIOR_BASE + (decayed_utility * RRF_PRIOR_SPAN))
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


def _record_access(items: list) -> None:
    """Bump ``access_count`` for shards this retrieval actually returned.

    The column has existed since the first schema but nothing ever wrote it, so
    every one of the 80,797 in-scope shards sat at 0 and usage could not inform
    ranking. Grouped by database so a multi-hit result costs one transaction per
    store rather than one per row.

    Best-effort by contract: several MCP servers hold these files open, and a
    locked bookkeeping write must never take down a recall that already
    succeeded. Deliberately NOT consumed by the ranking formula yet -- whether
    the signal should decay is an open question for the GM (see
    ``wargames/recall-elevation.md``); until then it only accumulates.
    """
    if not items:
        return
    by_db: dict = {}
    for item in items:
        db_index, shard_id = item.get("_db_index"), item.get("id")
        if db_index and shard_id:
            by_db.setdefault(db_index, []).append(shard_id)
    for db_index, ids in by_db.items():
        try:
            conn = get_connection(db_index)
            try:
                conn.execute(
                    "UPDATE shards SET access_count = COALESCE(access_count, 0) + 1 "
                    f"WHERE id IN ({','.join('?' * len(ids))})", ids)
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error:
            continue  # bookkeeping never breaks retrieval


def retrieve(query: str, limit: int = 3, query_embedding: Optional[List[float]] = None,
             domain_key: Optional[str] = None) -> list:
    """
    Advanced Retrieval (Module 21): Runs both keyword (FTS/LIKE) and vector (semantic)
    searches in parallel lanes and merges them using Reciprocal Rank Fusion (RRF).
    When NOUGEN_RERANK=1, a cross-encoder reranks the top RRF candidates (Stage 2).
    """
    import concurrent.futures

    # ONE reference instant for this entire retrieval, threaded through both
    # lanes, the fusion and the tripartite score. Every candidate is therefore
    # aged against the same clock reading instead of against whenever the scan
    # loop happened to reach it -- the cause of the run-to-run id-order drift
    # measured on 2026-07-24 (see _temporal_decay).
    now = _now_utc()

    # Ensure all existing shard databases are schema-upgraded to the current version before querying
    for i in range(1, MAX_DB_COUNT + 1):
        if get_db_path(i).exists():
            init_db(i)

    # The caller's own domain is always resolved -- but it is used to BOOST
    # rather than to filter, unless NOUGEN_RECALL_SCOPE=domain restores the old
    # partitioned behaviour. An explicit domain_key argument still wins.
    local_domain = resolve_domain_from_path()
    if not domain_key:
        domain_key = local_domain if RECALL_SCOPE == "domain" else "*"
    query_tokens = frozenset(t for t in _TOKEN_RE.findall((query or "").lower())
                             if len(t) > 2)

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
                _keyword_retrieve, query, candidate_limit, query_embedding, active_domain, now
            )
            future_vector = executor.submit(
                _vector_retrieve, query_embedding, candidate_limit, active_domain, now
            )

            keyword_results = future_keyword.result()
            vector_results = future_vector.result()

        fused = reciprocal_rank_fusion([keyword_results, vector_results], k=60, now=now)
        return fused, keyword_results, vector_results

    all_results, kw_lane, vec_lane = run_parallel_retrieval(domain_key)

    # Fallback: sweep the ENTIRE brain (all domain_keys) when the domain-scoped
    # pass produced no LEXICAL evidence.
    #
    # Gating this on `not all_results` was effectively dead code: the vector
    # lane almost always returns in-domain neighbours, so all_results was
    # non-empty even when the keyword lane found nothing — and any shard whose
    # domain_key differs from the cwd-derived domain became unreachable on an
    # exact-term match. Measured 2026-07-24: query "OvisOCR2" under cwd domain
    # 'NouGen/NouGenShards-push-main' returned keyword=0 / vector=20, so the
    # sweep never fired and the exact-title shard (domain_key 'Watchtower')
    # was never surfaced; the whole-brain pass ranks it #1.
    # NOUGEN_RECALL_GLOBAL_FALLBACK: keyword (default) | empty (legacy) | off
    if domain_key != "*":
        mode = os.environ.get("NOUGEN_RECALL_GLOBAL_FALLBACK", "keyword").strip().lower()
        should_sweep = (not kw_lane) if mode == "keyword" else (not all_results)
        if mode != "off" and should_sweep:
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
            
        decay = _temporal_decay(item.get("timestamp"), now)
        
        density = item.get("density_score", 1.0)

        u_shard = (1.0 * relevance) * decay * density
        # High-volume domain damper (Rule 0.2, default-neutral): ~6.6K sharp
        # single-topic arXiv abstracts outrank sparse operational doctrine on
        # paraphrase queries. Set NOUGEN_RECALL_ARXIV_WEIGHT<1 to rebalance.
        if ARXIV_RECALL_WEIGHT != 1.0 and "arxiv" in (item.get("title") or "").lower():
            u_shard *= ARXIV_RECALL_WEIGHT
        # Domain affinity as a boost, not a filter: the caller's own directory
        # ranks first without the rest of the vault going invisible.
        u_shard *= _domain_affinity(item, local_domain)
        if COVERAGE_BOOST_SPAN:
            u_shard *= 1.0 + COVERAGE_BOOST_SPAN * _term_coverage(item, query_tokens)
        item["utility_score_tripartite"] = u_shard
        scored_results.append(item)
    
    # Sort candidates by the tripartite score
    scored_results.sort(key=lambda x: _rank_key(x, "utility_score_tripartite"))
    
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
    # Carry the authority tag through to the caller. arXiv 2607.20891's finding
    # is that verification at retrieval time does NOT survive a long-horizon
    # workflow, so the tier has to travel with the shard, not be checked once.
    _record_access(reordered)
    return provenance.annotate(reordered)


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

        # A mark_utility call is the one place today where a caller states, on
        # the record, that a specific shard mattered — so it doubles as a real
        # attribution observation (AttriMem, arXiv 2607.21106). Recorded through
        # the same non-blocking queue rather than a parallel mechanism.
        # NOTE: retrieval-time ACCESSED events are deliberately NOT recorded
        # here; those encode rank, not usage, and feeding them back would
        # fabricate a contribution signal.
        attribution.record_usage(
            [(shard_id, i)], contribution=val,
            source=attribution.SOURCE_MARK_UTILITY,
            metadata={"worked": bool(worked)})

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
        # Federated recall spans several stores; name the one this hit came from
        # so the caller can tell curated vault shards from imported transcripts.
        store = s.get("_store")
        if store:
            role = "primary" if s.get("_store_primary") else "secondary"
            db_tag += f" [store: {store}/{role}]"
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
