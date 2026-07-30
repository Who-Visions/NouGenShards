"""SQLite source adapters for Brain Scan.

`.db` / `.sqlite` files are listed in SUPPORTED_EXTS, but `parse_universal`
had no reader for them: they fell through to the raw-text fallback, which
ingested the literal bytes ("SQLite format 3\\x00...") as a single shard.
This module replaces that with schema-aware extraction.

Handlers are matched on a *table/column fingerprint*, never on filename, so a
renamed or relocated database still resolves to the right reader. Each handler
streams `NormalizedRecord`s so a 100MB+ index never has to be held in memory.
"""
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Set

from .candidate import NormalizedRecord

# Content shorter than this carries no recoverable meaning (ids, enum labels,
# empty strings). Applied after strip() to every emitted record.
MIN_CONTENT_CHARS = 24

# Per-record content ceiling. Matches the markdown parser's 10k budget so one
# oversized blob cannot dominate a shard database.
MAX_CONTENT_CHARS = 10000


def _tables(conn: sqlite3.Connection) -> Dict[str, Set[str]]:
    """Maps table name -> column names, skipping FTS shadow tables.

    FTS5 shadow tables (`*_data`, `*_idx`, `*_docsize`, `*_config`) hold the
    serialized index, not content: reading them yields binary noise, and the
    content is already reachable through the parent table.
    """
    out: Dict[str, Set[str]] = {}
    shadow = ("_data", "_idx", "_docsize", "_config", "_content")
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for (name,) in rows:
        if name.endswith(shadow):
            continue
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')}
        out[name] = cols
    return out


