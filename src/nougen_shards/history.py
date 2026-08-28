"""
NouGenShards: History Substrate & Event Logging.
Tracks machine experience evolution across multiple horizons.
"""
import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

# Configuration
def get_history_db_path() -> Path:
    """Gets the path to the history database in the active vault."""
    from . import core
    vault = core.active_vault_dir()
    vault.mkdir(parents=True, exist_ok=True, mode=0o700)
    return vault / "history.db"


def get_history_connection():
    """Establishes a connection to the history substrate with WAL enabled."""
    db_path = get_history_db_path()
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_history_db():
    """Initializes the shard_events table and optimized indexes."""
    conn = get_history_connection()
    cursor = conn.cursor()

    # Module 3: Deep Grep Latent Structure (Tracking evolution)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shard_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shard_id INTEGER NOT NULL,
            db_index INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            old_score REAL,
            new_score REAL,
            timestamp TEXT NOT NULL,
            metadata JSON
        );
    """)

    # Module 10: Integrate Constraints (Performance Indexes)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON shard_events(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_shard ON shard_events(shard_id, db_index);")

    conn.commit()
    conn.close()


def _count_shard_rows() -> Optional[int]:
    """Actual shard rows across the cluster, or None if the grid can't be read.

    Kept here rather than imported from core to avoid a circular import: core
    already imports history to log capture events.
    """
    try:
        from .core import MAX_DB_COUNT, get_db_path  # pylint: disable=import-outside-toplevel
    except Exception:  # pylint: disable=broad-except
        return None
    total = 0
    seen_any = False
    for i in range(1, MAX_DB_COUNT + 1):
        path = get_db_path(i)
        if not path.exists():
            continue
        conn = None
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
            total += conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            seen_any = True
        except (sqlite3.Error, OSError):
            continue
        finally:
            if conn is not None:
                conn.close()
    return total if seen_any else None


import atexit
import queue
import threading

_LOG_QUEUE: "queue.Queue[tuple]" = queue.Queue(maxsize=10000)
_LOG_WORKER_THREAD: Optional[threading.Thread] = None
_LOG_WORKER_LOCK = threading.Lock()
_LOG_STOP_EVENT = threading.Event()


def _history_writer_loop():
    """Background worker thread that batches and commits telemetry events."""
    while not _LOG_STOP_EVENT.is_set():
        batch = []
        try:
            first = _LOG_QUEUE.get(timeout=0.2)
            batch.append(first)
            while len(batch) < 200:
                try:
                    batch.append(_LOG_QUEUE.get_nowait())
                except queue.Empty:
                    break
        except queue.Empty:
            continue

        if batch:
            by_db = {}
            for entry in batch:
                db_p = entry[0]
                by_db.setdefault(db_p, []).append(entry[1:])

            for db_path, entries in by_db.items():
                conn = None
                try:
                    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    conn = sqlite3.connect(str(db_path), timeout=10.0)
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA synchronous = NORMAL;")
                    conn.execute("PRAGMA busy_timeout = 2000;")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS shard_events (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            shard_id INTEGER NOT NULL,
                            db_index INTEGER NOT NULL,
                            event_type TEXT NOT NULL,
                            old_score REAL,
                            new_score REAL,
                            timestamp TEXT NOT NULL,
                            metadata JSON
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON shard_events(timestamp);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_shard ON shard_events(shard_id, db_index);")
                    conn.executemany("""
                        INSERT INTO shard_events (shard_id, db_index, event_type, old_score, new_score, timestamp, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, entries)
                    conn.commit()
                except sqlite3.Error as exc:
                    print(f"[Warning] Failed to flush background history events: {exc}", file=sys.stderr)
                finally:
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass


def _ensure_worker_started():
    global _LOG_WORKER_THREAD
    if _LOG_WORKER_THREAD is None or not _LOG_WORKER_THREAD.is_alive():
        with _LOG_WORKER_LOCK:
            if _LOG_WORKER_THREAD is None or not _LOG_WORKER_THREAD.is_alive():
                _LOG_STOP_EVENT.clear()
                _LOG_WORKER_THREAD = threading.Thread(target=_history_writer_loop, daemon=True, name="NouGenHistoryWriter")
                _LOG_WORKER_THREAD.start()


def _shutdown_history_writer():
    _LOG_STOP_EVENT.set()

atexit.register(_shutdown_history_writer)


def log_event(shard_id: int, db_index: int, event_type: str,
              old_score: Optional[float] = None, new_score: Optional[float] = None, metadata: Optional[dict] = None):
    """Writes a historical event to the substrate asynchronously."""
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta_json = json.dumps(metadata or {})
    db_path = get_history_db_path()
    item = (db_path, shard_id, db_index, event_type, old_score, new_score, timestamp, meta_json)

    _ensure_worker_started()
    try:
        _LOG_QUEUE.put_nowait(item)
    except queue.Full:
        # If queue is saturated, log warning to stderr and degrade gracefully
        print("[Warning] Shard history queue full, dropping event", file=sys.stderr)



