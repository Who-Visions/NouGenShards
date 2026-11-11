"""Time-first recall for the whole substrate: "recall march" means the month.

This is the native home of what the DavOs tool `shards_window` first did
on the phone - every entry point (core callers, the CLI, the MCP gateway,
Kaedra/DavOs tools, Griot) now shares one implementation:

  split_temporal(query)  -> (Window | None, remaining text)
      "march"                  -> March window, ""
      "gemini upgrade in march" -> March window, "gemini upgrade"
      "gemini upgrade"          -> None, "gemini upgrade"
  retrieve_window(when=..., query=..., limit=..., tz=...) -> dict
      per-day and per-type histograms over every grid DB, then a listing
      ranked by utility/access (not recency), digit-blind title dedupe,
      per-day cap, and the dominant bulk type folded into a count.
  format_packet(result)  -> the text an agent or a terminal reads.

Environment (Rule 0.2, fallbacks logged):
  NOUGEN_WINDOW_LIMIT            listing ceiling (fallback 20)
  NOUGEN_WINDOW_BULK_TYPE_SHARE  share of the window at which an event
                                 type counts as bulk and is folded (0.15)
  NOUGEN_TZ                      zone for day boundaries when none given
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from . import timewindow
from .timewindow import Window

logger = logging.getLogger(__name__)

_LEAD = re.compile(r"^(?:recall|remember|what happened|show me|browse)\s+", re.I)
_SEP = re.compile(r"\s+(?:in|from|during|for|on|at|around|since|back in)\s+", re.I)


def _env_int(name: str, fallback: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return fallback
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int; using %d", name, raw, fallback)
        return fallback


def _env_float(name: str, fallback: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw else fallback
    except ValueError:
        return fallback


def split_temporal(query: str, *, tz: Optional[str] = None, now=None) -> Tuple[Optional[Window], str]:
    """Pull the time phrase out of a recall query, if there is one.

    The whole query is tried first ("last week"), then the text after a
    temporal preposition ("gemini upgrade in march"), then a trailing or
    leading phrase of up to four words ("march 2026 gemini upgrade"). The
    remainder is what is left to text-search inside that window.
    """
    text = _LEAD.sub("", str(query or "").strip())
    if not text:
        return None, ""
    def parse(s: str):
        return timewindow.parse_window(s, tz=tz, now=now)

    win = parse(text)
    if win:
        return win, ""
    parts = _SEP.split(text)
    if len(parts) == 2:
        win = parse(parts[1])
        if win:
            return win, parts[0].strip()
    words = text.split()
    for n in range(min(4, len(words) - 1), 0, -1):
        tail, head = " ".join(words[-n:]), " ".join(words[:n])
        win = parse(tail)
        if win:
            return win, " ".join(words[:-n]).strip()
        win = parse(head)
        if win:
            return win, " ".join(words[n:]).strip()
    return None, text


def retrieve_window(when: Optional[str] = None, *, query: str = "", limit: Optional[int] = None,
                    tz: Optional[str] = None, start_utc: Optional[str] = None,
                    end_utc: Optional[str] = None) -> Dict[str, Any]:
    """Everything the grid recorded in a period, shaped for an agent to answer from."""
    from . import core, locator  # pylint: disable=import-outside-toplevel
    zone = tz or os.getenv("NOUGEN_TZ")
    if start_utc and end_utc:
        win = Window(start_utc, end_utc, f"{start_utc[:16]} .. {end_utc[:16]}", "explicit UTC bounds", zone or "UTC")
    else:
        when = str(when or "").strip()
        if not when:
            return {"error": "when is required (e.g. 'march', '2026-03', 'last week', 'yesterday 7pm')"}
        win = timewindow.parse_window(when, tz=zone)
        if win is None:
            return {"error": f"could not read {when!r} as a time period; say a month, date, year,"
                             f" quarter, clock time, or 'last N minutes/hours/days'", "when": when}
    ceiling = _env_int("NOUGEN_WINDOW_LIMIT", 20)
    limit = max(1, min(int(limit or ceiling), ceiling))
    query = str(query or "").strip()

    where = "timestamp >= ? AND timestamp < ?"
    params: list = [win.start_utc, win.end_utc]
    # Every word must appear somewhere in the row (title/content/tags), not
    # the exact phrase: "gemini upgrade" should find "Gemini Agent Upgrade".
    for word in query.split():
        like = f"%{word}%"
        where += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
        params += [like, like, like]
    errored: List[int] = []
    live_dbs = [i for i in range(1, core.MAX_DB_COUNT + 1) if core.get_db_path(i).exists()]

    def scan(i: int, sql: str, p: list):
        try:
            conn = core.get_connection(i)
        except (sqlite3.DatabaseError, OSError):
            errored.append(i) if i not in errored else None
            return []
        try:
            return conn.execute(sql, p).fetchall()
        except (sqlite3.DatabaseError, OSError) as exc:
            logger.warning("retrieve_window: DB %s unreadable, skipped: %s", i, exc)
            errored.append(i) if i not in errored else None
            return []
        finally:
            conn.close()

    by_day: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    total = 0
    for i in live_dbs:
        for d, n in scan(i, f"SELECT substr(timestamp,1,10), COUNT(*) FROM shards WHERE {where} GROUP BY 1", params):
            by_day[d] = by_day.get(d, 0) + n
            total += n
        for et, n in scan(i, f"SELECT event_type, COUNT(*) FROM shards WHERE {where} GROUP BY 1", params):
            by_type[et or ""] = by_type.get(et or "", 0) + n

    # Bulk types are whatever dominates THIS window (arXiv sweeps one month,
    # env scrapes another) - decided from the histogram, never a fixed list.
    share = _env_float("NOUGEN_WINDOW_BULK_TYPE_SHARE", 0.15)
    bulk = {et for et, n in by_type.items() if total and n / total >= share} if len(by_type) > 1 else set()
    type_filter = (" AND event_type NOT IN (%s)" % ",".join("?" * len(bulk))) if bulk else ""
    list_sql = (f"SELECT id, timestamp, event_type, title, tags, utility_score, access_count "
                f"FROM shards WHERE {where}{type_filter} "
                f"ORDER BY utility_score DESC, access_count DESC, timestamp DESC LIMIT ?")
    rows: List[dict] = []

    def collect(sql: str, extra: list):
        for i in live_dbs:
            for r in scan(i, sql, params + extra + [limit * 2]):
                rows.append({"id": r[0], "db_index": i, "locator": locator.format_locator(r[0], i),
                             "timestamp": r[1], "event_type": r[2], "title": r[3],
                             "tags": (r[4] or "")[:160], "utility": r[5], "access_count": r[6]})

    collect(list_sql, sorted(bulk))
    if not rows and bulk:          # the window was ONLY bulk rows: list those, not nothing
        bulk = set()
        collect(list_sql.replace(type_filter, ""), [])

    # Spread the listing: one import burst must not fill every slot, and
    # "Phoebus Memory 1472/1484/1506: Project" is one shape, not three.
    rows.sort(key=lambda r: (r["utility"] or 0, r["access_count"] or 0, r["timestamp"] or ""), reverse=True)
    per_day_cap = max(1, limit // max(1, min(len(by_day), 3)))
    seen: set = set()
    used: Dict[str, int] = {}
    picked: List[dict] = []
    for r in rows:
        key = re.sub(r"\d+", "#", " ".join(str(r["title"] or "").lower().split()))[:80]
        day = str(r["timestamp"] or "")[:10]
        if key in seen or used.get(day, 0) >= per_day_cap:
            continue
        seen.add(key)
        used[day] = used.get(day, 0) + 1
        picked.append(r)
        if len(picked) >= limit:
            break
    picked.sort(key=lambda r: r["timestamp"] or "", reverse=True)
    return {"when": when, "window": win.as_dict(), "query": query or None,
            "total": total, "shown": len(picked),
            "by_day": dict(sorted(by_day.items())),
            "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "bulk_types_folded": {et: by_type[et] for et in sorted(bulk)},
            "shards": picked, "databases_errored": errored,
            "note": ("empty window: nothing recorded in that period" if total == 0 else
                     f"{total} shards in {win.label}; listing the {len(picked)} most useful"
                     f" (distinct titles, by utility then access), newest first")}


def format_packet(res: Dict[str, Any], max_days: int = 5) -> str:
    """Terminal/agent-readable rendering of retrieve_window()."""
    if res.get("error"):
        return f"Window recall: {res['error']}"
    w = res["window"]
    lines = [f"Window: {w['label']}  [{w['start_utc']} .. {w['end_utc']}) tz={w['tz']}  ({w['interpreted_as']})"]
    if res.get("query"):
        lines.append(f"Narrowed to shards mentioning: {res['query']!r}")
    folded = ", ".join(f"{k} x{v}" for k, v in (res.get("bulk_types_folded") or {}).items())
    lines.append(f"Recorded: {res['total']} shards" + (f"; folded bulk: {folded}" if folded else ""))
    if res["by_day"]:
        busiest = sorted(res["by_day"].items(), key=lambda kv: -kv[1])[:max_days]
        lines.append("Busiest days: " + ", ".join(f"{d} ({n})" for d, n in busiest))
    if res["by_type"]:
        top = [f"{k or '?'} {v}" for k, v in list(res["by_type"].items())[:5]]
        lines.append("By type: " + ", ".join(top))
    if res.get("databases_errored"):
        lines.append(f"[COVERAGE WARNING] grid DBs unreadable: {res['databases_errored']} - counts are partial.")
    if not res["shards"]:
        lines.append("Nothing recorded in this window.")
    for s in res["shards"]:
        lines.append(f"- {str(s['timestamp'])[:16]}  {s['locator']}  [{s['event_type']}]  {s['title']}")
    return "\n".join(lines)