def _has(tables: Dict[str, Set[str]], table: str, *required: str) -> bool:
    return table in tables and set(required).issubset(tables[table])


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _json_meta(raw: Any) -> Dict[str, Any]:
    """Best-effort parse of a JSON metadata column; never raises on bad data."""
    text = _clean(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return {"raw": text[:500]}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _row_iter(conn: sqlite3.Connection, sql: str, batch: int = 2000):
    """Streams a query in batches so a large table is never fully materialized."""
    cur = conn.execute(sql)
    while True:
        rows = cur.fetchmany(batch)
        if not rows:
            return
        for row in rows:
            yield row


# ---------------------------------------------------------------------------
# Blob text recovery (protobuf-encoded agent trajectories)
# ---------------------------------------------------------------------------

# Antigravity stores each step as a protobuf blob. Without the .proto schema we
# recover the human-readable fields by scanning for printable runs. The space
# floor is what separates prose from packed identifiers: UUIDs, base64 tokens
# and hashes are long printable runs with no spaces, and they made up nearly
# every match before this filter was added.
_PRINTABLE_RUN = re.compile(rb"[ -~\n\t]{60,}")
_MIN_SPACES = 8


def _recover_blob_text(blob: bytes) -> List[str]:
    found: List[str] = []
    seen: Set[str] = set()
    for match in _PRINTABLE_RUN.findall(blob):
        text = match.decode("ascii", errors="ignore").strip()
        if text.count(" ") < _MIN_SPACES:
            continue
        # Identical system prompts repeat across steps of one trajectory;
        # dedupe within the blob before the substrate's global hash pass.
        key = text[:200]
        if key in seen:
            continue
        seen.add(key)
        found.append(text)
    return found


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _extract_chunk_index(conn: sqlite3.Connection, path: Path,
                         tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """Machine-wide file index: chunks(source, title, body, content_hash).

    Written by the Who_Mac_Mini_indexer. `source` is the indexed file path and
    `body` the extracted text, so each row maps to exactly one shard.
    """
    sql = ("SELECT id, source, title, body, content_hash, indexed_at "
           "FROM chunks ORDER BY id")
    for row in _row_iter(conn, sql):
        rid, source, title, body, chash, indexed_at = row
        body = _clean(body).strip()
        if len(body) < MIN_CONTENT_CHARS:
            continue
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="file_index_chunk",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=None,
            role="system",
            timestamp=_clean(indexed_at),
            title=_clean(title) or Path(_clean(source)).name or f"chunk-{rid}",
            content=body[:MAX_CONTENT_CHARS],
            metadata={"indexed_source": _clean(source), "chunk_id": rid},
            parser="sqlite_chunk_index",
            confidence=0.85,
            source_hash=_clean(chash) or None,
            content_hash=_clean(chash) or None,
        )


def _extract_sol_vault(conn: sqlite3.Connection, path: Path,
                       tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """Sol-Ai memory vault: memories(+prompt/content/role) and thoughts."""
    sql = ("SELECT id, source_system, source_actor, source_kind, prompt, content, "
           "created_at, metadata_json, memory_category, title, project_name, "
           "tags_json, conversation_id, role, occurred_at "
           "FROM memories ORDER BY id")
    for row in _row_iter(conn, sql):
        (rid, sys_, actor, kind, prompt, content, created, meta_json,
         category, title, project, tags_json, conv_id, role, occurred) = row
        content = _clean(content).strip()
        if len(content) < MIN_CONTENT_CHARS:
            continue
        prompt_text = _clean(prompt).strip()
        # The prompt is the question the memory answers; keeping it inline
        # preserves the pair that makes the row searchable.
        body = f"PROMPT: {prompt_text}\n\n{content}" if prompt_text else content
        meta = _json_meta(meta_json)
        meta.update({
            "source_system": _clean(sys_), "source_actor": _clean(actor),
            "source_kind": _clean(kind), "memory_category": _clean(category),
            "project_name": _clean(project), "tags": _json_meta(tags_json) or _clean(tags_json),
        })
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="sol_memory",
            source_path=str(path.absolute()),
            project_path=_clean(project) or None,
            conversation_id=_clean(conv_id) or None,
            role=_clean(role) or "assistant",
            timestamp=_clean(occurred) or _clean(created),
            title=_clean(title) or f"{_clean(category) or 'memory'} #{rid}",
            content=body[:MAX_CONTENT_CHARS],
            metadata=meta,
            parser="sqlite_sol_vault",
            confidence=0.9,
        )

    if not _has(_tables(conn), "thoughts", "prompt", "thought"):
        return
    sql = ("SELECT id, prompt, thought, thinking_trace, source_system, "
           "source_actor, created_at FROM thoughts ORDER BY id")
    for row in _row_iter(conn, sql):
        rid, prompt, thought, trace, sys_, actor, created = row
        parts = [p for p in (
            f"PROMPT: {_clean(prompt).strip()}" if _clean(prompt).strip() else "",
            _clean(thought).strip(),
            f"TRACE: {_clean(trace).strip()}" if _clean(trace).strip() else "",
        ) if p]
        body = "\n\n".join(parts).strip()
        if len(body) < MIN_CONTENT_CHARS:
            continue
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="sol_thought",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=None,
            role="assistant",
            timestamp=_clean(created),
            title=(_clean(prompt).strip() or f"thought #{rid}")[:120],
            content=body[:MAX_CONTENT_CHARS],
            metadata={"source_system": _clean(sys_), "source_actor": _clean(actor)},
            parser="sqlite_sol_vault",
            confidence=0.85,
        )


