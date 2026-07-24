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
    """Gets the path to the history database dynamically, matching core.GLOBAL_DIR."""
    from . import core
    core.GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    return core.GLOBAL_DIR / "history.db"


# The history substrate's schema, declared once. Both the readiness probe and
# the creation path read this mapping, so "what must exist" has exactly one
# source of truth and there is no second init path to drift out of sync.
# Module 3: Deep Grep Latent Structure (tracking evolution).
# Module 10: Integrate Constraints (performance indexes).
HISTORY_SCHEMA = {
    "shard_events": (
        """
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_history_timestamp ON shard_events(timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_history_shard ON shard_events(shard_id, db_index);",
    ),
}
REQUIRED_TABLES = tuple(HISTORY_SCHEMA)


def _ensure_history_schema(conn) -> None:
    """Idempotently guarantee every required table exists on ``conn``.

    Gate on SCHEMA, never on file existence. ``history.db`` is materialized by
    the first *connection* to it — a HistoryEngine read, or the attribution
    writer that shares the same file — so ``path.exists()`` becomes true long
    before ``shard_events`` does. Existence-gating the init therefore silently
    and permanently disabled event logging in any environment where a read
    preceded the first write. This runs on every connection instead, so read and
    write entry points alike leave the substrate usable.
    """
    try:
        placeholders = ",".join("?" for _ in REQUIRED_TABLES)
        present = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                f"AND name IN ({placeholders})",
                REQUIRED_TABLES,
            )
        }
        missing = [name for name in REQUIRED_TABLES if name not in present]
        if not missing:
            return
        for name in missing:
            for statement in HISTORY_SCHEMA[name]:
                conn.execute(statement)
        conn.commit()
    except sqlite3.Error as exc:
        # Module 10: Graceful Degradation. A substrate we cannot provision must
        # not crash main memory; the caller's own error handling reports the
        # downstream failure. Write to stderr: a stray stdout line corrupts the
        # MCP stdio JSON-RPC stream.
        print(f"[Warning] Failed to ensure history schema: {exc}", file=sys.stderr)


def get_history_connection():
    """Establishes a connection to the history substrate with WAL enabled.

    This is the single authoritative entry point: every read and every write in
    this module goes through it, and it guarantees the schema before handing the
    connection back.
    """
    db_path = get_history_db_path()
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    _ensure_history_schema(conn)
    return conn


def init_history_db():
    """Materializes the history substrate (tables + optimized indexes).

    Kept as the public/eager entry point, but it owns no DDL of its own: it
    delegates to the same choke point every other caller uses so there is
    exactly one initialization path.
    """
    conn = get_history_connection()
    conn.close()


def log_event(shard_id: int, db_index: int, event_type: str,
              old_score: Optional[float] = None, new_score: Optional[float] = None, metadata: Optional[dict] = None):
    """Writes a historical event to the substrate."""
    # Init is lazy (no side-effects on import) and lives in
    # get_history_connection below, which gates on schema rather than on file
    # existence — an existence gate here dropped every write that followed a
    # read, because the read had already created an empty history.db.
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta_json = json.dumps(metadata or {})

    conn = get_history_connection()
    try:
        conn.execute("""
            INSERT INTO shard_events (shard_id, db_index, event_type, old_score, new_score, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (shard_id, db_index, event_type, old_score, new_score, timestamp, meta_json))
        conn.commit()
    except sqlite3.Error as exc:
        # Module 10: Graceful Degradation (Log failure but don't crash main memory).
        # Write to stderr: a stray stdout line corrupts the MCP stdio JSON-RPC stream.
        print(f"[Warning] Failed to log history event: {exc}", file=sys.stderr)
    finally:
        conn.close()


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

            total = conn.execute("SELECT COUNT(*) FROM shard_events WHERE event_type = 'CREATED'").fetchone()[0]
            return {"period": period, "new_shards": count, "total_shards": total}
        except sqlite3.Error:
            return {"period": period, "new_shards": 0, "total_shards": 0}
        finally:
            conn.close()

    @staticmethod
    def get_utility_delta(period: str = "week") -> float:
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
