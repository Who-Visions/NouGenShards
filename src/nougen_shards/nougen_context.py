"""NouGenContext core database and sandbox management."""
from pathlib import Path
import sqlite3
import json
import ast
import re
import urllib.request
from html.parser import HTMLParser
from datetime import datetime, timezone
from typing import Optional

NOUGEN_CONTEXT_DIR = Path.home() / ".nougen" / "context"
SESSION_DB_PATH = str(NOUGEN_CONTEXT_DIR / "session.db")

def _utc_now_iso() -> str:
    """UTC timestamp as '...Z'. Note: isoformat() on a tz-aware UTC datetime
    already yields '...+00:00'; appending 'Z' produced the invalid '...+00:00Z'
    that broke downstream fromisoformat() parsing."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _ensure_schema(conn):
    """Ensures required tables exist idempotently without wiping data."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ctx_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT
        );
    """)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS ctx_events_fts USING fts5(
            content,
            content='ctx_events',
            content_rowid='id'
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ctx_sandbox (
            handle TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            data TEXT NOT NULL,
            summary TEXT
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ctx_session (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ctx_checkpoints (
            label TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            events_count INTEGER NOT NULL,
            data TEXT NOT NULL
        );
    """)
    conn.commit()


def get_context_connection():
    """Establishes an SQLite connection for the session context with WAL enabled."""
    Path(SESSION_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SESSION_DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn

def init_context_db(clean_slate: bool = False):
    """Initializes the ephemeral session database schema.

    clean_slate defaults to False: wiping session.db is destructive and must be
    an explicit opt-in, so an implicit init never destroys live session state.
    """
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
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS ctx_events_ad AFTER DELETE ON ctx_events BEGIN
            INSERT INTO ctx_events_fts(ctx_events_fts, rowid, content) VALUES ('delete', old.id, old.content);
        END;
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS ctx_events_au AFTER UPDATE ON ctx_events BEGIN
            INSERT INTO ctx_events_fts(ctx_events_fts, rowid, content) VALUES ('delete', old.id, old.content);
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

    # ctx_checkpoints: full working set snapshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ctx_checkpoints (
            label TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            events_count INTEGER NOT NULL,
            data TEXT NOT NULL
        );
    """)

    conn.commit()
    conn.close()

def log_event(event_type: str, content: str, metadata: Optional[dict] = None):
    """Logs an event into the session context."""
    timestamp = _utc_now_iso()
    metadata_str = json.dumps(metadata or {})
    conn = get_context_connection()
    try:
        conn.execute(
            "INSERT INTO ctx_events (timestamp, type, content, metadata) VALUES (?, ?, ?, ?)",
            (timestamp, event_type, content, metadata_str)
        )
        conn.commit()
    finally:
        conn.close()

def search_context(query: str, limit: int = 5):
    """Searches session context using BM25.

    Raw user input can contain FTS5 operators/quotes that raise OperationalError;
    fall back to a LIKE scan instead of hard-failing the search. The fallback uses
    the SAME projection (id/timestamp/type/content/metadata) as the FTS path so
    callers see a stable schema either way.
    """
    conn = get_context_connection()
    try:
        cursor = conn.execute("""
            SELECT e.id, e.timestamp, e.type, e.content, e.metadata
            FROM ctx_events e
            JOIN ctx_events_fts f ON e.id = f.rowid
            WHERE ctx_events_fts MATCH ?
            ORDER BY bm25(ctx_events_fts) ASC
            LIMIT ?
        """, (query, limit))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        pattern = f"%{query}%"
        cursor = conn.execute("""
            SELECT id, timestamp, type, content, metadata
            FROM ctx_events
            WHERE content LIKE ? OR type LIKE ? OR metadata LIKE ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        """, (pattern, pattern, pattern, limit))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

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
    timestamp = _utc_now_iso()
    conn = get_context_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO ctx_sandbox (handle, timestamp, data, summary) VALUES (?, ?, ?, ?)",
            (handle, timestamp, data, summary)
        )
        conn.commit()
    finally:
        conn.close()

def fetch_sandbox(handle: str):
    """Retrieves data from the sandbox by handle."""
    conn = get_context_connection()
    try:
        row = conn.execute("SELECT data FROM ctx_sandbox WHERE handle = ?", (handle,)).fetchone()
        return row["data"] if row else None
    finally:
        conn.close()

def search_events(query: str, limit: int = 5) -> list:
    """Searches context events by content, event type, or metadata."""
    conn = get_context_connection()
    try:
        pattern = f"%{query}%"
        rows = conn.execute("""
            SELECT id, type, content as description, timestamp, metadata
            FROM ctx_events
            WHERE content LIKE ? OR type LIKE ? OR metadata LIKE ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        """, (pattern, pattern, pattern, limit)).fetchall()
        return [
            {
                "id": r["id"],
                "event_type": r["type"],
                "description": r["description"],
                "timestamp": r["timestamp"],
                "metadata": r["metadata"],
            }
            for r in rows
        ]
    finally:
        conn.close()


class _HTMLContentExtractor(HTMLParser):
    """Zero-dependency HTML to structured markdown/text converter."""
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip_tags = {"script", "style", "noscript", "svg"}
        self._tag_stack = []
        self.text_parts = []
        self.headings = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        self._tag_stack.append(tag_lower)
        if tag_lower == "title":
            self._in_title = True
        elif tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.text_parts.append(f"\n\n{'#' * int(tag_lower[1])} ")
        elif tag_lower in ("p", "div", "section", "article"):
            self.text_parts.append("\n\n")
        elif tag_lower == "li":
            self.text_parts.append("\n* ")
        elif tag_lower == "br":
            self.text_parts.append("\n")
        elif tag_lower == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href and not href.startswith("javascript:") and not href.startswith("#"):
                self.links.append(href)

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = False
        if self._tag_stack and self._tag_stack[-1] == tag_lower:
            self._tag_stack.pop()

    def handle_data(self, data):
        if any(t in self._skip_tags for t in self._tag_stack):
            return
        clean_text = data.strip()
        if not clean_text:
            return
        if self._in_title:
            self.title = (self.title + " " + clean_text).strip()
        else:
            if self._tag_stack and self._tag_stack[-1] in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.headings.append(f"{self._tag_stack[-1].upper()}: {clean_text}")
            self.text_parts.append(clean_text + " ")

    def get_markdown(self) -> str:
        raw = "".join(self.text_parts)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def fetch_and_index_web(url: str, label: Optional[str] = None, timeout: int = 15) -> dict:
    """Natively fetches, extracts, indexes and sandboxes a web page without polluting context."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NouGenContext/2.0 (Valerion Engine)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            raw_bytes = resp.read()
            html_text = raw_bytes.decode(charset, errors="replace")
    except Exception as exc:
        return {"error": f"Failed to fetch {url}: {exc}", "url": url}

    parser = _HTMLContentExtractor()
    parser.feed(html_text)
    title = parser.title.strip() or label or url
    markdown_content = parser.get_markdown()

    summary_lines = [line.strip() for line in markdown_content.split("\n") if line.strip() and not line.startswith("#")]
    summary = " ".join(summary_lines[:5])[:600]

    handle = f"web:{url}"
    store_sandbox(handle, markdown_content, summary=summary)

    metadata = {
        "url": url,
        "label": label,
        "title": title,
        "headings_count": len(parser.headings),
        "links_count": len(parser.links),
        "content_length": len(markdown_content)
    }
    log_event(
        "WEB_INDEX",
        f"Web indexed: {title} ({url})\nSummary: {summary}",
        metadata=metadata
    )

    return {
        "url": url,
        "title": title,
        "handle": handle,
        "summary": summary,
        "headings": parser.headings[:15],
        "key_links": list(dict.fromkeys(parser.links))[:12],
        "total_length_bytes": len(markdown_content),
        "status": "indexed_in_nougen_context"
    }