class HistoryEngine:
    """Module 2: Activate Orchestration (Analytical Control Loop)."""

    @staticmethod
    def get_period_delta(period: str) -> timedelta:
        """Maps friendly period names to timedeltas."""
        mapping = {
            "24h": timedelta(hours=24),
            "week": timedelta(days=7),
            "month": timedelta(days=30),
            "quarter": timedelta(days=90),
            "year": timedelta(days=365)
        }
        return mapping.get(period, mapping["week"])

    @staticmethod
    def get_growth_rate(period: str = "week"):
        """Calculates memory growth in the specified window."""
        delta = HistoryEngine.get_period_delta(period)
        cutoff = (datetime.now(timezone.utc) - delta).isoformat().replace("+00:00", "Z")

        conn = get_history_connection()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM shard_events WHERE event_type = 'CREATED' AND timestamp > ?",
                (cutoff,)
            ).fetchone()[0]

            # total_shards must be a REAL row count, not a count of CREATED events.
            # The event log only sees writes that went through history.log_event, so
            # bulk-ingest and repair paths that write rows directly never register.
            # The event log undercounts by construction, and the result was being
            # surfaced to the user as "Total Memory Size" -- a label that promises
            # a row count. Prefer the real thing.
            total = _count_shard_rows()
            if total is None:  # grid unreadable -- fall back to the event proxy
                total = conn.execute(
                    "SELECT COUNT(*) FROM shard_events WHERE event_type = 'CREATED'"
                ).fetchone()[0]
            return {"period": period, "new_shards": count, "total_shards": total}
        except sqlite3.Error:
            return {"period": period, "new_shards": 0, "total_shards": 0}
        finally:
            conn.close()

    @staticmethod
    def get_utility_delta(period: str = "week"):
        """Measures the net change in usefulness across the fabric."""
        delta = HistoryEngine.get_period_delta(period)
        cutoff = (datetime.now(timezone.utc) - delta).isoformat().replace("+00:00", "Z")

        conn = get_history_connection()
        try:
            res = conn.execute("""
                SELECT SUM(new_score - old_score) FROM shard_events 
                WHERE event_type = 'UTILITY_CHANGE' AND timestamp > ?
            """, (cutoff,)).fetchone()[0]
            return res or 0.0
        except sqlite3.Error: return 0.0
        finally: conn.close()

    @staticmethod
    def get_utility_stats(period: str = "week"):
        """Alias for get_utility_delta (used by tests)."""
        return HistoryEngine.get_utility_delta(period)

    @staticmethod
    def get_top_shards(period: str = "week", limit: int = 5):
        """Identifies top shards by utility growth in the period."""
        delta = HistoryEngine.get_period_delta(period)
        cutoff = (datetime.now(timezone.utc) - delta).isoformat().replace("+00:00", "Z")
        
        conn = get_history_connection()
        try:
            # Query for net positive utility changes
            query = """
                SELECT shard_id, db_index, SUM(new_score - old_score) as growth
                FROM shard_events
                WHERE event_type = 'UTILITY_CHANGE' AND timestamp > ?
                GROUP BY shard_id, db_index
                ORDER BY growth DESC
                LIMIT ?
            """
            rows = conn.execute(query, (cutoff, limit)).fetchall()
            
            # Enrich with titles from core
            from . import core # pylint: disable=import-outside-toplevel
            enriched = []
            for r in rows:
                item = dict(r)
                shard = core.get_shard_by_id(item['shard_id'], item['db_index'])
                if shard:
                    item['title'] = shard['title']
                    item['utility_score'] = shard['utility_score']
                else:
                    item['title'] = "Unknown Shard"
                    item['utility_score'] = 0.0
                enriched.append(item)
            return enriched
        except sqlite3.Error: return []
        finally: conn.close()

    @staticmethod
    def export_stats_json(period: str = "week"):
        """Consolidates all stats into a single JSON packet."""
        return json.dumps({
            "period": period,
            "growth": HistoryEngine.get_growth_rate(period),
            "utility_delta": HistoryEngine.get_utility_delta(period),
            "top_shards": HistoryEngine.get_top_shards(period)
        }, indent=2)

    @staticmethod
    def get_timeline(period: str = "week"):

        """Generates a simple ASCII timeline of memory growth."""
        delta = HistoryEngine.get_period_delta(period)
        now = datetime.now(timezone.utc)
        steps = 10
        step_delta = delta / steps

        buckets = []
        conn = get_history_connection()
        try:
            for i in range(steps):
                start = (now - delta + (i * step_delta)).isoformat().replace("+00:00", "Z")
                end = (now - delta + ((i + 1) * step_delta)).isoformat().replace("+00:00", "Z")
                count = conn.execute(
                    "SELECT COUNT(*) FROM shard_events WHERE event_type = 'CREATED' AND timestamp >= ? AND timestamp < ?",
                    (start, end)
                ).fetchone()[0]
                buckets.append(count)
        except sqlite3.Error:
            buckets = [0] * steps
        finally:
            conn.close()

        m_val = max(buckets) if buckets and max(buckets) > 0 else 1
        normalized = [int((b / m_val) * 5) for b in buckets]

        chart = ""
        for h in range(5, 0, -1):
            line = "  "
            for val in normalized:
                line += "█ " if val >= h else "  "
            chart += line + "\n"

        return chart + f"  {period} growth timeline"
