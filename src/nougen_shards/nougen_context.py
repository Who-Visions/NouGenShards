"""NouGenContext core database and sandbox management."""
from pathlib import Path
import sqlite3
import json
import ast
import ipaddress
import os
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse
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


_ALLOWED_FETCH_SCHEMES = ("http", "https")


def _max_fetch_bytes() -> int:
    """Response size cap. Env NOUGEN_CONTEXT_MAX_FETCH_BYTES overrides; 5 MB fallback."""
    try:
        return max(1, int(os.environ.get("NOUGEN_CONTEXT_MAX_FETCH_BYTES", "")))
    except ValueError:
        return 5_000_000


def _validate_fetch_url(url: str) -> Optional[str]:
    """Return an error string if `url` must not be fetched, else None.

    http(s) only (urllib would otherwise happily read file:// and ftp://), and hosts that resolve to
    loopback/private/link-local/reserved space are refused so an MCP caller cannot use this tool to
    read local files or reach internal services (the shard gateway, cloud metadata).
    NOUGEN_CONTEXT_ALLOW_PRIVATE_HOSTS=1 opts out for trusted local use.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_FETCH_SCHEMES or not parsed.hostname:
        return f"blocked: only http(s) URLs with a host are allowed (got scheme {scheme!r})"
    if os.environ.get("NOUGEN_CONTEXT_ALLOW_PRIVATE_HOSTS") == "1":
        return None
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except OSError as exc:
        return f"blocked: cannot resolve host ({exc})"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return f"blocked: {parsed.hostname} resolves to a non-public address"
    return None


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect hop so a public URL cannot bounce the fetch to an internal one."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        err = _validate_fetch_url(newurl)
        if err:
            raise urllib.error.URLError(err)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_and_index_web(url: str, label: Optional[str] = None, timeout: int = 15) -> dict:
    """Natively fetches, extracts, indexes and sandboxes a web page without polluting context."""
    blocked = _validate_fetch_url(url)
    if blocked:
        return {"error": blocked, "url": url}
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NouGenContext/2.0 (Valerion Engine)"}
    )
    try:
        with urllib.request.build_opener(_CheckedRedirect).open(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            cap = _max_fetch_bytes()
            raw_bytes = resp.read(cap + 1)
            if len(raw_bytes) > cap:
                return {"error": f"blocked: response exceeds {cap} bytes", "url": url}
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


def query_ollama(
    prompt: str,
    system: Optional[str] = None,
    context_handle: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 35
) -> dict:
    """Natively query Ollama (local first on GPU, cloud fallback) to accelerate context synthesis."""
    import os
    from . import ollama_host

    endpoint = ollama_host.resolve_ollama_url()
    target_models = [model] if model else ["gemma4:e2b-qat", "Yukiai:e2b", "gemma2:2b", "mrs-b:latest"]

    full_prompt = prompt
    if context_handle:
        data = fetch_sandbox(context_handle)
        if data:
            full_prompt = f"Context from sandbox ({context_handle}):\n{data[:10000]}\n\nTask/Question:\n{prompt}"

    for candidate in target_models:
        payload = {
            "model": candidate,
            "prompt": full_prompt,
            "stream": False,
            "options": {"num_ctx": 32768, "temperature": 0.2}
        }
        if system:
            payload["system"] = system

        req = urllib.request.Request(
            f"{endpoint.rstrip('/')}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res = json.loads(response.read().decode("utf-8"))
                reply = res.get("response", "").strip()
                if "<channel|>" in reply:
                    reply = reply.split("<channel|>")[-1].strip()
                elif "<|channel|>" in reply:
                    reply = reply.split("<|channel|>")[-1].strip()

                log_event(
                    "OLLAMA_ACCELERATION",
                    f"Ollama ({candidate}) assisted on: {prompt[:100]}",
                    metadata={"model": candidate, "tokens": res.get("eval_count", 0), "handle": context_handle}
                )
                return {
                    "status": "success",
                    "model": candidate,
                    "response": reply,
                    "tokens_eval": res.get("eval_count", 0),
                    "endpoint": endpoint
                }
        except Exception:
            continue

    # Cloud fallback if env configured
    cloud_url = os.environ.get("NOUGEN_OLLAMA_CLOUD_URL") or os.environ.get("OLLAMA_CLOUD_URL")
    if cloud_url:
        try:
            req = urllib.request.Request(
                f"{cloud_url.rstrip('/')}/api/generate",
                data=json.dumps({
                    "model": model or "gemma4:31b",
                    "prompt": full_prompt,
                    "stream": False
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res = json.loads(response.read().decode("utf-8"))
                return {
                    "status": "success",
                    "model": "cloud:" + (model or "gemma4:31b"),
                    "response": res.get("response", "").strip(),
                    "endpoint": cloud_url
                }
        except Exception:
            pass

    return {
        "status": "unavailable",
        "error": "Ollama local and cloud endpoints did not respond.",
        "attempted_models": target_models
    }


def synthesize_sandbox(handle: str, instruction: str = "Summarize the core findings and key action items.") -> dict:
    """Uses Ollama to intelligently synthesize raw sandbox data and stores summary back to sandbox."""
    res = query_ollama(instruction, context_handle=handle)
    if res.get("status") == "success":
        summary = res["response"]
        data = fetch_sandbox(handle) or ""
        store_sandbox(handle, data, summary=summary)
        return {
            "status": "synthesized",
            "handle": handle,
            "model": res["model"],
            "summary": summary
        }
    return {
        "status": "fallback",
        "handle": handle,
        "error": res.get("error", "Ollama synthesis unavailable")
    }