def analyze_file(file_path: str, query: Optional[str] = None, max_lines_preview: int = 20) -> dict:
    """Analyzes a file in the sandbox, extracting AST or pattern insights without full context read."""
    path = Path(file_path).resolve()
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    if not path.is_file():
        return {"error": f"Not a file: {file_path}"}

    size = path.stat().st_size
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"error": f"Could not read file: {exc}"}

    lines = text.splitlines()
    ext = path.suffix.lower()

    analysis = {
        "file_path": str(path),
        "name": path.name,
        "extension": ext,
        "total_lines": len(lines),
        "size_bytes": size,
    }

    if ext == ".py":
        try:
            tree = ast.parse(text, filename=str(path))
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
            analysis["ast"] = {
                "classes": classes[:20],
                "functions": functions[:30],
                "imports": list(dict.fromkeys(imports))[:20],
                "syntax_valid": True
            }
        except SyntaxError as e:
            analysis["ast"] = {"syntax_valid": False, "syntax_error": f"Line {e.lineno}: {e.msg}"}
    elif ext == ".json":
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                analysis["json_schema"] = {"type": "object", "keys": list(data.keys())[:30], "total_keys": len(data)}
            elif isinstance(data, list):
                sample_type = type(data[0]).__name__ if data else "empty"
                analysis["json_schema"] = {"type": "array", "total_items": len(data), "sample_item_type": sample_type}
        except json.JSONDecodeError as exc:
            analysis["json_schema"] = {"valid": False, "error": str(exc)}

    if query:
        matched = []
        for idx, line in enumerate(lines, 1):
            if query.lower() in line.lower():
                matched.append(f"L{idx}: {line.strip()[:150]}")
                if len(matched) >= max_lines_preview:
                    break
        analysis["query_matches"] = matched

    handle = f"file:{path}"
    store_sandbox(handle, text, summary=f"{path.name}: {len(lines)} lines, {size} bytes")

    log_event(
        "FILE_ANALYSIS",
        f"Analyzed {path.name} ({len(lines)} lines, {size} bytes)" + (f" for '{query}'" if query else ""),
        metadata=analysis
    )

    return analysis


