"""Attribution-guided utility: credit shards by observed CONTRIBUTION, not by rank.

WHY THIS EXISTS
---------------
`AttriMem: Attribution-Guided Process Feedback for Agent Memory Learning`
(arXiv 2607.21106) argues that outcome-level reward cannot
identify WHICH retrieved memories actually supported an answer, and that credit
should come from each memory's real contribution instead.

Today NouGen's ranking prior (`shards.utility_score`) is not a contribution
signal at all. Two things move it:

  * `mark_shard()` / the `mark_utility` MCP tool -- a manual, binary,
    outcome-level verdict (+1.0 / -0.5); and
  * bulk-ingest defaults, which stamp an entire batch of rows at one high
    prior that no downstream outcome ever earned.

HONEST STATEMENT OF WHAT DOES NOT EXIST
---------------------------------------
**Nothing downstream currently reports which shards an agent actually used or
cited.** The `ACCESSED` events written by the retrieval lanes are logged at
*retrieval* time -- they record that a shard was RETURNED, i.e. its rank. Using
them as attribution would launder retrieval rank into a "contribution" signal
and make the rich-get-richer loop worse while looking like evidence. They are
therefore deliberately NOT read here.

So this module implements the smallest honest version: an **explicit API the
caller invokes** to declare which shards it used. No signal is inferred, no
signal is fabricated. Until a caller calls it, `observed_prior()` reports "no
evidence" and ranking falls back to the existing prior unchanged.

WHAT IS DELIBERATELY NOT IMPLEMENTED
------------------------------------
AttriMem's actual contribution is an RL framework: token-level local rewards
combined with a global outcome reward, optimizing a memory-construction policy.
Both the token-level attribution (needs logprobs/gradients over the generating
model) and the policy optimization are GPU-bound fine-tuning. The Stadium is an
RTX 2080 Super with 8GB VRAM. **The RL half is skipped, explicitly.** This is
the logging half only: record real usage now so a contribution-based tiebreak
has ground truth to stand on later.

COST
----
Writes go through a bounded queue drained by one daemon thread, so
`record_usage()` never blocks a recall path and never touches SQLite on the
caller's thread. Overflow drops and counts rather than blocking -- a dropped
telemetry row must never stall retrieval. Reads use one aggregate query cached
behind a TTL, so ranking does no per-item I/O.

RULE 0.2: every threshold, half-life, weight, and TTL resolves env -> config ->
logged fallback.
"""
import atexit
import json
import logging
import os
import queue
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Configuration (Rule 0.2) ----------------------------------------------


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        logger.warning("attribution: bad int for %s, using fallback %s", name, default)
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        logger.warning("attribution: bad float for %s, using fallback %s", name, default)
        return default


def _env_flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# Logging is ON by default: it is cheap and it is the only way real ground truth
# ever accumulates.
ENABLED = _env_flag("NOUGEN_ATTRIBUTION", "1")
# The TIEBREAK is OFF by default and must be switched on deliberately. Turning
# it on before usage data exists would replace a bad prior with an empty one.
TIEBREAK_ENABLED = _env_flag("NOUGEN_ATTRIBUTION_TIEBREAK", "0")
# Recency half-life for observed credit (days).
HALFLIFE_DAYS = _env_float("NOUGEN_ATTRIBUTION_HALFLIFE_DAYS", 30.0)
# Scale mapping accumulated credit onto the utility-prior scale.
CREDIT_WEIGHT = _env_float("NOUGEN_ATTRIBUTION_CREDIT_WEIGHT", 1.0)
# Prior assigned to a shard with attribution records whose net credit is <= 0.
FLOOR_PRIOR = _env_float("NOUGEN_ATTRIBUTION_FLOOR_PRIOR", 0.1)
# Minimum observations before attribution is trusted enough to replace the prior.
MIN_OBSERVATIONS = _env_int("NOUGEN_ATTRIBUTION_MIN_OBSERVATIONS", 1)
# Read-side snapshot TTL (seconds) so ranking never does per-item I/O.
CACHE_TTL_S = _env_float("NOUGEN_ATTRIBUTION_CACHE_TTL_S", 60.0)
# Bounded write queue; overflow is dropped and counted, never blocked on.
QUEUE_MAX = _env_int("NOUGEN_ATTRIBUTION_QUEUE_MAX", 1000)
# Flush batch size for the background writer.
BATCH_MAX = _env_int("NOUGEN_ATTRIBUTION_BATCH_MAX", 64)
DB_TIMEOUT = _env_float("NOUGEN_ATTRIBUTION_DB_TIMEOUT", 10.0)
# Bounded wait for flush(); a telemetry flush must never hang a process exit.
FLUSH_TIMEOUT_S = _env_float("NOUGEN_ATTRIBUTION_FLUSH_TIMEOUT_S", 5.0)
_FLUSH_POLL_S = _env_float("NOUGEN_ATTRIBUTION_FLUSH_POLL_S", 0.005)

# Source labels for how a usage record was obtained.
SOURCE_EXPLICIT = "explicit_api"
SOURCE_MARK_UTILITY = "mark_utility"

_TABLE = "shard_attribution"

