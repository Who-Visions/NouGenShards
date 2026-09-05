"""
Valerion Core — NouGenShards Memory Substrate.
Logic: SQLite + FTS5 + BM25 + Trigram (n-gram) + Vector Embeddings + Weighted Relevance Reranking.
Architecture: Valerion 21-step cognitive loop. Weighted multi-signal relevance blend (BM25 + semantic + usefulness prior).
"""
# pylint: disable=duplicate-code
import hashlib
import json
import logging
import os
import sqlite3
import threading as _threading
from contextvars import ContextVar, Token, copy_context
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

#: Seconds a capture may wait for its embedding before storing NULL and
#: leaving the row for embedding_backfill. Env-tunable per Rule 0.0 item 4;
#: the literal is a fallback only.
DEFAULT_EMBED_CAPTURE_TIMEOUT_S = float(os.environ.get("NOUGEN_EMBED_CAPTURE_TIMEOUT_S", "15"))

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

_ACTIVE_VAULT_DIR: ContextVar[Optional[Path]] = ContextVar(
    "nougen_active_vault_dir", default=None)
_ACTIVE_TENANT_ID: ContextVar[Optional[str]] = ContextVar(
    "nougen_active_tenant_id", default=None)


def active_vault_dir() -> Path:
    """Request-local vault, falling back to the legacy process-wide vault."""
    return _ACTIVE_VAULT_DIR.get() or GLOBAL_DIR


def active_tenant_id() -> str:
    """Request-local tenant; unset local/CLI work retains owner behaviour."""
    return _ACTIVE_TENANT_ID.get() or "owner"


def vault_context_is_set() -> bool:
    return _ACTIVE_VAULT_DIR.get() is not None


def bind_active_vault(vault_dir: Path, tenant_id: str) -> tuple[Token, Token]:
    """Bind a tenant to the current context and return reset tokens."""
    return (_ACTIVE_VAULT_DIR.set(Path(vault_dir)), _ACTIVE_TENANT_ID.set(tenant_id))


def reset_active_vault(tokens: tuple[Token, Token]) -> None:
    """Undo :func:`bind_active_vault` in the context that created it."""
    vault_token, tenant_token = tokens
    _ACTIVE_TENANT_ID.reset(tenant_token)
    _ACTIVE_VAULT_DIR.reset(vault_token)


def _ensure_active_vault_dir() -> Path:
    vault = active_vault_dir()
    vault.mkdir(parents=True, exist_ok=True, mode=0o700)
    if active_tenant_id() != "owner":
        try:
            vault.chmod(0o700)
        except OSError:
            pass
    return vault