def _extract_iris(conn: sqlite3.Connection, path: Path,
                  tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """Iris agent memory: conversational memories plus error/fix touchdowns."""
    sql = ("SELECT id, timestamp, role, content, session_id, metadata "
           "FROM memories ORDER BY rowid")
    for row in _row_iter(conn, sql):
        rid, ts, role, content, session, meta = row
        content = _clean(content).strip()
        if len(content) < MIN_CONTENT_CHARS:
            continue
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="iris_memory",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=_clean(session) or None,
            role=_clean(role) or "assistant",
            timestamp=_clean(ts),
            title=f"[{_clean(role) or 'msg'}] {content.splitlines()[0][:100]}",
            content=content[:MAX_CONTENT_CHARS],
            metadata=_json_meta(meta),
            parser="sqlite_iris",
            confidence=0.85,
            source_hash=_clean(rid) or None,
        )

    if not _has(_tables(conn), "touchdowns", "error", "fix"):
        return
    # error->fix pairs are the highest-utility rows in the whole corpus: they
    # are exactly the "what broke and what fixed it" shape the substrate ranks.
    sql = "SELECT id, error, fix, success, timestamp FROM touchdowns ORDER BY id"
    for rid, error, fix, success, ts in _row_iter(conn, sql):
        error, fix = _clean(error).strip(), _clean(fix).strip()
        if not error and not fix:
            continue
        body = f"ERROR: {error}\n\nFIX: {fix}"
        if len(body.strip()) < MIN_CONTENT_CHARS:
            continue
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="iris_touchdown",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=None,
            role="system",
            timestamp=_clean(ts),
            title=f"[FIX] {error.splitlines()[0][:100] if error else f'touchdown #{rid}'}",
            content=body[:MAX_CONTENT_CHARS],
            metadata={"success": bool(success)},
            parser="sqlite_iris",
            confidence=0.95,
        )


def _extract_notion(conn: sqlite3.Connection, path: Path,
                    tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """Notion mirror: pages(+content) with their blocks folded in.

    Blocks are emitted as part of their parent page rather than individually —
    a single Notion block ("- [ ] ship it") is not independently searchable,
    and 12k fragment shards would crowd out real context.
    """
    tables = _tables(conn)
    blocks_by_page: Dict[str, List[str]] = {}
    if _has(tables, "blocks", "page_id", "content"):
        for page_id, btype, content in _row_iter(
                conn, "SELECT page_id, type, content FROM blocks"):
            text = _clean(content).strip()
            if not text:
                continue
            prefix = f"[{_clean(btype)}] " if _clean(btype) else ""
            blocks_by_page.setdefault(_clean(page_id), []).append(prefix + text)

    seen_pages: Set[str] = set()
    sql = "SELECT id, parent_id, title, url, content, meta FROM pages"
    for pid, parent, title, url, content, meta in _row_iter(conn, sql):
        pid = _clean(pid)
        seen_pages.add(pid)
        parts = [p for p in (_clean(content).strip(),
                             "\n".join(blocks_by_page.get(pid, []))) if p]
        body = "\n\n".join(parts).strip()
        if len(body) < MIN_CONTENT_CHARS:
            continue
        page_meta = _json_meta(meta)
        page_meta.update({"url": _clean(url), "parent_id": _clean(parent),
                          "block_count": len(blocks_by_page.get(pid, []))})
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="notion_page",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=None,
            role="system",
            timestamp="",
            title=_clean(title) or f"page {pid[:8]}",
            content=body[:MAX_CONTENT_CHARS],
            metadata=page_meta,
            parser="sqlite_notion",
            confidence=0.8,
        )

    # Blocks whose parent page is missing would otherwise be dropped silently.
    orphans = {k: v for k, v in blocks_by_page.items() if k not in seen_pages}
    for page_id, texts in orphans.items():
        body = "\n".join(texts).strip()
        if len(body) < MIN_CONTENT_CHARS:
            continue
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="notion_orphan_blocks",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=None,
            role="system",
            timestamp="",
            title=f"orphan blocks {page_id[:8]}",
            content=body[:MAX_CONTENT_CHARS],
            metadata={"page_id": page_id, "block_count": len(texts)},
            parser="sqlite_notion",
            confidence=0.6,
        )