_queue: "queue.Queue[Optional[tuple]]" = queue.Queue(maxsize=QUEUE_MAX)
_writer_thread: Optional[threading.Thread] = None
_writer_lock = threading.Lock()
_dropped = 0
_cache: Dict[str, object] = {"at": 0.0, "db": None, "data": {}}
_cache_lock = threading.Lock()


def _db_path():
    """Attribution rides the history substrate, not the shard DBs.

    The shard grid holds MEMORY; this is TELEMETRY about memory. Keeping it in
    history.db means no shard table is altered and nothing here can corrupt a
    vault row.
    """
    from . import history  # pylint: disable=import-outside-toplevel
    return history.get_history_db_path()


def _connect(path):
    conn = sqlite3.connect(str(path), timeout=DB_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn=None) -> None:
    """Create the additive attribution table. Never drops or alters existing tables."""
    own = conn is None
    if own:
        path = _db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = _connect(path)
    try:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shard_id INTEGER NOT NULL,
                db_index TEXT NOT NULL,
                store TEXT,
                query TEXT,
                session_id TEXT,
                contribution REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT
            );
        """)
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_attr_shard ON {_TABLE}(shard_id, db_index);")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_attr_ts ON {_TABLE}(timestamp);")
        conn.commit()
    finally:
        if own:
            conn.close()


def _drain(rows: List[tuple]) -> None:
    try:
        conn = _connect(_db_path())
    except sqlite3.Error as exc:
        logger.warning("attribution: cannot open store (%s); %d rows dropped", exc, len(rows))
        return
    try:
        init_db(conn)
        conn.executemany(
            f"""INSERT INTO {_TABLE}
                (shard_id, db_index, store, query, session_id,
                 contribution, source, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
        conn.commit()
    except sqlite3.Error as exc:
        # Degrade like history.log_event: telemetry loss must never surface as a
        # memory failure, and stdout is reserved for the MCP JSON-RPC stream.
        logger.warning("attribution: write failed (%s); %d rows dropped", exc, len(rows))
    finally:
        conn.close()


def _writer_loop() -> None:
    """Drain forever. `task_done` is in a `finally` so a failing write can never
    leave the queue with unfinished tasks (that deadlocks any waiter)."""
    while True:
        q = _queue
        item = q.get()
        batch = [item]
        try:
            while len(batch) < BATCH_MAX:
                try:
                    batch.append(q.get_nowait())
                except queue.Empty:
                    break
            _drain(batch)
        except Exception:  # noqa: BLE001 - telemetry must never kill the thread
            logger.warning("attribution: writer batch failed", exc_info=True)
        finally:
            for _ in batch:
                try:
                    q.task_done()
                except ValueError:
                    break


def _ensure_writer() -> None:
    global _writer_thread  # pylint: disable=global-statement
    with _writer_lock:
        if _writer_thread is not None and _writer_thread.is_alive():
            return
        _writer_thread = threading.Thread(
            target=_writer_loop, name="nougen-attribution-writer", daemon=True)
        _writer_thread.start()


def flush(timeout: Optional[float] = None,
          _defaults: dict = {"timeout": FLUSH_TIMEOUT_S,  # pylint: disable=dangerous-default-value
                             "poll": _FLUSH_POLL_S}) -> bool:
    """Wait for queued records to persist. For tests and shutdown only.

    Deliberately NOT `Queue.join()`: join has no timeout, so a queue that was
    swapped out (tests), or a writer thread that never started, hangs the
    caller forever. This polls under a deadline and gives up honestly instead.
    Returns True when the queue drained, False on timeout / no writer.
    """
    import time  # pylint: disable=import-outside-toplevel
    # Bind the tunables locally: atexit fires during interpreter teardown, when
    # module globals may already be cleared. Reading FLUSH_TIMEOUT_S off the
    # module there raises NameError inside the atexit callback on every exit.
    limit = _defaults["timeout"] if timeout is None else timeout
    poll = _defaults["poll"]
    deadline = time.time() + limit
    while time.time() < deadline:
        if getattr(_queue, "unfinished_tasks", 0) == 0:
            return True
        if _writer_thread is None or not _writer_thread.is_alive():
            return False
        time.sleep(poll)
    return False


atexit.register(flush)


def _normalize_ref(ref) -> Optional[Tuple[int, str, Optional[str]]]:
    """Accept a recall result dict or a (shard_id, db_index) pair.

    `_db_index` may be namespaced as "<store>:<idx>" by federation, and that
    namespacing is preserved verbatim: a bare int would resolve against the
    PRIMARY grid and credit a different shard.
    """
    store = None
    if isinstance(ref, dict):
        shard_id = ref.get("id")
        db_index = ref.get("_db_index")
        store = ref.get("_store")
    elif isinstance(ref, (tuple, list)) and len(ref) >= 2:
        shard_id, db_index = ref[0], ref[1]
    else:
        return None
    if shard_id is None or db_index is None:
        return None
    try:
        shard_id = int(shard_id)
    except (TypeError, ValueError):
        return None
    return (shard_id, str(db_index), store)


def record_usage(used, query: Optional[str] = None, session_id: Optional[str] = None,
                 contribution: float = 1.0, source: str = SOURCE_EXPLICIT,
                 metadata: Optional[dict] = None) -> int:
    """Declare that these shards actually CONTRIBUTED to a downstream answer.

    This is the explicit API referred to in the module docstring: the caller
    knows what it cited; nothing here guesses. Returns the number of records
    enqueued (0 when disabled or nothing resolvable was passed).

    Non-blocking by construction -- rows go onto a bounded queue drained by a
    daemon thread, so recall latency is unaffected.
    """
    global _dropped  # pylint: disable=global-statement
    if not ENABLED:
        return 0
    if isinstance(used, dict) or not isinstance(used, Iterable):
        used = [used]
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta = json.dumps(metadata or {})
    enqueued = 0
    for ref in used:
        norm = _normalize_ref(ref)
        if norm is None:
            continue
        shard_id, db_index, store = norm
        row = (shard_id, db_index, store, query, session_id,
               float(contribution), source, ts, meta)
        try:
            _queue.put_nowait(row)
            enqueued += 1
        except queue.Full:
            _dropped += 1
            logger.debug("attribution: queue full, record dropped (total %d)", _dropped)
    if enqueued:
        _ensure_writer()
    return enqueued


def dropped_count() -> int:
    return _dropped


def _snapshot() -> Dict[Tuple[int, str], Tuple[float, int]]:
    """(shard_id, db_index) -> (recency-decayed net credit, observation count).

    One aggregate query behind a TTL, keyed on the active vault so a store swap
    (federation repoints core.GLOBAL_DIR) cannot serve another store's cache.
    """
    import time  # pylint: disable=import-outside-toplevel
    try:
        path = str(_db_path())
    except Exception:  # noqa: BLE001
        return {}
    now = time.time()
    with _cache_lock:
        if _cache["db"] == path and (now - float(_cache["at"])) < CACHE_TTL_S:
            return _cache["data"]  # type: ignore[return-value]
    data: Dict[Tuple[int, str], Tuple[float, int]] = {}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=DB_TIMEOUT)
    except sqlite3.Error:
        conn = None
    if conn is not None:
        try:
            rows = conn.execute(
                f"SELECT shard_id, db_index, contribution, timestamp FROM {_TABLE}").fetchall()
            now_dt = datetime.now(timezone.utc)
            for shard_id, db_index, contribution, ts in rows:
                decay = 1.0
                try:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    age = (now_dt - dt).total_seconds() / 86400.0
                    if HALFLIFE_DAYS > 0:
                        decay = max(0.0, 0.5 ** (age / HALFLIFE_DAYS))
                except Exception:  # noqa: BLE001
                    pass
                key = (int(shard_id), str(db_index))
                credit, count = data.get(key, (0.0, 0))
                data[key] = (credit + float(contribution) * decay, count + 1)
        except sqlite3.Error:
            data = {}  # table absent == no evidence, which is the honest answer
        finally:
            conn.close()
    with _cache_lock:
        _cache["at"], _cache["db"], _cache["data"] = now, path, data
    return data


