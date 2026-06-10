"""
NouGenShards: History Substrate & Event Logging.
Tracks machine experience evolution across multiple horizons.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta

# Configuration
HISTORY_DIR = Path.home() / ".nougen" / "shards"
DB_PATH = HISTORY_DIR / "history.db"


def get_history_connection():
    """Establishes a connection to the history substrate with WAL enabled."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
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


def log_event(shard_id: int, db_index: int, event_type: str,
              old_score: float = None, new_score: float = None, metadata: dict = None):
    """Writes a historical event to the substrate."""
    # Lazy init to prevent side-effects on import
    if not DB_PATH.exists():
        init_history_db()

    timestamp = datetime.utcnow().isoformat() + "Z"
    meta_json = json.dumps(metadata or {})

    conn = get_history_connection()
    try:
        conn.execute("""
            INSERT INTO shard_events (shard_id, db_index, event_type, old_score, new_score, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (shard_id, db_index, event_type, old_score, new_score, timestamp, meta_json))
        conn.commit()
    except sqlite3.Error as exc:
        # Module 10: Graceful Degradation (Log failure but don't crash main memory)
        print(f"[Warning] Failed to log history event: {exc}")
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
        cutoff = (datetime.utcnow() - delta).isoformat() + "Z"

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
    def get_utility_delta(period: str = "week"):
        """Measures the net change in Bayesian confidence across the fabric."""
        delta = HistoryEngine.get_period_delta(period)
        cutoff = (datetime.utcnow() - delta).isoformat() + "Z"

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
        cutoff = (datetime.utcnow() - delta).isoformat() + "Z"
        
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
        now = datetime.utcnow()
        steps = 10
        step_delta = delta / steps

        buckets = []
        conn = get_history_connection()
        try:
            for i in range(steps):
                start = (now - delta + (i * step_delta)).isoformat() + "Z"
                end = (now - delta + ((i + 1) * step_delta)).isoformat() + "Z"
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
