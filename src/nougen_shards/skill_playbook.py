"""Outcome playbook for skills: counters and delta field notes.

Skills were applied but never scored. ``apply_skills`` returned the governing
skills, the work happened, and nothing recorded whether a skill helped, so the
registry could not tell a skill that keeps working from one that keeps
misleading its reader.

This is the pattern from Agentic Context Engineering (ACE, arXiv 2510.04618),
rebuilt for the skill registry:

* Counter layer. Every skill, and every field note under it, carries
  ``helpful`` and ``harmful`` counts that a reported outcome increments.
* Delta updates. A lesson learned while using a skill is ADDED as one short
  field note with its own id. SKILL.md is never rewritten from here, which is
  what keeps accumulated detail from collapsing into a summary.
* Deduplication. A note whose normalised text already exists under that skill
  increments the existing note instead of adding a twin.

The data is derived, so it lives in a SQLite sidecar next to the vault, not in
the skill files and not as shards. Nothing here can make a skill disappear:
the ranking bonus is strictly smaller than one matched term, so outcomes only
reorder skills that tie on relevance.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from . import core

NOTE_MAX_CHARS = 240
MIN_SAMPLES = 3          # below this a skill's rate is noise, so no ranking effect
_BONUS_SPAN = 0.5        # bonus stays inside (-0.5, +0.5): less than one matched term

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skill_counts (
    skill   TEXT PRIMARY KEY,
    helpful INTEGER NOT NULL DEFAULT 0,
    harmful INTEGER NOT NULL DEFAULT 0,
    updated REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_notes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    skill   TEXT    NOT NULL,
    norm    TEXT    NOT NULL,
    content TEXT    NOT NULL,
    helpful INTEGER NOT NULL DEFAULT 0,
    harmful INTEGER NOT NULL DEFAULT 0,
    created REAL    NOT NULL,
    UNIQUE (skill, norm)
);
"""


def db_path() -> Path:
    """Sidecar location; ``NOUGEN_SKILL_PLAYBOOK_DB`` overrides the vault default.

    The default follows the request's active vault, so a tenant's outcomes and
    field notes stay in that tenant's vault and never reach another tenant.
    """
    override = os.environ.get("NOUGEN_SKILL_PLAYBOOK_DB", "").strip()
    return Path(override) if override else Path(core.active_vault_dir()) / "skill_playbook.db"


_READY: set[str] = set()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    try:
        # Schema and WAL are set once per file per process, not on every read:
        # executescript commits and takes a write lock, which readers should not need.
        if str(path) not in _READY or not _has_schema(conn):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            _READY.add(str(path))
        yield conn
        conn.commit()
    finally:
        conn.close()


def _has_schema(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'skill_counts'").fetchone() is not None


def _key(skill: str) -> str:
    return " ".join(str(skill or "").split()).lower()


def clean_note(note: Optional[str]) -> str:
    """One line, bounded length, no control characters.

    A field note is written by one agent and read by the next, so it is kept
    to a single short line: it cannot carry a multi-line block, a heading or a
    fence into a later prompt.
    """
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(note or ""))
    text = " ".join(text.replace("`", "'").split())
    return text[:NOTE_MAX_CHARS].rstrip()


