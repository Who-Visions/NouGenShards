"""Destiny: prospective memory for the NouGen grid.

Shards remember what happened. A destiny records what state the grid, a
project, or a story is trying to reach: a terminal goal, the trigger that
activates it, the events it requires, the outcomes it forbids, how much
variance is acceptable, and how fulfilment is verified. Destinies live in
their own store and never touch a shard row, so a goal can never masquerade
as a fact (ChatGPT legs 20260902T011226Z / 011422Z, shard 17773).

A destiny is a goal graph, not a field: `destiny_links` ties one destiny to
any number of shards, relay legs, or agents with a role each. Transitions are
append-only in `destiny_events`; a failed destiny is preserved as Evolve's
raw material, never deleted.

Everything environment-shaped resolves from env with a logged fallback:
  NOUGEN_DESTINY_DB        sqlite path (default: <GLOBAL_DIR>/destinies.db)
  NOUGEN_DESTINY_BRANCHES  comma list of allowed branch labels
  NOUGEN_DESTINY_DEFAULT_BRANCH  branch used when none is given (default U0)
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

STATUSES = ("dormant", "active", "fulfilled", "failed", "superseded")
#: Legal lifecycle edges. Anything else is refused with an error dict.
TRANSITIONS = {
    "dormant": ("active", "superseded", "failed"),
    "active": ("fulfilled", "failed", "superseded"),
    "fulfilled": (),
    "failed": (),
    "superseded": (),
}
UNFINISHED = ("dormant", "active")
LINK_KINDS = ("shard", "relay", "agent", "destiny")
LINK_ROLES = ("evidence", "required", "forbidden", "outcome", "actor", "context")
_FALLBACK_BRANCHES = "U0,UX,ARCH,DRAFT,SIM,REL"


def allowed_branches() -> List[str]:
    """Canon branch labels. U0 prime, UX shadow origin, ARCH temporal architect,
    DRAFT deprecated, SIM hypothetical, REL relationship memory."""
    raw = os.environ.get("NOUGEN_DESTINY_BRANCHES", "").strip()
    if not raw:
        raw = _FALLBACK_BRANCHES
    return [b.strip() for b in raw.split(",") if b.strip()]


def default_branch() -> str:
    raw = os.environ.get("NOUGEN_DESTINY_DEFAULT_BRANCH", "").strip()
    return raw or allowed_branches()[0]


def db_path() -> Path:
    raw = os.environ.get("NOUGEN_DESTINY_DB", "").strip()
    if raw:
        return Path(raw)
    from . import core
    return Path(core.GLOBAL_DIR) / "destinies.db"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextlib.contextmanager
def _connect():
    """Open, ensure schema, commit on success, ALWAYS close. sqlite3's own
    context manager commits but never closes, which leaks a handle per call
    and, on Windows, pins the WAL file so temp dirs cannot be removed."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=float(os.environ.get("NOUGEN_DESTINY_DB_TIMEOUT_S", "5")))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS destinies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            goal TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'dormant',
            branch TEXT NOT NULL,
            trigger TEXT,
            required_events TEXT,      -- JSON list
            forbidden_outcomes TEXT,   -- JSON list
            acceptable_variance TEXT,
            verification TEXT,
            confidence REAL,
            deadline TEXT,
            supersedes INTEGER,
            superseded_by INTEGER,
            provenance TEXT,           -- JSON: who/where/why it was set
            created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS destiny_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destiny_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            ref TEXT NOT NULL,
            role TEXT NOT NULL,
            note TEXT,
            created_utc TEXT NOT NULL,
            UNIQUE(destiny_id, kind, ref, role)
        );
        CREATE TABLE IF NOT EXISTS destiny_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destiny_id INTEGER NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            actor TEXT,
            evidence TEXT,
            created_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_destinies_status ON destinies (status);
        CREATE INDEX IF NOT EXISTS idx_destinies_branch ON destinies (branch);
        CREATE INDEX IF NOT EXISTS idx_destiny_links_destiny ON destiny_links (destiny_id);
        CREATE INDEX IF NOT EXISTS idx_destiny_events_destiny ON destiny_events (destiny_id);
        """
    )


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except ValueError:
            pass
        return [v.strip() for v in value.split(";") if v.strip()]
    if isinstance(value, Iterable):
        return [str(x) for x in value]
    return [str(value)]


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for key in ("required_events", "forbidden_outcomes"):
        d[key] = _as_list(d.get(key))
    prov = d.get("provenance")
    if isinstance(prov, str) and prov:
        try:
            d["provenance"] = json.loads(prov)
        except ValueError:
            pass
    return d


def create_destiny(title: str, goal: str, *, branch: Optional[str] = None,
                   trigger: Optional[str] = None,
                   required_events: Any = None, forbidden_outcomes: Any = None,
                   acceptable_variance: Optional[str] = None,
                   verification: Optional[str] = None,
                   confidence: Optional[float] = None, deadline: Optional[str] = None,
                   supersedes: Optional[int] = None, provenance: Any = None,
                   status: str = "dormant", actor: Optional[str] = None) -> Dict[str, Any]:
    """Record a target state. Returns the stored destiny or {"error": ...}."""
    title = (title or "").strip()
    goal = (goal or "").strip()
    if len(title) < 3 or len(goal) < 3:
        return {"error": "title and goal are required (3+ chars each)"}
    if status not in ("dormant", "active"):
        return {"error": f"a new destiny starts dormant or active, not {status!r}"}
    branch = (branch or "").strip() or default_branch()
    if branch not in allowed_branches():
        return {"error": f"branch {branch!r} not in {allowed_branches()}; an unplaced branch is not a universe"}
    if provenance is not None and not isinstance(provenance, str):
        provenance = json.dumps(provenance)
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO destinies (title, goal, status, branch, trigger, required_events,
               forbidden_outcomes, acceptable_variance, verification, confidence, deadline,
               supersedes, provenance, created_utc, updated_utc)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, goal, status, branch, trigger, json.dumps(_as_list(required_events)),
             json.dumps(_as_list(forbidden_outcomes)), acceptable_variance, verification,
             confidence, deadline, supersedes, provenance, now, now))
        did = cur.lastrowid
        conn.execute("INSERT INTO destiny_events (destiny_id, from_status, to_status, actor, evidence, created_utc) VALUES (?,?,?,?,?,?)",
                     (did, None, status, actor, "created", now))
        if supersedes:
            _transition(conn, supersedes, "superseded", actor, f"superseded by destiny {did}", now)
            conn.execute("UPDATE destinies SET superseded_by=?, updated_utc=? WHERE id=?", (did, now, supersedes))
        row = conn.execute("SELECT * FROM destinies WHERE id=?", (did,)).fetchone()
    return _row_to_dict(row)


def _transition(conn: sqlite3.Connection, destiny_id: int, to_status: str,
                actor: Optional[str], evidence: Optional[str], now: str) -> Dict[str, Any]:
    row = conn.execute("SELECT id, status FROM destinies WHERE id=?", (destiny_id,)).fetchone()
    if row is None:
        return {"error": f"destiny {destiny_id} not found"}
    frm = row["status"]
    if to_status not in STATUSES:
        return {"error": f"unknown status {to_status!r}; statuses: {STATUSES}"}
    if to_status not in TRANSITIONS.get(frm, ()):
        return {"error": f"illegal transition {frm} -> {to_status}; a {frm} destiny is preserved, not rewritten"}
    conn.execute("UPDATE destinies SET status=?, updated_utc=? WHERE id=?", (to_status, now, destiny_id))
    conn.execute("INSERT INTO destiny_events (destiny_id, from_status, to_status, actor, evidence, created_utc) VALUES (?,?,?,?,?,?)",
                 (destiny_id, frm, to_status, actor, evidence, now))
    return {"id": destiny_id, "from": frm, "to": to_status}


def update_status(destiny_id: int, to_status: str, *, actor: Optional[str] = None,
                  evidence: Optional[str] = None) -> Dict[str, Any]:
    """Move a destiny along its lifecycle. Every move is an event; nothing is erased."""
    now = _now()
    with _connect() as conn:
        out = _transition(conn, int(destiny_id), to_status, actor, evidence, now)
        if "error" in out:
            return out
        row = conn.execute("SELECT * FROM destinies WHERE id=?", (destiny_id,)).fetchone()
    return _row_to_dict(row)


def link(destiny_id: int, kind: str, ref: str, role: str = "evidence",
         note: Optional[str] = None) -> Dict[str, Any]:
    """Attach a shard (ref "db:id" or "id"), relay leg id, agent name, or another
    destiny to a destiny. The referenced object is never modified."""
    if kind not in LINK_KINDS:
        return {"error": f"kind {kind!r} not in {LINK_KINDS}"}
    if role not in LINK_ROLES:
        return {"error": f"role {role!r} not in {LINK_ROLES}"}
    ref = str(ref).strip()
    if not ref:
        return {"error": "ref is required"}
    now = _now()
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM destinies WHERE id=?", (destiny_id,)).fetchone() is None:
            return {"error": f"destiny {destiny_id} not found"}
        conn.execute("INSERT OR IGNORE INTO destiny_links (destiny_id, kind, ref, role, note, created_utc) VALUES (?,?,?,?,?,?)",
                     (destiny_id, kind, ref, role, note, now))
        links = conn.execute("SELECT kind, ref, role, note FROM destiny_links WHERE destiny_id=? ORDER BY id", (destiny_id,)).fetchall()
    return {"id": destiny_id, "links": [dict(lnk) for lnk in links]}


def get_destiny(destiny_id: int) -> Dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM destinies WHERE id=?", (destiny_id,)).fetchone()
        if row is None:
            return {"error": f"destiny {destiny_id} not found"}
        d = _row_to_dict(row)
        d["links"] = [dict(lnk) for lnk in conn.execute(
            "SELECT kind, ref, role, note, created_utc FROM destiny_links WHERE destiny_id=? ORDER BY id", (destiny_id,))]
        d["events"] = [dict(e) for e in conn.execute(
            "SELECT from_status, to_status, actor, evidence, created_utc FROM destiny_events WHERE destiny_id=? ORDER BY id", (destiny_id,))]
    return d


def unfinished_destinies(*, status: Optional[str] = None, trigger: Optional[str] = None,
                         branch: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """The agent primitive: what is the grid still trying to make true?

    Default = dormant + active. `trigger` is a substring match. `branch` is an
    exact label. Oldest first, so the longest-held destinies surface first.
    """
    clauses, params = [], []
    if status:
        if status not in STATUSES:
            return {"error": f"unknown status {status!r}; statuses: {STATUSES}"}
        clauses.append("status = ?")
        params.append(status)
    else:
        clauses.append("status IN (%s)" % ",".join("?" * len(UNFINISHED)))
        params.extend(UNFINISHED)
    if trigger:
        clauses.append("LOWER(COALESCE(trigger,'')) LIKE ?")
        params.append(f"%{trigger.lower()}%")
    if branch:
        clauses.append("branch = ?")
        params.append(branch)
    limit = max(1, min(int(limit or 20), 200))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM destinies WHERE {' AND '.join(clauses)} ORDER BY created_utc ASC, id ASC LIMIT ?",
            (*params, limit)).fetchall()
        total = conn.execute(f"SELECT COUNT(*) FROM destinies WHERE {' AND '.join(clauses)}", params).fetchone()[0]
    return {"count": len(rows), "total": total, "destinies": [_row_to_dict(r) for r in rows],
            "filter": {"status": status or list(UNFINISHED), "trigger": trigger, "branch": branch}}


def search_destinies(query: str, *, limit: int = 20, include_finished: bool = True) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    if len(q) < 2:
        return {"error": "query too short"}
    like = f"%{q}%"
    where = "(LOWER(title) LIKE ? OR LOWER(goal) LIKE ? OR LOWER(COALESCE(trigger,'')) LIKE ? OR LOWER(COALESCE(verification,'')) LIKE ?)"
    params: List[Any] = [like, like, like, like]
    if not include_finished:
        where += " AND status IN (%s)" % ",".join("?" * len(UNFINISHED))
        params.extend(UNFINISHED)
    limit = max(1, min(int(limit or 20), 200))
    with _connect() as conn:
        rows = conn.execute(f"SELECT * FROM destinies WHERE {where} ORDER BY updated_utc DESC LIMIT ?", (*params, limit)).fetchall()
    return {"count": len(rows), "destinies": [_row_to_dict(r) for r in rows]}


def evolve_report(*, since_utc: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """Evolve's raw material: every terminal transition (fulfilled / failed /
    superseded) with its evidence, newest first. Read-only by design: the
    dream-lane contract is gate-don't-write, and Evolve inherits it. What the
    fleet changes because of this report is a decision, not an automation."""
    clauses = ["to_status IN ('fulfilled','failed','superseded')"]
    params: List[Any] = []
    if since_utc:
        clauses.append("e.created_utc >= ?")
        params.append(since_utc)
    limit = max(1, min(int(limit or 50), 500))
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT e.destiny_id, d.title, d.branch, e.from_status, e.to_status, e.actor, e.evidence, e.created_utc
                FROM destiny_events e JOIN destinies d ON d.id = e.destiny_id
                WHERE {' AND '.join(clauses)} ORDER BY e.created_utc DESC, e.id DESC LIMIT ?""",
            (*params, limit)).fetchall()
        counts = {s: conn.execute("SELECT COUNT(*) FROM destinies WHERE status=?", (s,)).fetchone()[0] for s in STATUSES}
    out = [dict(r) for r in rows]
    return {"status_counts": counts, "terminal_events": out,
            "failed": [r for r in out if r["to_status"] == "failed"],
            "note": "read-only: Evolve proposes, the GM decides"}