def get_db_path(index: int) -> Path:
    """Returns the path for a specific database index (Module 11: Transform Architecture)."""
    from . import snapshot_mode  # pylint: disable=import-outside-toplevel
    if snapshot_mode.enabled():
        snap = snapshot_mode.snapshot_dir()
        if snap is not None:
            return snap / f"nougen_shards_{index}.db"
    return active_vault_dir() / f"nougen_shards_{index}.db"


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
    """Establishes an SQLite connection with WAL enabled (Module 19: Stabilize Reasoning).

    In snapshot mode the file is a published read-only artifact on a network
    mount: open it immutable (no locks, no journal probing, no shm) - the
    only sqlite access pattern that is safe over FUSE, and the reason
    snapshot mode exists at all.
    """
    path = get_db_path(index)
    from . import snapshot_mode  # pylint: disable=import-outside-toplevel
    if snapshot_mode.enabled() and snapshot_mode.snapshot_dir() is not None:
        conn = sqlite3.connect(f"file:{path}?immutable=1&mode=ro", uri=True,
                               timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn
    try:
        conn = sqlite3.connect(str(path), timeout=10.0)
    except sqlite3.OperationalError as exc:
        # "unable to open database file" is how the descriptor ceiling shows
        # up: the file is there, the process just cannot open one more. Every
        # caller degrades ("ONE bad DB must not zero out the read"), so without
        # this line the ceiling is invisible - phoebus ran at it for a day
        # while /health stayed 200. Name the count, then re-raise unchanged.
        if "unable to open" in str(exc).lower():
            from . import fd_budget  # pylint: disable=import-outside-toplevel
            logger.error("grid DB %s: %s - process holds %s open descriptors "
                         "(soft limit %s); see fd_budget.py",
                         index, exc, fd_budget.open_fd_count(), _nofile_soft_limit())
        raise
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _nofile_soft_limit():
    try:
        import resource  # pylint: disable=import-outside-toplevel
        return resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    except (ImportError, ValueError, OSError):
        return None


_INITIALIZED_DBS = set()


def quarantine_malformed_dbs() -> list:
    """Rename unreadable grid DB files aside so the grid heals itself at boot.

    2026-09-01 Space-sqlite P1: six of nine grid DBs went "disk image is
    malformed" on the Space's network-backed volume. The files cannot be
    repaired remotely (no shell on a Space) and a full volume wipe throws away
    every HEALTHY index with them. Surgical alternative: quick_check each grid
    DB; a file that fails is RENAMED (never deleted - forensics) to
    ``<name>.malformed-<utcstamp>`` together with its -wal/-shm sidecars, and
    an empty healthy DB is recreated in its place. Healthy indices are never
    touched, and a missing-only refill can then restore just the lost rows.

    Env-gated per Rule 0.2: ``NOUGEN_QUARANTINE_MALFORMED_ON_BOOT`` (default
    on; "0"/"false"/"no"/"off" disables). No-op in snapshot mode - published
    snapshots are immutable artifacts.

    Returns a list of {"index", "moved_to", "reason"} dicts, one per
    quarantined DB, so callers can log and surface the action.
    """
    flag = os.environ.get("NOUGEN_QUARANTINE_MALFORMED_ON_BOOT", "1")
    if flag.strip().lower() in ("0", "false", "no", "off"):
        return []
    from . import snapshot_mode  # pylint: disable=import-outside-toplevel
    if snapshot_mode.enabled() and snapshot_mode.snapshot_dir() is not None:
        return []
    quarantined = []
    for i in range(1, MAX_DB_COUNT + 1):
        path = get_db_path(i)
        if not path.exists():
            continue
        reason = None
        try:
            conn = sqlite3.connect(str(path), timeout=10.0)
            try:
                row = conn.execute("PRAGMA quick_check(1);").fetchone()
            finally:
                conn.close()
            if row and str(row[0]).lower() == "ok":
                continue
            reason = str(row[0]) if row else "quick_check returned no row"
        except (sqlite3.DatabaseError, OSError) as exc:
            reason = f"{type(exc).__name__}: {exc}"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = path.with_name(f"{path.name}.malformed-{stamp}")
        try:
            path.rename(dest)
        except OSError as exc:
            # Locked or volume-level fault: leave it - the per-DB scan guards
            # already skip unreadable files, so this is no worse than before.
            logger.error("grid DB %s failed quick_check but could not be "
                         "quarantined (%s): %s", i, reason, exc)
            continue
        for suffix in ("-wal", "-shm"):
            side = Path(str(path) + suffix)
            if side.exists():
                try:
                    side.rename(Path(str(dest) + suffix))
                except OSError as exc:
                    logger.error("grid DB %s sidecar %s not moved: %s",
                                 i, suffix, exc)
        _INITIALIZED_DBS.discard((str(path.parent), i))
        init_db(i)
        logger.error("grid DB %s quarantined to %s (%s) and recreated empty",
                     i, dest.name, reason)
        try:
            from . import history  # pylint: disable=import-outside-toplevel
            history.log_event(0, i, "DB_QUARANTINED",
                              metadata={"moved_to": dest.name, "reason": reason})
        except Exception:  # pylint: disable=broad-except
            pass
        quarantined.append({"index": i, "moved_to": dest.name, "reason": reason})
    return quarantined


def init_db(index: int = 1):  # noqa: C901
    """Initializes the substrate schema (Module 6: Copy Successful Topology).

    Idempotent, but re-running CREATE TABLE / DROP+CREATE TRIGGER on every
    capture dominates bulk-ingestion cost — so each (vault, index) pair is
    initialized once per process. Keyed by vault dir because tests and tools
    repoint NOUGEN_VAULT_DIR/GLOBAL_DIR mid-process.
    """
    from . import snapshot_mode  # pylint: disable=import-outside-toplevel
    if snapshot_mode.enabled() and snapshot_mode.snapshot_dir() is not None:
        # Snapshot artifacts are published complete and immutable; there is
        # nothing to initialize and nothing may be written.
        return
    vault = _ensure_active_vault_dir()
    key = (str(vault), index)
    if key in _INITIALIZED_DBS:
        return
    conn = get_connection(index)
    try:
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

        # Relay provenance (schema v3): older nodes did not retain the
        # publisher URI, so add it idempotently during normal startup.
        try:
            cursor.execute("ALTER TABLE shards ADD COLUMN source_uri TEXT;")
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
        _INITIALIZED_DBS.add(key)
    finally:
        conn.close()


def get_dedup_path():
    """Path to the central dedup index (Module 12: Refactor Complexity)."""
    return _ensure_active_vault_dir() / "dedup_index.db"


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
        # A corrupt DB here does not break a read, it silently degrades DEDUP:
        # the backfill aborts, hashes from the remaining DBs never land, and
        # global dedup starts missing duplicates with no error anywhere.
        src = None
        try:
            src = get_connection(i)
            rows = src.execute("SELECT file_hash FROM shards").fetchall()
            conn.executemany(
                "INSERT OR IGNORE INTO hashes (file_hash, db_index) VALUES (?, ?)",
                [(r["file_hash"], i) for r in rows])
        except (sqlite3.DatabaseError, OSError) as exc:
            logger.error("grid DB %s unreadable during dedup backfill, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            continue
        finally:
            if src is not None:
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
                    "NOUGEN_DENSITY_MODELS", "gemma4:e2b-qat,gemma4:e2b,gemma4:e4b,gemma4:31b-cloud"
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
        # Capture-time embed budget. 1.5s was the original default and lost
        # ~90% of captures on phoebus (measured 2026-09-03: 0.25s hot, 4.5s
        # warm, 13.4s cold load for nomic-embed-text). Env-tunable, logged fallback.
        timeout = float(os.environ.get("NOUGEN_EMBED_TIMEOUT",
                                       str(DEFAULT_EMBED_CAPTURE_TIMEOUT_S)))
    except ValueError:
        timeout = 1.5
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


def _query_embed_enabled() -> bool:
    return os.environ.get("NOUGEN_QUERY_EMBED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _embed_query(query: str) -> Optional[np.ndarray]:
    """Embed the query at read time so the vector lane actually fires.

    Shards are embedded at write ("born recallable"), but until 2026-08-30 no
    recall caller ever computed a QUERY embedding, so _vector_retrieve was a
    permanent no-op and every recall ran keyword-only against a fully-embedded
    vault. A miss here is non-fatal: recall degrades to keyword lanes exactly
    as before, and the miss is logged rather than swallowed.
    """
    model = os.environ.get("NOUGEN_EMBED_MODEL", "nomic-embed-text")
    try:
        # Default is looser than capture's 1.5s: the first query after an
        # idle period pays ollama's model (re)load, and a cold-load miss here
        # silently degrades every recall to keyword-only.
        timeout = float(os.environ.get("NOUGEN_QUERY_EMBED_TIMEOUT",
                                       os.environ.get("NOUGEN_EMBED_TIMEOUT", "3.0")))
    except ValueError:
        timeout = 3.0
    try:
        from .embedding_backfill import embed as _embed  # local import: optional dep path
        vec = _embed((query or "")[:4000], model, timeout=timeout)
    except Exception as exc:  # pylint: disable=broad-except
        vec = None
        logger.debug("query embedding raised: %s", exc)
    if not vec:
        logger.warning("query embedding unavailable (model=%s); recall is keyword-only "
                       "for this query -- is ollama up?", model)
        return None
    arr = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return (arr / norm) if norm > 0 else None


#: Grid DBs whose FILES failed a write with a corruption-class error this
#: process. Hash-routed writes skip them (content lands in the next healthy
#: DB); retrieval already degrades per-DB on its own.
_QUARANTINED_WRITE_DBS: set = set()


def _next_healthy_write_index(after: int) -> int:
    """Next write target after `after`, skipping quarantined indexes."""
    for step in range(1, MAX_DB_COUNT + 1):
        cand = ((after - 1 + step) % MAX_DB_COUNT) + 1
        if cand not in _QUARANTINED_WRITE_DBS:
            return cand
    raise LookupError("every grid DB is quarantined for writes")


class CaptureResult(dict):
    """What `capture()` hands back: a bool that can also say what happened.

    A bare True/False could not tell a caller whether a write FAILED or was a
    no-op DUPLICATE, and could not name the row it wrote - so every surface
    downstream could only forward "success" or "already exists", and a caller
    that saw a falsy answer had no way to know which. Observed live: a capture
    answered with an empty object and had in fact SUCCEEDED, while later ones
    answered identically and had not landed.

    It subclasses `dict` for two reasons: JSON/MCP serialization keeps working
    with no encoder of its own, and `__bool__` is the `captured` flag, so every
    existing `if capture(...)` / `assert capture(...)` caller keeps its exact
    old meaning. Identity checks (`is True`) do not survive and are not part of
    the contract - truthiness is.

    Keys: `captured` (bool), `shard_id`/`db_index` (ints, present when the row
    is known), `reason` (stable machine token: "written" / "duplicate" /
    "error"), and `error` (short human string, only when nothing was written).
    """

    __slots__ = ()

    def __bool__(self) -> bool:
        return bool(self.get("captured", False))

    # Attribute access alongside the mapping. Callers that serialize this over
    # MCP want the dict; callers reading it in Python want `.captured` rather
    # than `["captured"]`, and a missing key should read as absent instead of
    # raising - a result that failed before it ever reached a DB legitimately
    # has no shard_id.
    @property
    def captured(self) -> bool:
        return bool(self.get("captured", False))

    @property
    def shard_id(self):
        return self.get("shard_id")

    @property
    def db_index(self):
        return self.get("db_index")

    @property
    def reason(self):
        return self.get("reason")

    @property
    def error(self):
        return self.get("error")


def capture(event_type: str, title: str, content: str,
            tags: Optional[List[str]] = None, embedding: Optional[List[float]] = None,
            domain_key: Optional[str] = None, density_score: Optional[float] = None,
            sensitivity: Optional[str] = None,
            original_timestamp: Optional[str] = None,
            source_uri: Optional[str] = None,
            utility: Optional[float] = None) -> bool:
    """Saves a unit of experience (Module 5: Extract Invariants).

    `sensitivity` is 'normal' (default, plaintext -- the existing corpus),
    'private', or 'secret'. Private and secret bodies are AES-256-GCM encrypted
    by private_vault before they reach SQLite, so personal-scope material
    (finances, health, identity documents) is not readable from the DB file.
    Titles and tags stay plaintext: they are the only handle recall has on an
    encrypted shard, so keep identifying detail out of them.

    `original_timestamp` (ISO-8601 string) stamps migrated content at its TRUE
    era instead of migration time, so date-window queries and coverage
    histograms reflect when the experience actually happened. An unparseable
    value logs a warning and falls back to now -- it never crashes a write.

    `source_uri` and `utility` are compatibility fields used by relay and other
    publishers. Provenance is retained in the shard row, while `utility` seeds
    the usefulness prior without requiring callers to know the SQLite schema.
    """
    from . import private_vault as _pv  # pylint: disable=import-outside-toplevel
    from .brain_scan.redaction import redact_content  # pylint: disable=import-outside-toplevel

    # A shard is a durable publication surface. Redact credential-shaped text
    # before hashing, embedding, indexing, or encryption so neither SQLite nor
    # an embedding blob preserves a recoverable copy of a leaked credential.
    title = redact_content(str(title))
    content = redact_content(str(content))
    if tags:
        tags = [redact_content(str(tag)) for tag in tags]

    sensitivity = _pv.normalize_sensitivity(sensitivity)
    if not domain_key:
        domain_key = resolve_domain_from_path()

    if density_score is None:
        density_score = calculate_contrastive_perplexity(content)

    try:
        utility_score = float(utility) if utility is not None else 1.0
    except (TypeError, ValueError):
        logger.warning("capture: invalid utility %r; falling back to schema default", utility)
        utility_score = 1.0

    source_uri_value = (
        redact_content(str(source_uri)) if source_uri is not None else None
    )

    # Clean the content for O(1) deduplication hashing to exclude injected recall packets or static context.
    clean_content = content
    if "=== NOUGENSHARDS RECALL PACKET" in content:
        clean_content = content.split("=== NOUGENSHARDS RECALL PACKET")[0].strip()

    fhash = hashlib.md5(clean_content.encode("utf-8", errors="ignore")).hexdigest()

    from . import snapshot_mode  # pylint: disable=import-outside-toplevel
    if snapshot_mode.enabled():
        # This node serves read-only snapshot artifacts and must never write
        # sqlite (that is what corrupted every Space-local grid). Captures
        # forward to the writer node over the tunnel instead.
        fwd = snapshot_mode.forward_capture({
            "title": title, "content": content, "event_type": event_type,
            "tags": tags, "domain_key": domain_key,
            "density_score": density_score, "sensitivity": sensitivity,
            "original_timestamp": original_timestamp,
        })
        return CaptureResult(fwd)

    # Global Deduplication (Module 12): one indexed lookup in the central
    # hash index — O(1) — instead of scanning all 9 cluster databases.
    # The index also covers legacy hashes living in overflow DBs (a shard's
    # home shifts off its routing target when that DB was full at write time).
    dconn = _get_dedup_connection()
    try:
        _ensure_dedup_index(dconn)
        if dconn.execute("SELECT 1 FROM hashes WHERE file_hash = ?",
                         (fhash,)).fetchone():
            return CaptureResult(captured=False, reason="duplicate",
                                 error="duplicate: identical content is already in the vault")

        target_idx = get_write_index(fhash)

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
        if original_timestamp:
            try:
                # Validate; store the normalized ISO form so lexicographic
                # date-prefix comparisons (the window contract) stay sound.
                parsed = datetime.fromisoformat(
                    str(original_timestamp).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamp = parsed.astimezone(timezone.utc).isoformat().replace(
                    "+00:00", "Z")
            except (ValueError, TypeError):
                logger.warning(
                    "capture: unparseable original_timestamp %r; "
                    "falling back to now", original_timestamp)

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

        # Writes route AROUND corrupt DB files. capture() used to let a
        # corruption-class error raise straight out, and /sync/push turned
        # that into a 500 for its whole batch -- so every shard whose hash
        # routed to a malformed DB was un-ingestable, deterministically
        # (observed on the Space 2026-08-30: DB8 malformed, exactly the
        # batches carrying DB8-routed hashes kept failing all three retries).
        if target_idx in _QUARANTINED_WRITE_DBS:
            target_idx = _next_healthy_write_index(target_idx)
            init_db(target_idx)
        inserted = False
        for _reroute in range(MAX_DB_COUNT):
            conn = None
            try:
                # init_db and get_connection both open the DB file, so they
                # raise the same corruption-class errors as the INSERT and must
                # sit inside this guard.
                init_db(target_idx)
                conn = get_connection(target_idx)
                cursor = conn.execute("""
                    INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash, embedding, domain_key, density_score, sensitivity, enc, source_uri, utility_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (timestamp, event_type, title, stored_content, tags_str, fhash, emb_blob, domain_key, density_score, sensitivity, enc_flag, source_uri_value, utility_score))
                conn.commit()

                # Log CREATED event
                from . import history # pylint: disable=import-outside-toplevel
                history.log_event(cursor.lastrowid or 0, target_idx, "CREATED", new_score=utility_score)
                inserted = True
                break
            except sqlite3.IntegrityError:
                # Target DB already holds the hash (index was stale) — repair the
                # index so the next lookup short-circuits without touching shards.
                dconn.execute(
                    "INSERT OR IGNORE INTO hashes (file_hash, db_index) VALUES (?, ?)",
                    (fhash, target_idx))
                dconn.commit()
                return CaptureResult(captured=False, reason="duplicate",
                                     db_index=target_idx,
                                     error="duplicate: row already present in the routed DB")
            except sqlite3.OperationalError:
                # Locked/busy is NOT corruption: quarantining a merely-locked
                # DB would permanently divert its hash range. Preserve the
                # pre-quarantine contract and let the caller see it.
                raise
            except sqlite3.DatabaseError as db_err:
                # Checked AFTER IntegrityError (its subclass): reaching here
                # means the DB FILE is bad ("database disk image is
                # malformed"). Quarantine the index for this process, record
                # the degrade, and try the next healthy DB.
                from . import history  # pylint: disable=import-outside-toplevel
                _QUARANTINED_WRITE_DBS.add(target_idx)
                logger.error("grid DB %s quarantined for writes: %s: %s",
                             target_idx, type(db_err).__name__, db_err)
                try:
                    history.log_event(0, target_idx, "DB_DEGRADED",
                                      metadata={"error": f"write: {type(db_err).__name__}: {db_err}"})
                except Exception:  # pylint: disable=broad-except
                    pass
                try:
                    target_idx = _next_healthy_write_index(target_idx)
                except LookupError:
                    logger.error("capture dropped shard %r: every grid DB is "
                                 "quarantined for writes", title[:80])
                    return CaptureResult(
                        captured=False, reason="error",
                        error="every grid DB is quarantined for writes")
                init_db(target_idx)
            finally:
                if conn is not None:
                    conn.close()
        if not inserted:
            return CaptureResult(
                captured=False, reason="error",
                error="write did not land after exhausting healthy grid DBs")

        dconn.execute(
            "INSERT OR IGNORE INTO hashes (file_hash, db_index) VALUES (?, ?)",
            (fhash, target_idx))
        dconn.commit()
        return CaptureResult(captured=True, reason="written",
                             shard_id=int(cursor.lastrowid or 0),
                             db_index=target_idx)
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


#: Fallback multiplier applied to in-domain hits when the domain was resolved
#: implicitly from the process CWD (see retrieve). >1 keeps local context first
#: on ties without letting it mask cross-domain matches; 1.0 disables the bias.
DEFAULT_DOMAIN_BOOST = 1.2

#: Fallback bm25 magnitude that normalizes to 0.5 keyword strength. Chosen from
#: the measured live-corpus span (weak single-token OR hits ~6-12, near-exact
#: multi-term hits 20-90), so mid-strength matches land mid-scale instead of
#: everything saturating at ~1.0.
DEFAULT_BM25_HALF_SCORE = 20.0


def _bm25_half_score() -> float:
    """Resolve the bm25 half-strength scale: env first, logged fallback."""
    raw = os.environ.get("NOUGEN_BM25_HALF_SCORE")
    if raw:
        try:
            val = float(raw)
            if val > 0:
                return val
            logger.warning("NOUGEN_BM25_HALF_SCORE=%r must be > 0; "
                           "falling back to %s", raw, DEFAULT_BM25_HALF_SCORE)
        except ValueError:
            logger.warning("NOUGEN_BM25_HALF_SCORE=%r is not a number; "
                           "falling back to %s", raw, DEFAULT_BM25_HALF_SCORE)
    else:
        logger.debug("NOUGEN_BM25_HALF_SCORE unset; using fallback %s",
                     DEFAULT_BM25_HALF_SCORE)
    return DEFAULT_BM25_HALF_SCORE


def _domain_affinity_boost() -> float:
    """Resolve the implicit-domain affinity boost: env first, logged fallback."""
    raw = os.environ.get("NOUGEN_DOMAIN_BOOST")
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
            logger.warning("NOUGEN_DOMAIN_BOOST=%r must be > 0; "
                           "falling back to %s", raw, DEFAULT_DOMAIN_BOOST)
        except ValueError:
            logger.warning("NOUGEN_DOMAIN_BOOST=%r is not a number; "
                           "falling back to %s", raw, DEFAULT_DOMAIN_BOOST)
    else:
        logger.debug("NOUGEN_DOMAIN_BOOST unset; using fallback %s",
                     DEFAULT_DOMAIN_BOOST)
    return DEFAULT_DOMAIN_BOOST

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
    # strong hit (-8 -> 0.11) scored *below* a weak one (-0.5 -> 0.67). A raw
    # logistic 1/(1+e^bm25) fixed the inversion but saturates: measured corpus
    # scores span roughly -6 (weak single-token) to -90 (near-exact multi-term),
    # and the logistic maps ALL of them to ~1.0, so keyword strength contributed
    # a constant and stale high-utility rows outranked near-exact fresh matches.
    # Map through a rational saturation x/(x+half) instead: still monotonically
    # increasing in match strength and bounded in [0, 1), but discriminating
    # across the whole measured range. `half` is the bm25 magnitude that scores
    # 0.5 (env NOUGEN_BM25_HALF_SCORE; fallback from the measured corpus span).
    strength = max(0.0, -item["bm25_score"])
    norm_bm25 = strength / (strength + _bm25_half_score())

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

    # Synthesize Coherent Likelihood (Module 9). When the caller supplied no
    # query embedding the semantic lane is ABSENT, not zero-valued: weighting a
    # missing sensor as 0 capped likelihood at WEIGHT_BM25 and let the decayed
    # utility prior dominate every keyword-only retrieval. Renormalize over the
    # signal that actually exists (broken-sensor absence, HARDENING inv. 4).
    if query_embedding is None:
        likelihood = norm_bm25
    else:
        likelihood = (norm_bm25 * WEIGHT_BM25) + (sem_score * WEIGHT_SEMANTIC)

    # 3. Temporal decay factor (half-life of 30 days) to prevent stale successful sessions from dominating results
    decayed_utility = item["utility_score"] * _temporal_decay(item.get("timestamp"), now)

    # 4. Final relevance: a weighted blend of the likelihood signal and the decayed utility score
    item["final_score"] = (likelihood * WEIGHT_LIKELIHOOD) + (decayed_utility * WEIGHT_PRIOR)
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

    `joiner` sits BETWEEN the quoted tokens: the default " " keeps FTS5's
    implicit-AND semantics; pass " OR " for the ranked-OR retry (tokens stay
    quoted either way, so user text still cannot inject operators).
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


def bulk_ingest_event_types() -> List[str]:
    """Event types treated as bulk research corpus rather than agent memory.

    The vault holds two populations that were never separated: agent memory
    (doctrine, corrections, decisions, milestones) and a bulk research ingest
    (arXiv papers and similar). Measured 2026-08-14, the ingest population was
    ~92% of all rows, so an undifferentiated semantic search almost always
    returned a paper -- correctly, by similarity, and uselessly. A query about
    which port the model server listens on matched papers about audio models
    "listening".

    `domain_key` cannot separate them: it records the working directory capture
    ran in, so papers ingested from a repo carry the same domain as that repo's
    doctrine. `event_type` does separate them, and is compared case-insensitively
    because the column was never normalized ('milestone' and 'MILESTONE' both
    occur).
    """
    raw = os.environ.get("NOUGEN_RECALL_EXCLUDE_EVENT_TYPES", "IMPORT,INGEST")
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def _ingest_filter_sql(alias: str = "s", include_research: bool = False):
    """-> (sql_fragment, params). Fragment ends with ' AND ' or is empty."""
    if include_research:
        return "", ()
    excluded = bulk_ingest_event_types()
    if not excluded:
        return "", ()
    marks = ",".join("?" for _ in excluded)
    return f"UPPER({alias}.event_type) NOT IN ({marks}) AND ", tuple(excluded)


def _retrieve_db_workers() -> int:
    """Concurrent grid-DB scans per retrieval lane. Env-first (Rule 0.2)."""
    raw = os.environ.get("NOUGEN_RETRIEVE_DB_WORKERS", "")
    try:
        n = int(raw) if raw.strip() else 0
    except ValueError:
        logger.warning("NOUGEN_RETRIEVE_DB_WORKERS=%r is not an int; using auto", raw)
        n = 0
    if n <= 0:
        n = min(MAX_DB_COUNT, os.cpu_count() or 4)
    return max(1, n)


def _run_db_scans(scan_fn):
    """Run scan_fn(i) for every grid DB concurrently; yield (i, result) in DB order.

    The per-DB scan loops in both retrieval lanes were serial — on a 9-DB,
    six-figure-shard grid that alone was ~14s per pass (measured 2026-08-30).
    Each scan owns its connection, so threads never share sqlite handles, and
    yielding in DB order keeps downstream merge/sort output bit-identical to
    the serial loop.
    """
    import concurrent.futures  # pylint: disable=import-outside-toplevel
    workers = _retrieve_db_workers()
    if workers == 1:
        for i in range(1, MAX_DB_COUNT + 1):
            yield i, scan_fn(i)
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {i: executor.submit(copy_context().run, scan_fn, i)
                   for i in range(1, MAX_DB_COUNT + 1)}
        for i in range(1, MAX_DB_COUNT + 1):
            yield i, futures[i].result()


def _keyword_retrieve(query: str, limit: int = 20, query_embedding: Optional[List[float]] = None,
                      domain_key: str = "global", include_research: bool = False) -> list:
    """Scans for keyword matches using FTS5 (with LIKE fallback)."""
    from . import history, ngram  # pylint: disable=import-outside-toplevel

    # One reference clock for the whole scan (see _temporal_decay).
    query_now = datetime.now(timezone.utc)
    results = []
    missed_dbs = []  # DBs where both exact lanes missed; fed to the fuzzy pass below

    def _scan_db(i: int) -> tuple:
        """Scan one grid DB (thread-owned connection). Returns (rows, missed)."""
        from . import history  # pylint: disable=import-outside-toplevel
        # The existence probe belongs INSIDE the guard too. Path.exists() returns
        # False only for ENOENT/ENOTDIR; on EACCES/EPERM it RAISES. An
        # ACL-locked DB file would therefore escape the handler below and kill
        # the whole fan-out - the same failure the handler exists to stop,
        # through a different door, two lines earlier.
        #
        # (PowerShell's Test-Path has the opposite bug: it RETURNS $false on
        #  UnauthorizedAccessException, so "not allowed to look" reads as "not
        #  there". Python raising here is the better default - it just has to be
        #  caught rather than left outside the try.)
        db_rows: list = []
        accessed: list = []
        missed = False
        conn = None
        try:
            if not get_db_path(i).exists():
                return db_rows, missed
            conn = get_connection(i)
            fts_worked = False
            db_hits = 0
            fts_query = _build_fts_match_query(query)
            if fts_query is not None:
                # Attempt implicit-AND first, then a ranked-OR retry: FTS5's
                # implicit AND starves conversational multi-term queries (one
                # off-corpus token -> 0 rows), and the LIKE fallback below is
                # stricter still (substring of the WHOLE query). The OR retry
                # reuses the exact same safe-quoted tokens, and bm25 ranks
                # best-covering rows first, so AND-quality hits keep their spot.
                # Single-token queries produce an identical expression, so the
                # retry is skipped.
                attempts = [fts_query]
                or_query = _build_fts_match_query(query, joiner=" OR ")
                if or_query is not None and or_query != fts_query:
                    attempts.append(or_query)
                # The try guards ONLY the SQL: sqlite3.OperationalError here
                # means "FTS unavailable, use the LIKE fallback". Row processing
                # happens outside it so an unrelated error can't leave partially
                # appended FTS rows in `results` and then double-append the same
                # shards via the fallback (which scrambled retrieval ordering).
                res = None
                via_or_retry = False
                for match_expr in attempts:
                    try:
                        # domain_key None/"*" => search ALL domains (whole brain), not one bucket.
                        dom_clause = "" if domain_key in (None, "*") else "s.domain_key = ? AND "
                        dom_params = () if domain_key in (None, "*") else (domain_key,)
                        ing_clause, ing_params = _ingest_filter_sql("s", include_research)
                        cursor = conn.execute(f"""
                            SELECT s.id, s.timestamp, s.title, s.content, s.utility_score,
                                   s.embedding, s.tags, s.domain_key, s.density_score, bm25(shards_fts) as bm25_score
                            FROM shards s JOIN shards_fts ON s.id = shards_fts.rowid
                            WHERE {dom_clause}{ing_clause}shards_fts MATCH ?
                            ORDER BY bm25_score ASC, s.id ASC LIMIT ?
                        """, (*dom_params, *ing_params, match_expr, limit))
                        res = cursor.fetchall()
                    except sqlite3.OperationalError:
                        res = None
                    if res:
                        via_or_retry = match_expr is not fts_query
                        break
                if res:
                    for row in res:
                        accessed.append(row["id"])
                        item = _process_fts_result(row, i, query_embedding, query_now)
                        if via_or_retry:
                            item["_or_retry"] = True
                        db_rows.append(item)
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
                    accessed.append(item["id"])
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
                    db_rows.append(item)
                    db_hits += 1

            # Fuzzy lane is DEFERRED, not run here: note the miss and move on.
            # See the second pass below for why.
            if not fts_worked and db_hits == 0:
                missed = True
        except (sqlite3.DatabaseError, OSError) as exc:
            # ONE bad DB must not zero out the whole federated read. The try
            # around the FTS SQL below catches only sqlite3.OperationalError,
            # but a corrupt file raises sqlite3.DatabaseError ("database disk
            # image is malformed") -- its PARENT class, so that except never
            # matched. With no except on this loop, the error escaped the
            # for-loop entirely and every ranked read returned empty while the
            # other 8 DBs sat there healthy and unread.
            #
            # 2026-08-29: that is exactly what shipped. shards_coverage showed
            # databases_errored [{index:5, malformed}], and recall AND search
            # both returned 0 against a six-figure vault while shards_window --
            # which filters on timestamp and never touches this path -- happily
            # returned rows. Health said up the whole time.
            #
            # Degrade per DB: record it, skip it, keep scanning. A partial
            # answer from 8 DBs is worth infinitely more than a false empty,
            # and the log line names the index so the corrupt file is findable
            # instead of silently swallowed.
            logger.error("grid DB %s unreadable during scan, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            try:
                history.log_event(0, i, "DB_DEGRADED",
                                  metadata={"error": f"{type(exc).__name__}: {exc}"})
            except Exception:  # pylint: disable=broad-except
                pass
        finally:
            if conn is not None:
                conn.close()
        # ONE batched history write per DB scan. The per-row log_event calls
        # this replaces each opened a connection, INSERTed, committed, and
        # closed - ~360 synchronous commits per recall, a measured multi-second
        # tax that also serializes parallel scans on the history DB lock.
        if accessed:
            history.log_events([(sid, i, "ACCESSED") for sid in accessed])
        return db_rows, missed

    for i, (db_rows, missed) in _run_db_scans(_scan_db):
        results.extend(db_rows)
        if missed:
            missed_dbs.append(i)

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
            ing_clause, ing_params = _ingest_filter_sql("shards", include_research)
            # Fragment ends in " AND ", so strip it when it is the only predicate.
            if dom_params and ing_clause:
                where = "WHERE domain_key = ? AND " + ing_clause[:-5]
            elif dom_params:
                where = "WHERE domain_key = ?"
            elif ing_clause:
                where = "WHERE " + ing_clause[:-5]
            else:
                where = ""
            dom_params = (*dom_params, *ing_params)
            for i in missed_dbs:
                # Same guard as the first pass above, and this pass needs it
                # MORE: missed_dbs is by definition the set the exact lanes came
                # up short on, so a degraded DB is likelier to be in here than
                # in a random sweep. It was missed on 2026-08-29 because the
                # first pass in this same function was fixed and this one was
                # not -- one function, two fan-outs, one patch.
                conn = None
                try:
                    conn = get_connection(i)
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
                except (sqlite3.DatabaseError, OSError) as exc:
                    logger.error("grid DB %s unreadable during fuzzy pass, skipping it: %s: %s",
                                 i, type(exc).__name__, exc)
                    try:
                        history.log_event(0, i, "DB_DEGRADED",
                                          metadata={"error": f"{type(exc).__name__}: {exc}",
                                                    "pass": "fuzzy"})
                    except Exception:  # pylint: disable=broad-except
                        pass
                    continue
                finally:
                    if conn is not None:
                        conn.close()

    # Tiered ordering: every full-coverage hit (FTS implicit-AND / LIKE)
    # outranks every OR-retry hit, which outranks every fuzzy hit, regardless
    # of raw score - the lanes' score scales are not comparable (trigram-FTS
    # bm25 magnitudes are tiny, so a weighted exact score can sit below a
    # strong fuzzy similarity, and an OR hit covering one token must never
    # displace an AND hit covering all of them). Score is rounded so
    # sub-epsilon temporal-decay jitter can't reorder near-ties; bm25 (more
    # negative == stronger, absent treated as weakest) breaks sub-round ties
    # by match strength - on small corpora trigram bm25 is ~1e-6 and the
    # rounding erases it, and falling straight to insertion order picked the
    # wrong shard; then (_db_index, id) ASC pins true ties so identical
    # queries never reorder run-to-run.
    def _tier(x):
        if x.get("_fuzzy"):
            return 2
        if x.get("_or_retry"):
            return 1
        return 0
    results.sort(key=lambda x: (_tier(x),
                                -round(x.get("final_score", 0.0), 6),
                                x.get("bm25_score") or 0.0,
                                x.get("_db_index", 0),
                                x.get("id", 0)))
    return results[:limit]


def _vector_cache_enabled() -> bool:
    return os.environ.get("NOUGEN_VECTOR_CACHE", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


#: Process-level embedding matrix cache, one entry per grid DB. Selecting the
#: embedding column from `shards` still reads every row's FULL record (content
#: included) from disk - a per-query vector scan was effectively a 10.7GB table
#: scan across the grid (measured 27s, 2026-08-30). The cache pays that read
#: once per process and answers subsequent queries with an in-RAM matmul.
#: ~800MB RSS for a 260k-shard grid at 768 dims. NOUGEN_VECTOR_CACHE=0 turns
#: the whole semantic lane OFF (there is no uncached fallback scan - see
#: _vector_retrieve), warned once per process.
_VECTOR_CACHE: dict = {}
_VECTOR_LANE_OFF_WARNED = False
_VECTOR_CACHE_LOCK = _threading.Lock()  # eager: lazy init of a lock is itself a race
#: One build lock PER DB, not one for the grid. A single grid-wide lock
#: serialized the nine warm-up builds (15.7s cold, measured) and, worse, made
#: every request that arrived during a build queue behind ALL nine. On
#: phoebus 2026-09-04 one six-way burst 32s after boot left 327 threads
#: parked on that lock, each holding its sqlite connections, draining at ~10
#: threads per 6 minutes while every recall missed its deadline. Per-DB locks
#: let the builds run in parallel and let a waiter wait for one matrix, not
#: the grid.
_VECTOR_DB_LOCKS: dict = {}
_VECTOR_WAIT_WARNED: set = set()


def _vector_cache_lock(i: Optional[int] = None):
    """Build lock for DB ``i``; with no argument, the table guard (compat)."""
    if i is None:
        return _VECTOR_CACHE_LOCK
    with _VECTOR_CACHE_LOCK:
        lock = _VECTOR_DB_LOCKS.get(i)
        if lock is None:
            lock = _VECTOR_DB_LOCKS[i] = _threading.Lock()
        return lock


def _vector_cache_wait_s() -> float:
    """How long a recall may wait for another thread's matrix build.

    Bounded on purpose: a request that cannot get the matrix in time answers
    from the keyword lane (and from the stale matrix if one exists) instead of
    becoming a straggler that outlives its own deadline. Env-first (Rule 0.2).
    Default 5s: a warm build of one 110MB grid DB is ~0.5s, a cold one a few
    seconds; anything longer means the process is in trouble and piling on
    makes it worse.
    """
    raw = os.environ.get("NOUGEN_VECTOR_CACHE_WAIT_S", "")
    try:
        return float(raw) if raw.strip() else 5.0
    except ValueError:
        logger.warning("NOUGEN_VECTOR_CACHE_WAIT_S=%r is not a number; using 5.0", raw)
        return 5.0


def _db_write_signature(i: int) -> tuple:
    """Staleness key for DB i. Includes the -wal file: under WAL mode a write
    lands there first and the main file's mtime does not move until checkpoint."""
    sig = []
    base = str(get_db_path(i))
    for suffix in ("", "-wal"):
        try:
            st = os.stat(base + suffix)
            sig.append((st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append(None)
    return tuple(sig)


def _vector_cache_entry(i: int, conn) -> Optional[dict]:
    """Return the (fresh) cache entry for DB i, loading or refreshing as needed.

    Refresh strategy: the grid is append-mostly. On a signature change, rows
    with id > the cached max are fetched and appended; a shrink in embedded-row
    count forces a full reload. An embedding UPDATEd in place (backfill re-run)
    stays stale until the next full reload - logged, accepted: the alternative
    is re-reading the full table per capture, which is the cost this cache
    exists to kill.
    """
    sig = _db_write_signature(i)
    path = str(get_db_path(i))
    entry = _VECTOR_CACHE.get(i)
    if entry is not None and entry["sig"] == sig and entry["path"] == path:
        return entry
    lock = _vector_cache_lock(i)
    if not lock.acquire(timeout=_vector_cache_wait_s()):
        # Another thread is building this DB's matrix and has held it longer
        # than the wait budget. Do NOT queue: a stale matrix still ranks the
        # rows it knows about, and None hands this DB to the keyword lane.
        # Either answer inside the recall deadline; a queued thread does not.
        # Warned once per DB per process - the condition repeats by nature.
        if i not in _VECTOR_WAIT_WARNED:
            _VECTOR_WAIT_WARNED.add(i)
            logger.warning("grid DB %s: vector cache build held its lock past %.1fs; "
                           "answering %s for this recall (NOUGEN_VECTOR_CACHE_WAIT_S)",
                           i, _vector_cache_wait_s(),
                           "from the stale matrix" if entry is not None and entry["path"] == path
                           else "keyword-only")
        if entry is not None and entry["path"] == path:
            return entry
        return None
    try:
        entry = _VECTOR_CACHE.get(i)
        if entry is not None and entry["sig"] == sig and entry["path"] == path:
            return entry
        # The cache key is the DB index, but the index can point at a DIFFERENT
        # file mid-process (tests and tools repoint NOUGEN_VAULT_DIR - same
        # reason init_db keys its guard by vault dir). Appending one vault's
        # rows onto another's matrix would silently corrupt ranking, so a path
        # change always forces a full reload. [codex finding, 2026-08-30]
        if entry is not None and entry["path"] != path:
            entry = None
        count = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM shards WHERE embedding IS NOT NULL"
        ).fetchone()
        n_embedded, max_id = int(count[0]), int(count[1])
        since_id = 0
        if entry is not None and n_embedded >= entry["n_embedded"] and len(entry["ids"]):
            since_id = entry["max_id"]  # append-only fast path
        else:
            entry = None  # full (re)load
        cursor = conn.execute("""
            SELECT id, timestamp, utility_score, domain_key, event_type, embedding
            FROM shards WHERE embedding IS NOT NULL AND id > ? ORDER BY id ASC
        """, (since_id,))
        ids, ts, util, dom, etype, blobs, legacy = [], [], [], [], [], [], []
        dim = entry["dim"] if entry else None
        for row in cursor:
            emb = row["embedding"]
            if isinstance(emb, (bytes, bytearray)) and not emb.startswith(b"[") \
                    and len(emb) % 4 == 0 and len(emb) > 0:
                row_dim = len(emb) // 4
                if dim is None:
                    dim = row_dim
                if row_dim == dim:
                    ids.append(row["id"])
                    ts.append(row["timestamp"])
                    util.append(row["utility_score"] if row["utility_score"] is not None else 0.0)
                    dom.append(row["domain_key"] or "")
                    etype.append((row["event_type"] or "").upper())
                    blobs.append(bytes(emb))
                    continue
            legacy.append((row["id"], row["utility_score"] or 0.0, row["timestamp"],
                           row["domain_key"] or "", (row["event_type"] or "").upper(), emb))
        if blobs:
            new_matrix = np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(len(blobs), dim)
        else:
            new_matrix = np.zeros((0, dim or 0), dtype=np.float32)
        if entry is not None:
            fresh = {
                "sig": sig, "path": path, "dim": dim, "n_embedded": n_embedded, "max_id": max_id,
                "ids": entry["ids"] + ids, "ts": entry["ts"] + ts,
                "util": np.concatenate([entry["util"], np.asarray(util, dtype=np.float32)]),
                "dom": entry["dom"] + dom, "etype": entry["etype"] + etype,
                "matrix": np.vstack([entry["matrix"], new_matrix]) if len(ids) else entry["matrix"],
                "legacy": entry["legacy"] + legacy,
            }
        else:
            fresh = {
                "sig": sig, "path": path, "dim": dim, "n_embedded": n_embedded, "max_id": max_id,
                "ids": ids, "ts": ts, "util": np.asarray(util, dtype=np.float32),
                "dom": dom, "etype": etype, "matrix": new_matrix, "legacy": legacy,
            }
        # Consistency gate: after an incremental append the cache must hold
        # exactly the DB's embedded-row count. A backfill that fills NULL
        # embeddings on OLD ids grows the count without growing max_id, which
        # the append path can never see - detected here and answered with a
        # full reload instead of serving a silently incomplete matrix.
        # [codex finding, 2026-08-30]
        if since_id and (len(fresh["ids"]) + len(fresh["legacy"])) != n_embedded:
            logger.info(
                "vector cache for DB %s inconsistent after incremental refresh "
                "(%d cached vs %d embedded) - backfill or delete detected, full reload",
                i, len(fresh["ids"]) + len(fresh["legacy"]), n_embedded)
            cursor = conn.execute("""
                SELECT id, timestamp, utility_score, domain_key, event_type, embedding
                FROM shards WHERE embedding IS NOT NULL ORDER BY id ASC
            """)
            ids, ts, util, dom, etype, blobs, legacy = [], [], [], [], [], [], []
            dim = None
            for row in cursor:
                emb = row["embedding"]
                if isinstance(emb, (bytes, bytearray)) and not emb.startswith(b"[") \
                        and len(emb) % 4 == 0 and len(emb) > 0:
                    row_dim = len(emb) // 4
                    if dim is None:
                        dim = row_dim
                    if row_dim == dim:
                        ids.append(row["id"])
                        ts.append(row["timestamp"])
                        util.append(row["utility_score"] if row["utility_score"] is not None else 0.0)
                        dom.append(row["domain_key"] or "")
                        etype.append((row["event_type"] or "").upper())
                        blobs.append(bytes(emb))
                        continue
                legacy.append((row["id"], row["utility_score"] or 0.0, row["timestamp"],
                               row["domain_key"] or "", (row["event_type"] or "").upper(), emb))
            matrix = (np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(len(blobs), dim)
                      if blobs else np.zeros((0, dim or 0), dtype=np.float32))
            fresh = {
                "sig": _db_write_signature(i), "path": path, "dim": dim,
                "n_embedded": n_embedded, "max_id": max_id,
                "ids": ids, "ts": ts, "util": np.asarray(util, dtype=np.float32),
                "dom": dom, "etype": etype, "matrix": matrix, "legacy": legacy,
            }
        _VECTOR_CACHE[i] = fresh
        return fresh
    finally:
        lock.release()


def _vector_retrieve(query_embedding: Optional[List[float]], limit: int = 20,
                     domain_key: str = "global", include_research: bool = False) -> list:
    """Scans for semantic vector matches independent of FTS.

    Scoring runs against the per-DB embedding matrix cache (one BLAS matvec -
    see _VECTOR_CACHE); only each DB's top `limit` candidates are then fetched
    and hydrate()d from sqlite. hydrate() can mean a DPAPI decrypt per row, so
    it must never run across the whole corpus.
    """
    if query_embedding is None:
        return []

    # There is deliberately NO uncached scan path: the pre-cache implementation
    # read every row's full record per query (a 10.7GB effective scan, 27s).
    # So the cache switch is a LANE switch - turning it off turns semantic
    # recall off entirely, and that must be loud, not a silent empty result.
    if not _vector_cache_enabled():
        global _VECTOR_LANE_OFF_WARNED  # pylint: disable=global-statement
        if not _VECTOR_LANE_OFF_WARNED:
            logger.warning(
                "NOUGEN_VECTOR_CACHE=0: the semantic recall lane is OFF "
                "(no uncached scan path exists) - recall is keyword-only")
            _VECTOR_LANE_OFF_WARNED = True
        return []

    from . import history  # pylint: disable=import-outside-toplevel

    # One reference clock for the whole scan (see _temporal_decay).
    query_now = datetime.now(timezone.utc)
    q_vec = np.asarray(query_embedding, dtype=np.float32)
    qdim = int(q_vec.shape[0])
    excluded_types = frozenset() if include_research else frozenset(bulk_ingest_event_types())

    def _scan_db(i: int) -> list:
        from . import history  # pylint: disable=import-outside-toplevel
        db_rows: list = []
        conn = None
        try:
            # Path.exists() raises on EACCES (only ENOENT/ENOTDIR are False),
            # so the probe stays inside the guard - same rationale as the
            # keyword lane.
            if not get_db_path(i).exists():
                return db_rows
            conn = get_connection(i)
            cache = _vector_cache_entry(i, conn)
            scored = []  # (final_score, id)
            if cache and cache["dim"] == qdim and len(cache["ids"]):
                sem_scores = np.array(cache["matrix"] @ q_vec)
                # Mask rows excluded by domain scope / ingest filter by sinking
                # their scores below any real cosine instead of copying the
                # matrix per query.
                if domain_key not in (None, "*"):
                    mask = np.fromiter((d != domain_key for d in cache["dom"]),
                                       dtype=bool, count=len(cache["dom"]))
                    sem_scores[mask] = -1e9
                if excluded_types:
                    mask = np.fromiter((e in excluded_types for e in cache["etype"]),
                                       dtype=bool, count=len(cache["etype"]))
                    sem_scores[mask] = -1e9
                # Exact-score (timestamp parse + decay) only a semantic-top
                # pool: _temporal_decay parses an ISO timestamp per call and
                # doing that for every row was the residual latency after the
                # matmul. The prior term is bounded (<= WEIGHT_PRIOR * utility),
                # so a generous pool cannot exclude a row exact scoring would
                # have promoted into the top `limit`.
                pool_n = min(len(cache["ids"]), max(limit * 8, 256))
                if pool_n < len(cache["ids"]):
                    pool_idx = np.argpartition(-sem_scores, pool_n - 1)[:pool_n]
                else:
                    pool_idx = np.arange(len(cache["ids"]))
                for idx in pool_idx:
                    if sem_scores[idx] <= -1e8:
                        continue
                    decayed_utility = float(cache["util"][idx]) * _temporal_decay(cache["ts"][idx], query_now)
                    scored.append((float(sem_scores[idx]) * WEIGHT_LIKELIHOOD
                                   + decayed_utility * WEIGHT_PRIOR, int(cache["ids"][idx])))
                for sid, utility, ts, dom, etype, emb in cache["legacy"]:
                    if domain_key not in (None, "*") and dom != domain_key:
                        continue
                    if etype in excluded_types:
                        continue
                    try:
                        emb_array = np.array(json.loads(emb.decode()), dtype=np.float32) \
                            if emb.startswith(b"[") else np.frombuffer(emb, dtype=np.float32)
                        sem = float(np.dot(q_vec, emb_array)) if emb_array.shape[0] == qdim else 0.0
                    except Exception:  # pylint: disable=broad-except
                        sem = 0.0
                    decayed_utility = utility * _temporal_decay(ts, query_now)
                    scored.append((sem * WEIGHT_LIKELIHOOD + decayed_utility * WEIGHT_PRIOR, sid))
            elif cache and cache["dim"] not in (None, qdim):
                logger.warning(
                    "vector lane skipped on DB %s: cached embedding dim %s != query dim %s "
                    "(embed model changed?)", i, cache["dim"], qdim)
            if not scored:
                return db_rows
            scored.sort(key=lambda t: (-round(t[0], 6), t[1]))
            top = scored[:limit]
            placeholders = ",".join("?" for _ in top)
            by_id = {sid: score for score, sid in top}
            cursor = conn.execute(f"""
                SELECT id, timestamp, title, content, utility_score, embedding, tags, domain_key
                FROM shards WHERE id IN ({placeholders})
            """, [sid for _, sid in top])
            for row in cursor:
                item = hydrate(dict(row))
                item["_db_index"] = i
                item["final_score"] = by_id.get(item["id"], 0.0)
                db_rows.append(item)
        except (sqlite3.DatabaseError, OSError) as exc:
            # ONE bad DB must not zero out the whole federated read - degrade
            # per DB: record it, skip it, keep scanning (see keyword lane for
            # the 2026-08-29 incident that mandates this).
            logger.error("grid DB %s unreadable during scan, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            try:
                history.log_event(0, i, "DB_DEGRADED",
                                  metadata={"error": f"{type(exc).__name__}: {exc}"})
            except Exception:  # pylint: disable=broad-except
                pass
        finally:
            if conn is not None:
                conn.close()
        return db_rows

    results = []
    for _i, db_rows in _run_db_scans(_scan_db):
        results.extend(db_rows)

    # Deterministic order: score DESC (rounded so sub-epsilon temporal-decay
    # jitter doesn't reorder near-ties run-to-run), then (_db_index, id) ASC.
    results.sort(key=lambda x: (-round(x.get("final_score", 0.0), 6), x.get("_db_index", 0), x.get("id", 0)))
    top_results = results[:limit]

    history.log_events([(item["id"], item["_db_index"], "ACCESSED") for item in top_results])

    return top_results


def reciprocal_rank_fusion(result_lists: List[List[dict]], k: int = 60,
                           weights: Optional[List[float]] = None) -> List[dict]:
    """
    Module 8 / 21: Reciprocal Rank Fusion (RRF) to merge multiple ranked lists.

    Fuses by POSITION only: score = 1/(k+rank), summed across lists. Callers that
    want match quality to influence the merge must hand their list in ranked
    order — that is the supported lever, and it keeps this function's arithmetic
    exactly as specified.
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

    for list_idx, rank_list in enumerate(result_lists):
        if not rank_list:
            continue
        # Optional per-list weight (default 1.0): lets a caller declare one
        # lane authoritative without changing the 1/(k+rank) arithmetic.
        weight = 1.0
        if weights is not None and list_idx < len(weights):
            weight = float(weights[list_idx])
        for rank_idx, item in enumerate(rank_list):
            key = get_rrf_key(item)
            rank = rank_idx + 1
            score = weight / (k + rank)
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

    # Tie-break fields are stringified: grid rows carry int _db_index/id while
    # federated lanes (local vaults, cloud) carry strings ("vault_<stem>",
    # "vault_x_<hash>"), and Python 3 refuses int<str — one tied score across
    # lanes and the whole federated merge raised TypeError. The tie-break only
    # needs determinism, not numeric order, so lexicographic is sufficient.
    merged.sort(key=lambda x: (-round(x["final_score"], 6),
                               str(x.get("_db_index", 0)), str(x.get("id", 0))))
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
             domain_key: Optional[str] = None, include_research: bool = False) -> list:
    """
    Advanced Retrieval (Module 21): Runs both keyword (FTS/LIKE) and vector (semantic)
    searches in parallel lanes and merges them using Reciprocal Rank Fusion (RRF).
    When NOUGEN_RERANK=1, a cross-encoder reranks the top RRF candidates (Stage 2).
    """
    import concurrent.futures

    # Ensure all existing shard databases are schema-upgraded to the current
    # version before querying. Per-DB guard for the same reason as the fan-outs
    # below: Path.exists() RAISES on EACCES (only ENOENT/ENOTDIR return False)
    # and init_db opens the file, so one unreadable DB here would abort recall
    # before a single query ran -- upstream of every handler that exists to
    # prevent exactly that.
    for i in range(1, MAX_DB_COUNT + 1):
        try:
            if get_db_path(i).exists():
                init_db(i)
        except (sqlite3.DatabaseError, OSError) as exc:
            logger.error("grid DB %s unreadable during schema upgrade, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            continue

    # An explicit domain_key is a caller's deliberate scope and stays exclusive
    # (see test_domain_isolation_capture_and_retrieve). A domain resolved
    # implicitly from the process CWD is an accident of where the reader happens
    # to run, so it may only BOOST ranking, never GATE recall -- otherwise
    # shards written under another CWD-domain stay permanently invisible
    # whenever the scoped pass returns anything at all.
    explicit_domain = bool(domain_key)
    if not domain_key:
        domain_key = resolve_domain_from_path()
        
    if query_embedding is not None:
        arr = np.array(query_embedding, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            query_embedding = arr / norm
    elif _query_embed_enabled():
        # No caller in the MCP/app path ever passed a query embedding, which
        # left the vector lane permanently dark (see _embed_query). Compute one
        # here, best-effort, so semantic recall works for every entry point.
        query_embedding = _embed_query(query)

    candidate_limit = max(limit * 2, 20)

    def run_parallel_retrieval(active_domain: str) -> list:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_keyword = executor.submit(
                copy_context().run, _keyword_retrieve, query, candidate_limit,
                query_embedding, active_domain, include_research
            )
            future_vector = executor.submit(
                copy_context().run, _vector_retrieve, query_embedding,
                candidate_limit, active_domain, include_research
            )
            
            keyword_results = future_keyword.result()
            vector_results = future_vector.result()
            
        return reciprocal_rank_fusion([keyword_results, vector_results], k=60)

    if domain_key != "*" and not explicit_domain:
        # Implicit CWD-domain: scoped-plus-global fusion, not scoped-else-
        # global. Always run the whole-brain pass and merge, multiplying
        # scoped (in-domain) scores by a domain-affinity boost so local
        # context still ranks first on ties but can no longer mask
        # near-exact matches that live under another writer's CWD-domain.
        # The two passes are independent, so they run CONCURRENTLY - the
        # serial version doubled recall latency on every implicit-domain call.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_scoped = executor.submit(copy_context().run, run_parallel_retrieval, domain_key)
            future_whole = executor.submit(copy_context().run, run_parallel_retrieval, "*")
            all_results = future_scoped.result()
            whole_brain = future_whole.result()
    else:
        all_results = run_parallel_retrieval(domain_key)
        whole_brain = None
        if domain_key != "*" and not all_results:
            # Fallback: if the deliberately-scoped pass found nothing, sweep the
            # ENTIRE brain (all domain_keys). Without this, recall stays siloed
            # to one bucket (e.g. 'global' = <2% of shards) and misses the rest.
            all_results = run_parallel_retrieval("*")

    if whole_brain is not None:
            boost = _domain_affinity_boost()
            fused: dict = {}
            for item in whole_brain:
                fused[(item.get("_db_index", 0), item.get("id", 0))] = item
            for item in all_results:
                key = (item.get("_db_index", 0), item.get("id", 0))
                boosted = item.get("final_score", 0.0) * boost
                prior = fused.get(key)
                if prior is None or boosted > prior.get("final_score", 0.0):
                    item["final_score"] = boosted
                    fused[key] = item
            all_results = sorted(fused.values(),
                                 key=lambda x: (-x.get("final_score", 0.0),
                                                x.get("_db_index", 0),
                                                x.get("id", 0)))

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
        # The existence probe belongs INSIDE the guard too. Path.exists() returns
        # False only for ENOENT/ENOTDIR; on EACCES/EPERM it RAISES. An
        # ACL-locked DB file would therefore escape the handler below and kill
        # the whole fan-out - the same failure the handler exists to stop,
        # through a different door, two lines earlier.
        #
        # (PowerShell's Test-Path has the opposite bug: it RETURNS $false on
        #  UnauthorizedAccessException, so "not allowed to look" reads as "not
        #  there". Python raising here is the better default - it just has to be
        #  caught rather than left outside the try.)
        conn = None
        try:
            if not get_db_path(i).exists():
                continue
            conn = get_connection(i)
            if conn.execute("SELECT 1 FROM shards WHERE id = ?", (shard_id,)).fetchone():
                found.append(i)
        except sqlite3.Error:
            continue
        except (sqlite3.DatabaseError, OSError) as exc:
            # ONE bad DB must not zero out the whole federated read. The try
            # around the FTS SQL below catches only sqlite3.OperationalError,
            # but a corrupt file raises sqlite3.DatabaseError ("database disk
            # image is malformed") -- its PARENT class, so that except never
            # matched. With no except on this loop, the error escaped the
            # for-loop entirely and every ranked read returned empty while the
            # other 8 DBs sat there healthy and unread.
            #
            # 2026-08-29: that is exactly what shipped. shards_coverage showed
            # databases_errored [{index:5, malformed}], and recall AND search
            # both returned 0 against a six-figure vault while shards_window --
            # which filters on timestamp and never touches this path -- happily
            # returned rows. Health said up the whole time.
            #
            # Degrade per DB: record it, skip it, keep scanning. A partial
            # answer from 8 DBs is worth infinitely more than a false empty,
            # and the log line names the index so the corrupt file is findable
            # instead of silently swallowed.
            logger.error("grid DB %s unreadable during scan, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            try:
                from . import history  # pylint: disable=import-outside-toplevel
                history.log_event(0, i, "DB_DEGRADED",
                                  metadata={"error": f"{type(exc).__name__}: {exc}"})
            except Exception:  # pylint: disable=broad-except
                pass
            continue
        finally:
            if conn is not None:
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
        # The existence probe belongs INSIDE the guard too. Path.exists() returns
        # False only for ENOENT/ENOTDIR; on EACCES/EPERM it RAISES. An
        # ACL-locked DB file would therefore escape the handler below and kill
        # the whole fan-out - the same failure the handler exists to stop,
        # through a different door, two lines earlier.
        #
        # (PowerShell's Test-Path has the opposite bug: it RETURNS $false on
        #  UnauthorizedAccessException, so "not allowed to look" reads as "not
        #  there". Python raising here is the better default - it just has to be
        #  caught rather than left outside the try.)
        conn = None
        try:
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
            else:
                continue
        except (sqlite3.DatabaseError, OSError) as exc:
            # Found by tests/test_grid_fanout_guard_invariant.py after TWO
            # careful human reads of this file missed it. It got the
            # open-inside-the-try placement in the first sweep but never the
            # handler, so a corrupt DB still aborted the walk and every later
            # index went unchecked -- silently reporting "shard not found".
            logger.error("grid DB %s unreadable while marking shard %s, skipping it: %s: %s",
                         i, shard_id, type(exc).__name__, exc)
            continue
        finally:
            if conn is not None:
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
        # The existence probe belongs INSIDE the guard too. Path.exists() returns
        # False only for ENOENT/ENOTDIR; on EACCES/EPERM it RAISES. An
        # ACL-locked DB file would therefore escape the handler below and kill
        # the whole fan-out - the same failure the handler exists to stop,
        # through a different door, two lines earlier.
        #
        # (PowerShell's Test-Path has the opposite bug: it RETURNS $false on
        #  UnauthorizedAccessException, so "not allowed to look" reads as "not
        #  there". Python raising here is the better default - it just has to be
        #  caught rather than left outside the try.)
        conn = None
        try:
            if not get_db_path(i).exists():
                continue
            conn = get_connection(i)
            conn.execute("UPDATE shards SET utility_score = utility_score * ?", (factor,))
            conn.commit()
        except (sqlite3.DatabaseError, OSError) as exc:
            # ONE bad DB must not zero out the whole federated read. The try
            # around the FTS SQL below catches only sqlite3.OperationalError,
            # but a corrupt file raises sqlite3.DatabaseError ("database disk
            # image is malformed") -- its PARENT class, so that except never
            # matched. With no except on this loop, the error escaped the
            # for-loop entirely and every ranked read returned empty while the
            # other 8 DBs sat there healthy and unread.
            #
            # 2026-08-29: that is exactly what shipped. shards_coverage showed
            # databases_errored [{index:5, malformed}], and recall AND search
            # both returned 0 against a six-figure vault while shards_window --
            # which filters on timestamp and never touches this path -- happily
            # returned rows. Health said up the whole time.
            #
            # Degrade per DB: record it, skip it, keep scanning. A partial
            # answer from 8 DBs is worth infinitely more than a false empty,
            # and the log line names the index so the corrupt file is findable
            # instead of silently swallowed.
            logger.error("grid DB %s unreadable during scan, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            try:
                from . import history  # pylint: disable=import-outside-toplevel
                history.log_event(0, i, "DB_DEGRADED",
                                  metadata={"error": f"{type(exc).__name__}: {exc}"})
            except Exception:  # pylint: disable=broad-except
                pass
            continue
        finally:
            if conn is not None:
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
        # The existence probe belongs INSIDE the guard too. Path.exists() returns
        # False only for ENOENT/ENOTDIR; on EACCES/EPERM it RAISES. An
        # ACL-locked DB file would therefore escape the handler below and kill
        # the whole fan-out - the same failure the handler exists to stop,
        # through a different door, two lines earlier.
        #
        # (PowerShell's Test-Path has the opposite bug: it RETURNS $false on
        #  UnauthorizedAccessException, so "not allowed to look" reads as "not
        #  there". Python raising here is the better default - it just has to be
        #  caught rather than left outside the try.)
        conn = None
        try:
            if not get_db_path(i).exists():
                continue
            conn = get_connection(i)
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
        except (sqlite3.DatabaseError, OSError) as exc:
            # ONE bad DB must not zero out the whole federated read. The try
            # around the FTS SQL below catches only sqlite3.OperationalError,
            # but a corrupt file raises sqlite3.DatabaseError ("database disk
            # image is malformed") -- its PARENT class, so that except never
            # matched. With no except on this loop, the error escaped the
            # for-loop entirely and every ranked read returned empty while the
            # other 8 DBs sat there healthy and unread.
            #
            # 2026-08-29: that is exactly what shipped. shards_coverage showed
            # databases_errored [{index:5, malformed}], and recall AND search
            # both returned 0 against a six-figure vault while shards_window --
            # which filters on timestamp and never touches this path -- happily
            # returned rows. Health said up the whole time.
            #
            # Degrade per DB: record it, skip it, keep scanning. A partial
            # answer from 8 DBs is worth infinitely more than a false empty,
            # and the log line names the index so the corrupt file is findable
            # instead of silently swallowed.
            logger.error("grid DB %s unreadable during scan, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            try:
                from . import history  # pylint: disable=import-outside-toplevel
                history.log_event(0, i, "DB_DEGRADED",
                                  metadata={"error": f"{type(exc).__name__}: {exc}"})
            except Exception:  # pylint: disable=broad-except
                pass
            continue
        finally:
            if conn is not None:
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