def _norm(note: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", note.lower()).strip()


def note_id(row_id: int) -> str:
    return f"sk-{int(row_id):05d}"


def _parse_note_id(value: str) -> Optional[int]:
    m = re.fullmatch(r"\s*\[?sk-0*(\d+)\]?\s*", str(value or ""), flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def mark(skill: str, worked: bool, note: Optional[str] = None,
         note_ids: Optional[list[str]] = None) -> dict:
    """Record one outcome for ``skill``.

    ``note`` adds a field note (or bumps the identical existing one).
    ``note_ids`` are notes that were shown and that this outcome confirms or
    contradicts; each gets the same helpful/harmful increment.
    """
    key = _key(skill)
    if not key:
        raise ValueError("A skill name is required.")
    column = "helpful" if worked else "harmful"
    now = time.time()
    added: Optional[str] = None
    bumped: list[str] = []
    with _connect() as conn:
        conn.execute(
            "INSERT INTO skill_counts (skill, helpful, harmful, updated) VALUES (?, 0, 0, ?) "
            "ON CONFLICT(skill) DO NOTHING", (key, now))
        conn.execute(f"UPDATE skill_counts SET {column} = {column} + 1, updated = ? WHERE skill = ?",
                     (now, key))
        for raw in note_ids or []:
            row_id = _parse_note_id(raw)
            if row_id is None:
                continue
            cur = conn.execute(
                f"UPDATE skill_notes SET {column} = {column} + 1 WHERE id = ? AND skill = ?",
                (row_id, key))
            if cur.rowcount:
                bumped.append(note_id(row_id))
        text = clean_note(note)
        norm = _norm(text)
        if norm:
            row = conn.execute("SELECT id FROM skill_notes WHERE skill = ? AND norm = ?",
                               (key, norm)).fetchone()
            if row:
                # The same lesson reported again is evidence for it, not a second note.
                conn.execute("UPDATE skill_notes SET helpful = helpful + 1 WHERE id = ?", (row[0],))
                bumped.append(note_id(row[0]))
            else:
                cur = conn.execute(
                    "INSERT INTO skill_notes (skill, norm, content, created) VALUES (?, ?, ?, ?)",
                    (key, norm, text, now))
                added = note_id(cur.lastrowid)
        helpful, harmful = conn.execute(
            "SELECT helpful, harmful FROM skill_counts WHERE skill = ?", (key,)).fetchone()
    return {"skill": key, "helpful": helpful, "harmful": harmful,
            "note_added": added, "notes_bumped": bumped}


def counts(skill: str) -> tuple[int, int]:
    """(helpful, harmful) for one skill; (0, 0) when it has never been marked."""
    with _connect() as conn:
        row = conn.execute("SELECT helpful, harmful FROM skill_counts WHERE skill = ?",
                           (_key(skill),)).fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def bonus_from_counts(helpful: int, harmful: int) -> float:
    """Ranking nudge in (-0.5, +0.5); 0.0 until there are enough samples.

    Laplace-smoothed success rate, centred on zero. The span is under one
    matched term on purpose: outcomes break ties, relevance still decides.
    """
    total = helpful + harmful
    if total < MIN_SAMPLES:
        return 0.0
    rate = (helpful + 1) / (total + 2)
    return (rate - 0.5) * 2 * _BONUS_SPAN


def bonuses() -> dict[str, float]:
    """Ranking nudge per skill key, for every skill that has outcomes. One query."""
    if not db_path().exists():
        return {}
    with _connect() as conn:
        rows = conn.execute("SELECT skill, helpful, harmful FROM skill_counts").fetchall()
    return {skill: bonus_from_counts(int(h), int(m)) for skill, h, m in rows}


def field_notes(skill: str, limit: int = 5) -> list[dict]:
    """Notes worth showing next time, best first.

    A note that has been contradicted at least as often as confirmed is held
    back (ACE's 'problematic' bucket); it stays in the table for audit.
    """
    if not db_path().exists():
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, helpful, harmful FROM skill_notes "
            "WHERE skill = ? AND NOT (harmful > 0 AND harmful >= helpful) "
            "ORDER BY (helpful - harmful) DESC, created DESC LIMIT ?",
            (_key(skill), max(0, int(limit)))).fetchall()
    return [{"id": note_id(r[0]), "content": r[1], "helpful": int(r[2]), "harmful": int(r[3])}
            for r in rows]


def format_field_notes(skill: str, limit: int = 5) -> str:
    """Field notes as ``[sk-00012] helpful=2 harmful=0 :: text`` lines, or ''."""
    notes = field_notes(skill, limit)
    return "\n".join(
        f"[{n['id']}] helpful={n['helpful']} harmful={n['harmful']} :: {n['content']}" for n in notes)


def stats() -> dict:
    """Roster health: which skills keep working, which keep misleading."""
    if not db_path().exists():
        return {"skills": 0, "outcomes": 0, "notes": 0, "strong": [], "problematic": []}
    with _connect() as conn:
        rows = conn.execute("SELECT skill, helpful, harmful FROM skill_counts ORDER BY skill").fetchall()
        notes = conn.execute("SELECT COUNT(*) FROM skill_notes").fetchone()[0]
    strong = [s for s, h, m in rows if h + m >= MIN_SAMPLES and bonus_from_counts(h, m) > 0.2]
    problematic = [s for s, h, m in rows if m > 0 and m >= h]
    return {"skills": len(rows), "outcomes": sum(h + m for _, h, m in rows), "notes": int(notes),
            "strong": strong, "problematic": problematic}