def _extract_trajectory(conn: sqlite3.Connection, path: Path,
                        tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """Antigravity agent trajectories: protobuf step blobs.

    Text is recovered heuristically (see `_recover_blob_text`); confidence is
    set lower than the schema-backed handlers to reflect that.
    """
    tables = _tables(conn)
    traj_id = ""
    if _has(tables, "trajectory_meta", "trajectory_id"):
        row = conn.execute(
            "SELECT trajectory_id FROM trajectory_meta LIMIT 1").fetchone()
        if row:
            traj_id = _clean(row[0])
    if not traj_id:
        traj_id = path.stem

    sql = ("SELECT idx, step_type, step_payload FROM steps "
           "WHERE step_payload IS NOT NULL ORDER BY idx")
    for idx, step_type, payload in _row_iter(conn, sql, batch=200):
        if not isinstance(payload, (bytes, bytearray)):
            continue
        passages = _recover_blob_text(bytes(payload))
        if not passages:
            continue
        body = "\n\n".join(passages).strip()
        if len(body) < MIN_CONTENT_CHARS:
            continue
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="agent_trajectory_step",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=traj_id or None,
            role="assistant",
            timestamp="",
            title=f"[traj {traj_id[:8]}] step {idx}",
            content=body[:MAX_CONTENT_CHARS],
            metadata={"step_index": idx, "step_type": step_type,
                      "passages": len(passages), "recovery": "printable_run"},
            parser="sqlite_trajectory",
            confidence=0.5,
        )


def _extract_codex_logs(conn: sqlite3.Connection, path: Path,
                        tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """Codex tracing logs. Only rows carrying a body are worth a shard."""
    sql = ("SELECT id, ts, level, target, feedback_log_body, module_path "
           "FROM logs WHERE feedback_log_body IS NOT NULL "
           "AND TRIM(feedback_log_body) != '' ORDER BY id")
    for rid, ts, level, target, body, module in _row_iter(conn, sql):
        body = _clean(body).strip()
        if len(body) < MIN_CONTENT_CHARS:
            continue
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="codex_log",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=None,
            role="system",
            timestamp=_clean(ts),
            title=f"[{_clean(level)}] {_clean(target)}"[:120] or f"log #{rid}",
            content=body[:MAX_CONTENT_CHARS],
            metadata={"module_path": _clean(module), "level": _clean(level)},
            parser="sqlite_codex_logs",
            confidence=0.4,
        )