def invalidate_cache() -> None:
    with _cache_lock:
        _cache["at"], _cache["db"], _cache["data"] = 0.0, None, {}


def credit_for(shard_id, db_index) -> Optional[Tuple[float, int]]:
    """Observed (credit, observations) for one shard, or None when unobserved."""
    if shard_id is None or db_index is None:
        return None
    try:
        key = (int(shard_id), str(db_index))
    except (TypeError, ValueError):
        return None
    return _snapshot().get(key)


def observed_prior(item: dict, utility: float) -> float:
    """Replace the utility prior with observed attribution WHEN evidence exists.

    Returns `utility` unchanged when the tiebreak is off, when no usage has ever
    been recorded for this shard, or when the observation count is below
    NOUGEN_ATTRIBUTION_MIN_OBSERVATIONS. No evidence means no change -- the
    absence of a signal is never dressed up as one.
    """
    if not TIEBREAK_ENABLED:
        return utility
    observed = credit_for(item.get("id"), item.get("_db_index"))
    if observed is None:
        return utility
    credit, count = observed
    if count < MIN_OBSERVATIONS:
        return utility
    item["_attribution_credit"] = credit
    item["_attribution_observations"] = count
    if credit <= 0:
        return FLOOR_PRIOR
    return credit * CREDIT_WEIGHT


def describe() -> Dict[str, object]:
    """Resolved configuration plus live counters, for diagnostics."""
    snap = _snapshot() if ENABLED else {}
    return {
        "logging_enabled": ENABLED,
        "tiebreak_enabled": TIEBREAK_ENABLED,
        "observed_shards": len(snap),
        "queue_dropped": _dropped,
        "halflife_days": HALFLIFE_DAYS,
        "credit_weight": CREDIT_WEIGHT,
        "min_observations": MIN_OBSERVATIONS,
        "cache_ttl_s": CACHE_TTL_S,
        "queue_max": QUEUE_MAX,
        "rl_half": "not implemented (AttriMem RL/policy learning is GPU-bound; 8GB VRAM)",
    }