def checkpoint_session(label: str) -> dict:
    """Takes a snapshot of current session events and state into a named checkpoint."""
    timestamp = _utc_now_iso()
    conn = get_context_connection()
    try:
        events = [dict(r) for r in conn.execute("SELECT id, timestamp, type, content, metadata FROM ctx_events ORDER BY id ASC").fetchall()]
        session_state = [dict(r) for r in conn.execute("SELECT key, value FROM ctx_session").fetchall()]
        payload = json.dumps({"events": events, "session": session_state})
        conn.execute(
            "INSERT OR REPLACE INTO ctx_checkpoints (label, timestamp, events_count, data) VALUES (?, ?, ?, ?)",
            (label, timestamp, len(events), payload)
        )
        conn.commit()
        return {"status": "checkpoint_saved", "label": label, "events_count": len(events), "timestamp": timestamp}
    finally:
        conn.close()


def restore_session(label: str) -> dict:
    """Restores session state from a named checkpoint."""
    conn = get_context_connection()
    try:
        row = conn.execute("SELECT data, timestamp, events_count FROM ctx_checkpoints WHERE label = ?", (label,)).fetchone()
        if not row:
            return {"error": f"Checkpoint '{label}' not found"}
        data = json.loads(row["data"])
        events = data.get("events", [])
        session_state = data.get("session", [])

        conn.execute("DELETE FROM ctx_events")
        conn.execute("DELETE FROM ctx_session")
        for ev in events:
            conn.execute(
                "INSERT INTO ctx_events (id, timestamp, type, content, metadata) VALUES (?, ?, ?, ?, ?)",
                (ev["id"], ev["timestamp"], ev["type"], ev["content"], ev["metadata"])
            )
        for s in session_state:
            conn.execute("INSERT INTO ctx_session (key, value) VALUES (?, ?)", (s["key"], s["value"]))
        conn.commit()
        return {"status": "checkpoint_restored", "label": label, "events_restored": len(events)}
    finally:
        conn.close()


def list_checkpoints() -> list:
    """Lists all saved session checkpoints."""
    conn = get_context_connection()
    try:
        rows = conn.execute("SELECT label, timestamp, events_count FROM ctx_checkpoints ORDER BY timestamp DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
