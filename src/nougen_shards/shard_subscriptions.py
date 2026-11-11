"""Proactive shard surfacing: subscriptions that push new shards to you.

Recall only answers when asked. A subscription inverts that: name a set of tags
and/or keywords once, and every later ``surface()`` returns the shards captured
*since the last check* that match it -- before anyone thinks to search.

Origin: NouGenMorph of youtube y7iRJMkpu5U ("second brain" talk), shard 26643@db1.
The fleet already had capture, substrate, embeddings and RAG; the missing layer
was surfacing on subscription (#tag, feed, location) instead of on query.

Matching is on ``title`` and ``tags`` only. Those stay plaintext by contract
(core.capture docstring); content may be encrypted at rest, so matching it would
silently miss sealed shards and look like "no news".

State lives in one JSON file (subscriptions + a per-DB id cursor). A new
subscription starts at the current max id per DB, so it surfaces only what
arrives after it was made, never a flood of history.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from . import core


def _state_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return Path(path)
    return core.active_subdir("subscriptions") / "subscriptions.json"


def _load(path: Path) -> dict:
    if not path.exists():
        return {"subscriptions": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _db_paths() -> Iterable[tuple[int, Path]]:
    for idx in range(1, core.MAX_DB_COUNT + 1):
        p = core.get_db_path(idx)
        if p.exists():
            yield idx, p


def _max_ids() -> dict:
    out = {}
    for idx, p in _db_paths():
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            out[str(idx)] = con.execute("SELECT COALESCE(MAX(id), 0) FROM shards").fetchone()[0]
        except sqlite3.OperationalError:
            out[str(idx)] = 0
        finally:
            con.close()
    return out


def _norm(items: Optional[Iterable[str]]) -> list:
    return sorted({str(i).strip().lstrip("#").lower() for i in (items or []) if str(i).strip()})


def subscribe(name: str, tags: Optional[Iterable[str]] = None,
              keywords: Optional[Iterable[str]] = None, path: Optional[Path] = None) -> dict:
    """Create or replace a subscription. Cursor starts at 'now'."""
    tags, keywords = _norm(tags), _norm(keywords)
    if not tags and not keywords:
        raise ValueError("a subscription needs at least one tag or keyword")
    sp = _state_path(path)
    state = _load(sp)
    sub = {"tags": tags, "keywords": keywords, "cursor": _max_ids()}
    state["subscriptions"][name] = sub
    _save(sp, state)
    return sub


def unsubscribe(name: str, path: Optional[Path] = None) -> bool:
    sp = _state_path(path)
    state = _load(sp)
    gone = state["subscriptions"].pop(name, None) is not None
    _save(sp, state)
    return gone


def list_subscriptions(path: Optional[Path] = None) -> dict:
    return _load(_state_path(path))["subscriptions"]


def _matches(sub: dict, title: str, tags_raw: Optional[str]) -> bool:
    try:
        tags = {str(t).lstrip("#").lower() for t in json.loads(tags_raw or "[]")}
    except (ValueError, TypeError):
        tags = set()
    if sub["tags"] and tags & set(sub["tags"]):
        return True
    hay = " ".join([(title or "").lower(), *tags])
    return any(k in hay for k in sub["keywords"])


def surface(name: Optional[str] = None, advance: bool = True,
            path: Optional[Path] = None) -> dict:
    """Return new matching shards per subscription, oldest first; advance cursors.

    ``advance=False`` peeks without consuming. Cursors move past every scanned
    row (matched or not) so the next call never rescans the same ids.
    """
    sp = _state_path(path)
    state = _load(sp)
    subs = state["subscriptions"]
    names = [name] if name else list(subs)
    result = {}
    dbs = list(_db_paths())
    for n in names:
        sub = subs.get(n)
        if sub is None:
            raise KeyError(f"no subscription named {n!r}")
        hits = []
        for idx, p in dbs:
            key = str(idx)
            since = int(sub["cursor"].get(key, 0))
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            try:
                rows = con.execute(
                    "SELECT id, timestamp, event_type, title, tags FROM shards WHERE id > ? ORDER BY id",
                    (since,)).fetchall()
            except sqlite3.OperationalError:
                rows = []
            finally:
                con.close()
            for sid, ts, et, title, tags_raw in rows:
                if _matches(sub, title, tags_raw):
                    hits.append({"ref": f"{sid}@db{idx}", "id": sid, "db": idx,
                                 "timestamp": ts, "event_type": et, "title": title})
            if rows and advance:
                sub["cursor"][key] = rows[-1][0]
        hits.sort(key=lambda h: (h["timestamp"] or "", h["db"], h["id"]))
        # No truncation: the cursor already moved past these rows, so cutting the
        # list here would drop matches for good. Callers trim for display.
        result[n] = hits
    if advance:
        _save(sp, state)
    return result
