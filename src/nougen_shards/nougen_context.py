"""NouGenContext core database and sandbox management."""
from pathlib import Path
import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional

NOUGEN_CONTEXT_DIR = Path.home() / ".nougen" / "context"
NOUGEN_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DB_PATH = str(NOUGEN_CONTEXT_DIR / "session.db")

def get_context_connection():
    """Establishes an SQLite connection for the session context with WAL enabled."""
    conn = sqlite3.connect(SESSION_DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_context_db(clean_slate: bool = True):
    """Initializes the ephemeral session database schema."""
    if clean_slate and Path(SESSION_DB_PATH).exists():
        # Clean-slate rule: wipe session.db unless continuing
        try:
            # Close any active connections first if possible, or just delete
            Path(SESSION_DB_PATH).unlink(missing_ok=True)
            Path(f"{SESSION_DB_PATH}-wal").unlink(missing_ok=True)
            Path(f"{SESSION_DB_PATH}-shm").unlink(missing_ok=True)
        except OSError:
            pass

    conn = get_context_connection()
    cursor = conn.cursor()

    # ctx_events: every file edit, git op, error, and decision
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ctx_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT
        );
    """)

    # ctx_events_fts: FTS5 for fast recall
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS ctx_events_fts USING fts5(
            content,
            content='ctx_events',
            content_rowid='id'
        );
    """)

    # Triggers for ctx_events synchronization
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS ctx_events_ai AFTER INSERT ON ctx_events BEGIN
            INSERT INTO ctx_events_fts(rowid, content) VALUES (new.id, new.content);
        END;
    """)

    # ctx_sandbox: large raw outputs keyed by handle
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ctx_sandbox (
            handle TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            data TEXT NOT NULL,
            summary TEXT
        );
    """)

    # ctx_session: current working set (open files, last task, etc)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ctx_session (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    conn.commit()
    conn.close()

def log_event(event_type: str, content: str, metadata: Optional[dict] = None):
    """Logs an event into the session context."""
    timestamp = datetime.now(timezone.utc).isoformat() + "Z"
    metadata_str = json.dumps(metadata or {})
    conn = get_context_connection()
    conn.execute(
        "INSERT INTO ctx_events (timestamp, type, content, metadata) VALUES (?, ?, ?, ?)",
        (timestamp, event_type, content, metadata_str)
    )
    conn.commit()
    conn.close()

def search_context(query: str, limit: int = 5):
    """Searches session context using BM25."""
    conn = get_context_connection()
    cursor = conn.execute("""
        SELECT e.id, e.timestamp, e.type, e.content, e.metadata
        FROM ctx_events e
        JOIN ctx_events_fts f ON e.id = f.rowid
        WHERE ctx_events_fts MATCH ?
        ORDER BY bm25(ctx_events_fts) ASC
        LIMIT ?
    """, (query, limit))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results

def get_event(event_id: int):
    """Retrieves a specific event from the context by ID."""
    conn = get_context_connection()
    try:
        row = conn.execute("SELECT id, type, content, timestamp, metadata FROM ctx_events WHERE id = ?", (event_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def store_sandbox(handle: str, data: str, summary: str = ""):
    """Stores large tool output in the sandbox."""
    timestamp = datetime.now(timezone.utc).isoformat() + "Z"
    conn = get_context_connection()
    conn.execute(
        "INSERT OR REPLACE INTO ctx_sandbox (handle, timestamp, data, summary) VALUES (?, ?, ?, ?)",
        (handle, timestamp, data, summary)
    )
    conn.commit()
    conn.close()

def fetch_sandbox(handle: str):
    """Retrieves data from the sandbox by handle."""
    conn = get_context_connection()
    row = conn.execute("SELECT data FROM ctx_sandbox WHERE handle = ?", (handle,)).fetchone()
    conn.close()
    return row["data"] if row else None

def search_events(query: str, limit: int = 5) -> list:
    conn = get_context_connection()
    try:
        rows = conn.execute("SELECT id, type, content as description, timestamp, metadata FROM ctx_events LIMIT ?", (limit,)).fetchall()
        return [{"id": r["id"], "event_type": r["type"], "description": r["description"], "timestamp": r["timestamp"], "metadata": r["metadata"]} for r in rows]
    finally:
        conn.close()