def _extract_chroma(conn: sqlite3.Connection, path: Path,
                    tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """ChromaDB vector store.

    Chroma keeps the document text in `embedding_metadata` as a key/value EAV
    table: one row per (embedding id, metadata key), with the body under the
    reserved key `chroma:document`. Reading the table row-wise — what the
    generic fallback does — turns 61k documents into 428k meaningless
    fragments, so the rows are pivoted back into one record per embedding.
    """
    doc_key = "chroma:document"
    sql = ("SELECT id, key, string_value, int_value, float_value "
           "FROM embedding_metadata ORDER BY id")

    def _emit(emb_id: Any, fields: Dict[str, Any]) -> Optional[NormalizedRecord]:
        body = _clean(fields.pop(doc_key, "")).strip()
        if len(body) < MIN_CONTENT_CHARS:
            return None
        source_file = _clean(fields.get("source_file", ""))
        # wing/room are the mempalace's own filing coordinates; they make a
        # far better title than the opaque embedding id.
        wing = _clean(fields.get("wing", ""))
        room = _clean(fields.get("room", ""))
        label = " / ".join([p for p in (wing, room) if p])
        title = (Path(source_file).name if source_file else "") or label or f"doc {emb_id}"
        return NormalizedRecord(
            source_tool=tool,
            source_kind="chroma_document",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=None,
            role="system",
            timestamp=_clean(fields.get("filed_at", "")),
            title=(f"{label}: {title}" if label else title)[:160],
            content=body[:MAX_CONTENT_CHARS],
            metadata={k: v for k, v in fields.items() if v not in (None, "")},
            parser="sqlite_chroma",
            confidence=0.85,
        )

    current_id: Any = None
    fields: Dict[str, Any] = {}
    for emb_id, key, sval, ival, fval in _row_iter(conn, sql):
        if emb_id != current_id:
            if current_id is not None:
                rec = _emit(current_id, fields)
                if rec:
                    yield rec
            current_id, fields = emb_id, {}
        value = sval if sval is not None else (ival if ival is not None else fval)
        fields[_clean(key)] = value
    if current_id is not None:
        rec = _emit(current_id, fields)
        if rec:
            yield rec


def _extract_legacy_shards(conn: sqlite3.Connection, path: Path,
                           tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """A prototype-era NouGenShards vault: shards(finding, logic, outcome_history).

    Predates the current substrate schema (title/content/event_type), so it
    cannot be attached directly and has to be re-captured row by row. The
    prototype's own utility_score is carried through as metadata rather than
    applied, since scores are not comparable across substrates.
    """
    sql = ("SELECT id, timestamp, category, tags, source, finding, logic, "
           "utility_score, access_count, outcome_history FROM shards ORDER BY id")
    for row in _row_iter(conn, sql):
        (rid, ts, category, tags, source, finding, logic,
         utility, access, outcome) = row
        finding, logic = _clean(finding).strip(), _clean(logic).strip()
        parts = [p for p in (finding, f"LOGIC: {logic}" if logic else "") if p]
        body = "\n\n".join(parts).strip()
        if len(body) < MIN_CONTENT_CHARS:
            continue
        yield NormalizedRecord(
            source_tool=tool,
            source_kind="legacy_shard",
            source_path=str(path.absolute()),
            project_path=None,
            conversation_id=None,
            role="system",
            timestamp=_clean(ts),
            title=f"[{_clean(category) or 'shard'}] {(finding or logic).splitlines()[0][:100]}",
            content=body[:MAX_CONTENT_CHARS],
            metadata={"legacy_id": rid, "category": _clean(category),
                      "tags": _clean(tags), "source": _clean(source),
                      "prototype_utility": utility, "prototype_access_count": access,
                      "outcome_history": _clean(outcome)[:500]},
            parser="sqlite_legacy_shards",
            confidence=0.9,
        )


def _extract_generic(conn: sqlite3.Connection, path: Path,
                     tool: str, is_project: bool) -> Iterator[NormalizedRecord]:
    """Fallback for an unrecognized schema.

    Emits one record per row of any table holding a substantial text column,
    rendered as `column: value` lines. Deliberately conservative: BLOB columns
    are described by size rather than decoded, since an unknown binary column
    is as likely to be an embedding vector as anything readable.
    """
    tables = _tables(conn)
    for name, cols in tables.items():
        if not cols:
            continue
        col_list = ", ".join(f'"{c}"' for c in sorted(cols))
        try:
            rows = _row_iter(conn, f'SELECT {col_list} FROM "{name}"')
            ordered = sorted(cols)
            for row in rows:
                lines = []
                for col, val in zip(ordered, row):
                    if isinstance(val, (bytes, bytearray)):
                        lines.append(f"{col}: <{len(val)} bytes>")
                    elif val is not None and str(val).strip():
                        lines.append(f"{col}: {str(val).strip()}")
                body = "\n".join(lines).strip()
                if len(body) < MIN_CONTENT_CHARS:
                    continue
                yield NormalizedRecord(
                    source_tool=tool,
                    source_kind=f"sqlite_row:{name}",
                    source_path=str(path.absolute()),
                    project_path=None,
                    conversation_id=None,
                    role="system",
                    timestamp="",
                    title=f"[{path.stem}] {name}",
                    content=body[:MAX_CONTENT_CHARS],
                    metadata={"table": name},
                    parser="sqlite_generic",
                    confidence=0.3,
                )
        except sqlite3.Error:
            # A virtual/corrupt table must not abort the remaining tables.
            continue


# Ordered most specific first; the first matching detector wins.
HANDLERS: List[Dict[str, Any]] = [
    {
        "name": "chunk_index",
        "detect": lambda t: _has(t, "chunks", "source", "title", "body"),
        "extract": _extract_chunk_index,
    },
    {
        "name": "sol_vault",
        "detect": lambda t: _has(t, "memories", "source_system", "content",
                                 "memory_category"),
        "extract": _extract_sol_vault,
    },
    {
        "name": "iris_memory",
        "detect": lambda t: _has(t, "memories", "content", "role", "session_id")
                            or _has(t, "touchdowns", "error", "fix"),
        "extract": _extract_iris,
    },
    {
        "name": "notion_intelligence",
        "detect": lambda t: _has(t, "pages", "title", "content")
                            and _has(t, "blocks", "page_id"),
        "extract": _extract_notion,
    },
    {
        "name": "chroma_vectors",
        "detect": lambda t: _has(t, "embedding_metadata", "key", "string_value")
                            and "embeddings" in t,
        "extract": _extract_chroma,
    },
    {
        # Detected on finding/logic, which the current substrate's own `shards`
        # table does not have — so an active vault can never match this.
        "name": "legacy_shards",
        "detect": lambda t: _has(t, "shards", "finding", "logic"),
        "extract": _extract_legacy_shards,
    },
    {
        "name": "agent_trajectory",
        "detect": lambda t: _has(t, "steps", "step_payload"),
        "extract": _extract_trajectory,
    },
    {
        "name": "codex_logs",
        "detect": lambda t: _has(t, "logs", "feedback_log_body", "target"),
        "extract": _extract_codex_logs,
    },
]


def is_sqlite(path: Path) -> bool:
    """True if the file carries the SQLite magic header.

    Checked by content, not extension: `.db` is used by plenty of non-SQLite
    formats, and opening one would raise DatabaseError mid-scan.
    """
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def detect_handler(path: Path) -> Optional[str]:
    """Returns the handler name for a database, or None if it cannot be read."""
    if not is_sqlite(path):
        return None
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return None
    try:
        tables = _tables(conn)
        if not tables:
            return None
        for handler in HANDLERS:
            if handler["detect"](tables):
                return str(handler["name"])
        return "generic"
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _connect(path: Path) -> sqlite3.Connection:
    """Opens a database strictly read-only.

    `immutable=1` additionally lets us read a database that another process
    holds a lock on (the live agent stores are frequently open elsewhere), at
    the cost of ignoring any un-checkpointed WAL content.
    """
    uri = f"file:{path.absolute()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    return conn


# Tables each handler draws rows from, used for a COUNT(*)-based dry-run
# estimate. Upper bound: rows below MIN_CONTENT_CHARS are still counted here,
# since filtering them would mean reading every row during a scan.
_COUNT_TABLES: Dict[str, List[str]] = {
    "chunk_index": ["chunks"],
    "sol_vault": ["memories", "thoughts"],
    "iris_memory": ["memories", "touchdowns"],
    "notion_intelligence": ["pages"],
    # One record per embedding, not per metadata row.
    "chroma_vectors": ["embeddings"],
    "legacy_shards": ["shards"],
    "agent_trajectory": ["steps"],
    "codex_logs": ["logs"],
}


def estimate_records(path: Path) -> int:
    """Row-count estimate for a database, without extracting content."""
    handler = detect_handler(path)
    if handler is None:
        return 0
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return 0
    try:
        tables = _tables(conn)
        targets = _COUNT_TABLES.get(handler, list(tables.keys()))
        total = 0
        for table in targets:
            if table not in tables:
                continue
            try:
                row = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
                total += int(row[0]) if row else 0
            except sqlite3.Error:
                continue
        return total
    finally:
        conn.close()


def iter_records(path: Path, tool: str, is_project: bool = False,
                 allow_generic: bool = True) -> Iterator[NormalizedRecord]:
    """Streams NormalizedRecords out of a SQLite database.

    Never raises on a malformed or locked database: a source that cannot be
    read yields nothing, so one bad file cannot abort a whole import.
    """
    if not is_sqlite(path):
        return
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return
    try:
        tables = _tables(conn)
        if not tables:
            return
        extractor: Optional[Callable] = None
        for handler in HANDLERS:
            if handler["detect"](tables):
                extractor = handler["extract"]
                break
        if extractor is None:
            if not allow_generic:
                return
            extractor = _extract_generic
        yield from extractor(conn, path, tool, is_project)
    except sqlite3.Error:
        return
    finally:
        conn.close()
