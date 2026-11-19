"""Destiny reconciler: turn stated GM intents into Destinies, once.

A stated goal should become a recorded Destiny without anyone writing it by
hand. ``plan`` is pure: it compares intents against the destinies already in
the store and says what to create, what is a duplicate, and what is invalid.
``apply`` writes only the planned creates, so running it twice is safe: the
second run finds every intent already present and creates nothing.

Dedupe key is the normalized title. A later intent with the same title as an
existing Destiny (any status) is a duplicate, never a new row, so a finished
Destiny is never re-opened by a restated goal.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List

from . import destiny

try:  # POSIX
    import fcntl as _fcntl
except ImportError:  # Windows nodes
    _fcntl = None
    import msvcrt as _msvcrt

ACTOR = "destiny-reconciler"


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def existing_index() -> Dict[str, Dict[str, Any]]:
    """Map normalized title -> {id, status} for every destiny in the store."""
    with destiny._connect() as conn:
        rows = conn.execute("SELECT id, title, status FROM destinies").fetchall()
    return {_norm(r["title"]): {"id": r["id"], "status": r["status"]} for r in rows}


def plan(intents: Iterable[Dict[str, Any]], existing: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Decide what to create. Pure: no store access.

    Each intent needs a title and a goal (3+ chars). ``trigger`` and
    ``verification`` are optional but reported as gaps, because a Destiny
    without them cannot be claimed or verified by a lane.
    """
    out: Dict[str, List[Dict[str, Any]]] = {"create": [], "duplicate": [], "invalid": [], "gaps": []}
    seen = dict(existing)
    for raw in intents:
        title = str(raw.get("title") or "").strip()
        goal = str(raw.get("goal") or "").strip()
        if len(title) < 3 or len(goal) < 3:
            out["invalid"].append({"title": title, "reason": "title and goal are required (3+ chars each)"})
            continue
        key = _norm(title)
        if key in seen:
            out["duplicate"].append({"title": title, "existing": seen[key]})
            continue
        missing = [f for f in ("trigger", "verification") if not str(raw.get(f) or "").strip()]
        if missing:
            out["gaps"].append({"title": title, "missing": missing})
        seen[key] = {"id": None, "status": "dormant"}
        out["create"].append({
            "title": title,
            "goal": goal,
            "trigger": raw.get("trigger") or None,
            "verification": raw.get("verification") or None,
            "branch": raw.get("branch") or None,
            "provenance": {"source": "gm-intent", "reconciler": ACTOR},
        })
    return out


def apply(planned: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Write the planned creates. Each returns the stored destiny or an error."""
    results: List[Dict[str, Any]] = []
    for item in planned.get("create", []):
        results.append(destiny.create_destiny(
            item["title"], item["goal"], branch=item.get("branch"), trigger=item.get("trigger"),
            verification=item.get("verification"), provenance=item.get("provenance"),
            status="dormant", actor=ACTOR))
    return results


@contextmanager
def _exclusive() -> Iterator[None]:
    """Serialize check-then-create across threads and processes on this host.

    Without this, two reconciles of the same title can both read it as absent
    and both insert: create_destiny has no uniqueness constraint.
    """
    lock_path = destiny.db_path().with_name(destiny.db_path().name + ".reconcile.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as fh:
        if _fcntl is not None:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
            try:
                yield
            finally:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
        else:
            fh.seek(0)
            _msvcrt.locking(fh.fileno(), _msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                fh.seek(0)
                _msvcrt.locking(fh.fileno(), _msvcrt.LK_UNLCK, 1)


def reconcile(intents: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Plan against the live store and apply. Idempotent by title, race-safe."""
    with _exclusive():
        planned = plan(list(intents), existing_index())
        created = apply(planned)
    return {"created": created, "duplicate": planned["duplicate"],
            "invalid": planned["invalid"], "gaps": planned["gaps"]}
