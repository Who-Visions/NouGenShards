"""
NouGenShards Production Node & Cortex HUD.
Architecture: FastAPI + Persistent Storage (/data) + Token Auth + Multi-tab Gradio UI.
"""
import os
import re
import sys
import json
import logging
import hashlib
import datetime
import contextlib
from typing import List, Optional

logger = logging.getLogger(__name__)
from fastapi import FastAPI, Header, HTTPException, Depends, Response, Query
from pydantic import BaseModel
import gradio as gr
import subprocess


# Add src to path for absolute imports. insert(0), not append: site-packages
# precedes an appended entry, so a stale installed nougen_shards would silently
# shadow the working tree (measured 2026-08-27: venv wheel frozen at 1.3.0 while
# src had diverged). Anchored to this file, not CWD, so a service launched from
# any directory still imports the tree it lives in.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

# Override Storage for HF Persistence
if os.environ.get("SPACE_ID"):
    os.environ["NOUGEN_HOME"] = "/data"
    os.environ["NOUGEN_VAULT_DIR"] = "/data/.vault"

from nougen_shards import bind_probe, core, history, mcp_oauth, tenants
from nougen_shards.federation import federated_retrieve
from nougen_shards.brain_scan import scan_environment

NODE_TOKEN = os.environ.get("NGS_NODE_TOKEN") or os.environ.get("SHARD_GATEWAY_TOKEN")


# --- Remote MCP server (mobile / Claude-app connector) ---
# Streamable-HTTP MCP endpoint mounted at /mcp so remote MCP clients (the
# Claude mobile/web app's custom connectors, MCP inspector, other agents) can
# use the node's memory directly. Deliberately exposes ONLY the memory tools:
# execute_sandboxed_code and brain scan/import stay stdio-local - remote code
# execution and container-filesystem recon do not belong on a network surface.
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

node_mcp = FastMCP(
    "NouGenShards",
    instructions=(
        "Persistent memory node. Use recall_memory before reasoning from "
        "scratch and capture_experience to store durable learnings."
    ),
    # Stateless JSON mode: every request is self-contained, which suits a
    # Space that may cold-start between calls.
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    # DNS-rebinding protection is a defense for loopback-bound servers whose
    # only gate is network locality; this endpoint is explicitly token-gated
    # (see _TokenGatedMCP) and served from a public host whose Host header
    # varies (hf.space, custom domains), so host allow-listing would only
    # break legitimate clients without adding security.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@node_mcp.tool()
def recall_memory(query: str, limit: int = 5) -> list:
    """Search the memory substrate. Returns ranked shards (fuzzy recall
    included when exact matching misses)."""
    # Federated for the same reason as POST /search below: a remote MCP client
    # should not get a narrower corpus than the local CLI.
    results = federated_retrieve(query, limit=max(1, min(limit, 20)))
    # Same compaction as POST /search (_json_safe): this path previously shipped
    # raw rows and was the one that leaked full vault bodies to MCP clients.
    return [_json_safe(r) for r in results]


@node_mcp.tool()
def capture_experience(title: str, content: str, event_type: str = "KNOWLEDGE",
                       tags: list[str] | None = None,
                       original_timestamp: str | None = None,
                       event_time_original: str | None = None,
                       source_created_at: str | None = None,
                       source_modified_at: str | None = None,
                       captured_at: str | None = None,
                       ai_first_touched_at: str | None = None,
                       ai_last_touched_at: str | None = None,
                       migrated_at: str | None = None,
                       amended_at: list[str] | str | None = None,
                       temporal_meta: dict | str | None = None) -> dict:
    """Store a unit of experience as a shard (deduplicated by content).

    `original_timestamp` / `event_time_original` (ISO-8601) stamps migrated
    content at its true era instead of capture time; invalid values fall back to now."""
    ok = core.capture(event_type, title, content, tags=tags,
                      original_timestamp=original_timestamp,
                      event_time_original=event_time_original,
                      source_created_at=source_created_at,
                      source_modified_at=source_modified_at,
                      captured_at=captured_at,
                      ai_first_touched_at=ai_first_touched_at,
                      ai_last_touched_at=ai_last_touched_at,
                      migrated_at=migrated_at,
                      amended_at=amended_at,
                      temporal_meta=temporal_meta)
    return {"captured": bool(ok)}


@node_mcp.tool()
def mark_utility(shard_id: int, worked: bool, db_index: int | None = None) -> dict:
    """Feed back whether a recalled shard was useful; adjusts its ranking prior."""
    core.mark_shard(shard_id, worked=worked, db_index=db_index)
    return {"marked": shard_id, "worked": worked}


@node_mcp.tool()
def node_status() -> dict:
    """Node health: shard count and storage mode."""
    return {"status": "ignited",
            "total_shards": _total_shards(),
            "storage": os.environ.get("NOUGEN_HOME", "default")}


def _window_search(query: str = "", since: Optional[str] = None,
                   until: Optional[str] = None, limit: int = 10) -> list:
    """Retrieve inside a time window, newest first.

    core.retrieve() ranks purely on content relevance -- there is no timestamp
    filter and no sort-by-date, so asking it for "March 2026" only matches
    shards whose TEXT contains those tokens and buries them under whatever is
    densest today. For an archive meant to be a witness, being unable to ask
    "what was I working on then" is a real gap, not a phrasing problem.

    Filtering happens in SQL, before scoring, so a sparse era still returns its
    shards instead of losing them to a relevance cut computed over the whole
    grid. Resolves date bounds against
    COALESCE(json_extract(temporal_meta, '$.event_time_original'), original_timestamp, timestamp).
    """
    ts_expr = "COALESCE(json_extract(temporal_meta, '$.event_time_original'), original_timestamp, timestamp)"
    where, params = [], []
    if since:
        where.append(f"{ts_expr} >= ?")
        params.append(since)
    if until:
        # Inclusive: "2026-03" should cover all of March, and "2026-03-14"
        # the whole day, so pad the bound to the end of whatever precision
        # the caller gave rather than cutting at midnight.
        params.append(until + "\ufffd")
        where.append(f"{ts_expr} <= ?")

    q = (query or "").strip()
    rows = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        try:
            conn = core.get_connection(i)
        except Exception:
            continue
        try:
            clauses = list(where)
            args = list(params)
            # Window browsing sees the research corpus, never the plumbing.
            _nr = core.no_recall_event_types()
            if _nr:
                clauses.append(
                    "UPPER(event_type) NOT IN (%s)" % ",".join("?" * len(_nr))
                )
                args.extend(_nr)
            if q:
                # Trigram FTS: match on the phrase, quoted so punctuation in the
                # query cannot be read as FTS operator syntax.
                clauses.append("id IN (SELECT rowid FROM shards_fts WHERE shards_fts MATCH ?)")
                args.append('"' + q.replace('"', '""') + '"')
            sql = (f"SELECT id, timestamp, event_type, title, content, tags, utility_score, "
                   f"temporal_meta, original_timestamp, {ts_expr} AS effective_timestamp "
                   f"FROM shards")
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += f" ORDER BY {ts_expr} DESC LIMIT ?"
            args.append(limit)
            for r in conn.execute(sql, args):
                rows.append({"id": r[0], "timestamp": r[1], "event_type": r[2],
                             "title": r[3], "content": r[4], "tags": r[5],
                             "utility_score": r[6],
                             "temporal_meta": r[7] if len(r) > 7 else None,
                             "original_timestamp": r[8] if len(r) > 8 else None,
                             "effective_timestamp": r[9] if len(r) > 9 else r[1],
                             "_db_index": i})
        except Exception:
            # A malformed FTS query or a bad shard row on one DB must not sink
            # the whole sweep -- the other eight still have answers.
            continue
        finally:
            conn.close()

    rows.sort(key=lambda x: str(x.get("effective_timestamp") or x.get("original_timestamp") or x.get("timestamp") or ""), reverse=True)
    return rows[:limit]


def _health_cache_ttl() -> float:
    """TTL for the expensive health/coverage aggregates. 0 disables caching.

    /health must answer in well under a second even while a federated search is
    hammering the disk (measured 2026-08-16: 7s under load). The aggregates it
    reports move on capture cadence, not request cadence, so a short cache
    changes nothing a caller can act on."""
    return float(os.environ.get("NOUGEN_HEALTH_CACHE_S", "30"))


#: (value, monotonic_ts) per aggregate. Stale-while-computing is acceptable:
#: these are counts, not auth gates — the gates in /health are re-read live.
_AGG_CACHE: dict = {}


def _cached(key: str, compute):
    ttl = _health_cache_ttl()
    if ttl <= 0:
        return compute()
    import time as _time
    hit = _AGG_CACHE.get(key)
    now = _time.monotonic()
    if hit is not None and now - hit[1] < ttl:
        return hit[0]
    value = compute()
    _AGG_CACHE[key] = (value, now)
    return value


def _federated_coverage() -> dict | None:
    """Registered federated read-through stores, so a recall MISS can be told
    apart from NOT MOUNTED at the federation layer too (decision 16729).

    Additive-only: consumers of substrate_coverage parse tolerantly, and this
    section never replaces or renames an existing field. Env-gated via
    NOUGEN_COVERAGE_FEDERATED (default on); returns None when disabled so the
    section disappears entirely rather than lying with zeros. Every store is
    opened read-only and degrades independently into `errored`.
    """
    if core.active_tenant_id() != "owner":
        return None
    if os.environ.get("NOUGEN_COVERAGE_FEDERATED", "1").strip().lower() in (
            "0", "false", "off", "no"):
        return None
    import sqlite3
    from pathlib import Path
    from nougen_shards import keymaker
    from nougen_shards.connectors.local_vault import _is_valid_identifier
    try:
        confs = keymaker.list_local_vaults()
    except Exception:  # keymaker store unreadable ≠ coverage endpoint down
        confs = []
    names: list = []
    errored: list = []
    rows_total = 0
    for conf in confs:
        stem = Path(str(conf.get("path", ""))).stem or f"id_{conf.get('id')}"
        table = conf.get("table_name", "")
        try:
            if not _is_valid_identifier(table):
                raise ValueError("invalid table identifier")
            conn = sqlite3.connect(
                f"file:{conf['path']}?mode=ro", uri=True, timeout=5)
            try:
                n = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            finally:
                conn.close()
            names.append(stem)
            rows_total += int(n)
        except Exception:
            errored.append(stem)
    return {"stores": len(names), "names": names,
            "rows_total": rows_total, "errored": errored}


@node_mcp.tool()
def substrate_coverage() -> dict:
    """What this node actually holds, so a recall MISS can be told apart from a
    PARTIAL MOUNT.

    Without this, an empty recall is ambiguous in the worst way: it reads as
    "that memory does not exist" when it may mean "this node never held that
    era". Measured on outpost 2026-08-15: March 2026 returned nothing, and the
    honest answer was a capture gap between two live months -- not a missing
    memory, and not a retrieval failure.

    Returns the span, the total, and a per-month count so a caller can see the
    holes rather than infer them."""
    from collections import Counter
    per_month = Counter()
    lo, hi, total = None, None, 0
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        try:
            conn = core.get_connection(i)
        except Exception:
            continue
        try:
            # Aggregate in SQL: iterating every row in Python made this tool an
            # O(corpus) scan per call (a measured contributor to the 2026-08-28
            # connector timeouts at 200k+ shards).
            for month, n, month_lo, month_hi in conn.execute(
                    "SELECT substr(timestamp, 1, 7), COUNT(*), MIN(timestamp), MAX(timestamp) "
                    "FROM shards WHERE timestamp IS NOT NULL GROUP BY substr(timestamp, 1, 7)"):
                month = str(month)
                per_month[month] += int(n)
                total += int(n)
                month_lo, month_hi = str(month_lo), str(month_hi)
                if lo is None or month_lo < lo:
                    lo = month_lo
                if hi is None or month_hi > hi:
                    hi = month_hi
        except Exception:
            continue
        finally:
            conn.close()

    months = sorted(per_month)
    gaps = []
    if months:
        y, m = map(int, months[0].split("-"))
        ey, em = map(int, months[-1].split("-"))
        while (y, m) <= (ey, em):
            key = f"{y:04d}-{m:02d}"
            if key not in per_month:
                gaps.append(key)
            m += 1
            if m == 13:
                y, m = y + 1, 1
    # Two ways an answer can be partial, and they need different responses.
    # A gap in `empty_months` means this node never captured that era. A grid
    # that is not fully mounted means it cannot read what it did capture, and
    # `total_shards` above is then a count of the readable part only. Reporting
    # the span without the mount state would let the second masquerade as the
    # first: a month reads as empty either way.
    # Density invariant (fleet decision, relay leg 20260828T053457Z): monthly
    # coverage must be dense from the grid's adoption era onward. A gap inside
    # that window is a capture regression, not history -- surface it as a
    # first-class violation instead of leaving callers to eyeball `months`.
    dense_since = os.environ.get("NOUGEN_COVERAGE_DENSE_SINCE", "2025-10")
    dense_min = int(os.environ.get("NOUGEN_COVERAGE_MIN_PER_MONTH", "1"))
    now_month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    dense_gaps = []
    try:
        y, m = map(int, dense_since.split("-"))
        ny, nm = map(int, now_month.split("-"))
        while (y, m) <= (ny, nm):
            key = f"{y:04d}-{m:02d}"
            if per_month.get(key, 0) < dense_min:
                dense_gaps.append(key)
            m += 1
            if m == 13:
                y, m = y + 1, 1
    except ValueError:
        dense_gaps = [f"invalid NOUGEN_COVERAGE_DENSE_SINCE: {dense_since!r}"]
    return {"total_shards": total,
            "span": {"earliest": lo, "latest": hi},
            "months": dict(sorted(per_month.items())),
            "empty_months": gaps,
            "density_invariant": {"since": dense_since,
                                  "min_per_month": dense_min,
                                  "ok": not dense_gaps,
                                  "violations": dense_gaps},
            # Cache key carries the active vault: a bare "substrate" key is
            # module-level state shared across tenants, so it would serve one
            # tenant's counts and DB detail to another.
            "grid": _cached(f"substrate:{core.active_vault_dir()}", _substrate_coverage),
            "vault": str(core.active_vault_dir()),
            # Federated read-through extent (decision 16729): "not found" must
            # be distinguishable from "not mounted" at the federation layer.
            # Cached: enumerating 40+ stores' row counts costs ~3.5s live
            # (nougen_memories alone is 379k rows) and moves on capture cadence.
            "federated_stores": _cached("federated", _federated_coverage)}


@node_mcp.tool()
def recall_window(query: str = "", since: str | None = None,
                  until: str | None = None, limit: int = 10) -> list:
    """Browse the vault by ERA, newest first -- the date-filtered counterpart to
    recall_memory.

    recall_memory ranks on content relevance only, so "what was I doing in
    March 2026" returns whatever mentions those words, topped by today's
    densest writes. This filters on the timestamp first.

    since/until are ISO prefixes and both are inclusive: since="2026-03",
    until="2026-03" is all of March; until="2026-03-14" covers that whole day.
    query is optional -- omit it to page an era, supply it to search within one.
    """
    return _window_search(query=query, since=since, until=until,
                          limit=max(1, min(limit, 50)))


def _window_page_max() -> int:
    """Per-page ceiling for cursor pagination, env-first (NOUGEN_WINDOW_PAGE_MAX)."""
    raw = os.environ.get("NOUGEN_WINDOW_PAGE_MAX", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            logger.warning("NOUGEN_WINDOW_PAGE_MAX=%r not an int; using fallback", raw)
    return 200


def _window_clauses(query: str, since: Optional[str], until: Optional[str]) -> tuple:
    """The one filter set shared by paging and counting, mirroring _window_search:
    era bounds, the no_recall event-type exclusion, and the quoted FTS clause.
    Page enumeration and the count tool MUST agree row-for-row, so they build
    their WHERE from here and nowhere else."""
    ts_expr = "COALESCE(json_extract(temporal_meta, '$.event_time_original'), original_timestamp, timestamp)"
    where, params = [], []
    if since:
        where.append(f"{ts_expr} >= ?")
        params.append(since)
    if until:
        # Inclusive prefix bound, same convention as _window_search.
        where.append(f"{ts_expr} <= ?")
        params.append(until + "\ufffd")
    _nr = core.no_recall_event_types()
    if _nr:
        where.append("UPPER(event_type) NOT IN (%s)" % ",".join("?" * len(_nr)))
        params.extend(_nr)
    q = (query or "").strip()
    if q:
        where.append("id IN (SELECT rowid FROM shards_fts WHERE shards_fts MATCH ?)")
        params.append('"' + q.replace('"', '""') + '"')
    return where, params


def _cursor_decode(cursor: str) -> tuple:
    """Cursor is opaque to callers but is simply 'timestamp|db_index|id' — the
    total-order key (timestamp DESC, db_index ASC, id ASC) of the last row of
    the previous page. ISO timestamps never contain '|'."""
    ts, db, sid = cursor.rsplit("|", 2)
    return ts, int(db), int(sid)


def _window_page(query: str = "", since: Optional[str] = None,
                 until: Optional[str] = None, limit: int = 10,
                 cursor: Optional[str] = None) -> dict:
    """Keyset-paginated era sweep: deterministic total order over
    (timestamp DESC, db_index ASC, id ASC), so walking pages to exhaustion
    enumerates every matching shard exactly once — the exhaustive-audit
    counterpart to _window_search's top-N sample."""
    ts_expr = "COALESCE(json_extract(temporal_meta, '$.event_time_original'), original_timestamp, timestamp)"
    limit = max(1, min(limit, _window_page_max()))
    base_where, base_params = _window_clauses(query, since, until)
    cur = None
    if cursor:
        try:
            cur = _cursor_decode(cursor)
        except (ValueError, TypeError):
            return {"rows": [], "next_cursor": None, "returned": 0,
                    "error": "bad cursor; restart the sweep without one"}

    rows = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        try:
            conn = core.get_connection(i)
        except Exception:
            continue
        try:
            clauses = list(base_where)
            args = list(base_params)
            if cur is not None:
                ts0, db0, id0 = cur
                if i < db0:
                    clauses.append(f"{ts_expr} < ?")
                    args.append(ts0)
                elif i == db0:
                    clauses.append(f"({ts_expr} < ? OR ({ts_expr} = ? AND id > ?))")
                    args.extend([ts0, ts0, id0])
                else:
                    clauses.append(f"{ts_expr} <= ?")
                    args.append(ts0)
            sql = (f"SELECT id, timestamp, event_type, title, content, tags, "
                   f"utility_score, temporal_meta, original_timestamp, {ts_expr} AS effective_timestamp FROM shards")
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            # limit+1 per DB guarantees the merged set can both fill the page
            # and prove whether anything remains beyond it.
            sql += f" ORDER BY {ts_expr} DESC, id ASC LIMIT ?"
            args.append(limit + 1)
            for r in conn.execute(sql, args):
                rows.append({"id": r[0], "timestamp": r[1], "event_type": r[2],
                             "title": r[3], "content": r[4], "tags": r[5],
                             "utility_score": r[6],
                             "temporal_meta": r[7] if len(r) > 7 else None,
                             "original_timestamp": r[8] if len(r) > 8 else None,
                             "effective_timestamp": r[9] if len(r) > 9 else r[1],
                             "_db_index": i})
        except Exception:
            # One bad DB must not sink the sweep; the others still answer.
            continue
        finally:
            conn.close()

    def _get_eff_ts(x):
        return str(x.get("effective_timestamp") or x.get("original_timestamp") or x.get("timestamp") or "")

    if cur is not None:
        # Belt-and-suspenders: drop anything not strictly after the cursor in
        # the total order, in case a DB's SQL branch ever drifts.
        ts0, db0, id0 = cur
        rows = [r for r in rows
                if _get_eff_ts(r) < ts0
                or (_get_eff_ts(r) == ts0
                    and (r["_db_index"] > db0
                         or (r["_db_index"] == db0 and r["id"] > id0)))]

    # Stable two-stage sort realizes (effective_timestamp DESC, db ASC, id ASC).
    rows.sort(key=lambda r: (r["_db_index"], r["id"]))
    rows.sort(key=_get_eff_ts, reverse=True)
    page = rows[:limit]
    has_more = len(rows) > limit
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = "%s|%d|%d" % (_get_eff_ts(last), last["_db_index"], last["id"])
    return {"rows": page, "next_cursor": next_cursor, "returned": len(page)}


@node_mcp.tool()
def recall_window_page(query: str = "", since: str | None = None,
                       until: str | None = None, limit: int = 10,
                       cursor: str | None = None) -> dict:
    """Exhaustively enumerate an era, page by page — the audit counterpart to
    recall_window, which stays a top-N sample.

    Walk: call without cursor, then keep passing back next_cursor until it
    comes back null. Every matching shard is returned exactly once, in
    (timestamp DESC) order, with cross-DB ties broken deterministically.
    Pair with recall_window_count to prove the sweep saw the full row count.
    """
    return _window_page(query=query, since=since, until=until,
                        limit=limit, cursor=cursor)


@node_mcp.tool()
def recall_window_count(query: str = "", since: str | None = None,
                        until: str | None = None) -> dict:
    """Exact matching-row count for an era, per cluster DB and total — built
    from the same filters as recall_window_page, so an exhaustive page walk
    and this count always agree. This is how an audit proves completeness."""
    where, params = _window_clauses(query, since, until)
    per_db, total = {}, 0
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        try:
            conn = core.get_connection(i)
        except Exception:
            continue
        try:
            sql = "SELECT COUNT(*) FROM shards"
            if where:
                sql += " WHERE " + " AND ".join(where)
            n = conn.execute(sql, params).fetchone()[0]
            per_db[str(i)] = n
            total += n
        except Exception:
            per_db[str(i)] = None
            continue
        finally:
            conn.close()
    return {"total": total, "per_db": per_db}


def _resolve_shard(shard_id: int, db_index: Optional[int] = None,
                   expect_title: Optional[str] = None) -> tuple:
    """Pin a shard id to exactly one cluster DB, or refuse.

    Shard ids are per-DB AUTOINCREMENT, so id 2416 exists in several of the 9
    DBs at once. Every mutation here keys on an id, and acting on "the first
    match" would silently mutate a different shard than the caller meant --
    tolerable for a utility nudge, unacceptable for a retraction or a delete.

    Returns (db_index, title). Raises ValueError naming the candidates when the
    id is ambiguous, so the caller disambiguates instead of gambling.
    """
    hits = []
    indices = [db_index] if db_index is not None else range(1, core.MAX_DB_COUNT + 1)
    for i in indices:
        if not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            row = conn.execute("SELECT title FROM shards WHERE id = ?", (shard_id,)).fetchone()
        finally:
            conn.close()
        if row:
            hits.append((i, row[0]))

    if not hits:
        raise ValueError(f"no shard with id {shard_id}"
                         + (f" in db {db_index}" if db_index is not None else " in any cluster DB"))

    if expect_title:
        exact = [h for h in hits if h[1] == expect_title]
        if not exact:
            found = "; ".join(f"db{i}: {t[:60]!r}" for i, t in hits)
            raise ValueError(
                f"title mismatch for id {shard_id} -- refusing to touch a shard the "
                f"caller has not seen. Expected {expect_title[:60]!r}; found {found}")
        hits = exact

    if len(hits) > 1:
        found = "; ".join(f"db{i}: {t[:50]!r}" for i, t in hits)
        raise ValueError(
            f"id {shard_id} is ambiguous across cluster DBs ({found}). "
            f"Pass db_index (recall results carry _db_index) to name the one you mean.")

    return hits[0]


@node_mcp.tool()
def shard_amend(shard_id: int, note: str, db_index: int | None = None,
                confirm_title: str | None = None) -> dict:
    """Append a dated note to an existing shard, preserving everything already
    there. The append-only way to correct or extend a shard: history is never
    rewritten, it grows. Use for living dossiers and for correcting a shard that
    later turned out to be partly wrong.

    PASS confirm_title. Recall is fuzzy and can hand back a neighbouring
    shard's id; amending the wrong shard writes your note into someone else's
    record. Supplying the expected title makes that a refusal."""
    idx, title = _resolve_shard(shard_id, db_index, expect_title=confirm_title)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    conn = core.get_connection(idx)
    try:
        row = conn.execute("SELECT content FROM shards WHERE id = ?", (shard_id,)).fetchone()
        merged = f"{row[0]}\n\n--- UPDATE {stamp} ---\n{note}"
        conn.execute("UPDATE shards SET content = ? WHERE id = ?", (merged, shard_id))
        conn.commit()
    finally:
        conn.close()
    return {"amended": shard_id, "db_index": idx, "title": title, "added_chars": len(note)}


@node_mcp.tool()
def shard_retract(shard_id: int, reason: str, db_index: int | None = None,
                  confirm_title: str | None = None) -> dict:
    """Retract a shard WITHOUT erasing it: prefix its title [RETRACTED], append
    the reason, tag it `retracted`, and floor its utility so outcome-weighted
    recall stops surfacing it.

    Preferred over shard_forget. The row survives, so the grid still records
    that this was once believed and why it stopped being true -- which is the
    whole point of a witness. Reach for forget only when the content must not
    exist (a secret pasted in by mistake).

    PASS confirm_title. Recall is fuzzy: a query can return a plausible
    neighbour rather than the shard you meant, and the id alone will not tell
    you. This was not theoretical -- on 2026-08-15 a self-test recalled by
    title, got a *different* shard's id back, and retracted real content.
    Supplying the title you believe you are acting on turns that into a refusal
    instead of damage."""
    idx, title = _resolve_shard(shard_id, db_index, expect_title=confirm_title)
    if title.startswith("[RETRACTED]"):
        return {"retracted": shard_id, "db_index": idx, "already": True, "title": title}
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    conn = core.get_connection(idx)
    try:
        row = conn.execute("SELECT content, tags FROM shards WHERE id = ?", (shard_id,)).fetchone()
        try:
            tags = json.loads(row[1]) if row[1] else []
            if not isinstance(tags, list):
                tags = []
        except Exception:
            tags = []
        if "retracted" not in tags:
            tags.append("retracted")
        conn.execute(
            "UPDATE shards SET title = ?, content = ?, tags = ?, utility_score = ? WHERE id = ?",
            (f"[RETRACTED] {title}",
             f"{row[0]}\n\n--- RETRACTED {stamp} ---\n{reason}",
             json.dumps(tags), 0.0, shard_id))
        conn.commit()
    finally:
        conn.close()
    return {"retracted": shard_id, "db_index": idx, "title": f"[RETRACTED] {title}"}


@node_mcp.tool()
def shard_forget(shard_id: int, confirm_title: str, db_index: int | None = None) -> dict:
    """PERMANENTLY delete a shard. Irreversible -- there is no undo and no
    tombstone; the row and its FTS index entry are gone.

    confirm_title must match the shard's current title exactly. That is not
    ceremony: ids repeat across the 9 cluster DBs, so an id alone can name a
    shard the caller has never seen. Requiring the title proves the caller is
    looking at the thing they are deleting.

    Prefer shard_retract. Use this only when the content must not exist."""
    idx, title = _resolve_shard(shard_id, db_index, expect_title=confirm_title)
    conn = core.get_connection(idx)
    try:
        # The shards_ad trigger keeps shards_fts in sync on delete.
        conn.execute("DELETE FROM shards WHERE id = ?", (shard_id,))
        conn.commit()
    finally:
        conn.close()
    return {"forgotten": shard_id, "db_index": idx, "title": title, "recoverable": False}


@node_mcp.tool()
def vault_put(key: str, value: str) -> dict:
    """Write a secret into the keymaker vault. WRITE-ONLY BY DESIGN.

    There is deliberately no vault_get on this node. Reading secrets over a
    network surface would put every provider key behind one bearer token; a
    remote lane can rotate a credential but can never exfiltrate one.

    Returns a SHA-256 fingerprint (first 12 hex) so the caller can prove the
    stored value matches what they intended without the value being echoed."""
    if core.active_tenant_id() != "owner":
        raise PermissionError("the secrets vault is owner-only")
    from nougen_shards import keymaker
    keymaker.init_vault()
    keymaker.ingest_secret(key, value)
    stored = keymaker.get_secret(key)
    return {"key": key,
            "stored": stored == value,
            "fingerprint": hashlib.sha256(value.encode()).hexdigest()[:12],
            "vault": str(keymaker.DB_PATH)}


@node_mcp.tool()
def vault_list() -> list:
    """Secret NAMES and fingerprints in the vault -- never values.

    Enough to answer "is this credential present, and is it the one I think?"
    (compare fingerprints) without the vault becoming readable."""
    if core.active_tenant_id() != "owner":
        raise PermissionError("the secrets vault is owner-only")
    from nougen_shards import keymaker
    out = []
    if not keymaker.DB_PATH.exists():
        return out
    import sqlite3 as _sq
    conn = _sq.connect(str(keymaker.DB_PATH))
    try:
        rows = conn.execute("SELECT secret_key, last_rotated FROM secrets ORDER BY secret_key").fetchall()
    finally:
        conn.close()
    for name, rotated in rows:
        val = keymaker.get_secret(name)
        out.append({"key": name, "last_rotated": rotated,
                    "fingerprint": hashlib.sha256(val.encode()).hexdigest()[:12] if val else None})
    return out


_mcp_asgi = node_mcp.streamable_http_app()


def _seed_upstreams() -> list:
    """Register read-through upstreams from the environment at boot.

    ``federated_retrieve`` already fans out to remote nodes, but it reads its
    peers from the keymaker ``cloud_nodes`` table. On a host with ephemeral
    storage that row does not survive a restart, so a node that was linked by
    hand silently stops federating after the next deploy and answers from
    whatever local shards it happens to have. Seeding from env makes the link
    a property of the deployment rather than of the disk.

    ``NGS_UPSTREAM_URL`` takes one URL or several separated by commas. Names
    come from ``NGS_UPSTREAM_NAME`` positionally, else from the host.
    """
    raw = os.environ.get("NGS_UPSTREAM_URL", "").strip()
    if not raw:
        return []

    urls = [u.strip() for u in raw.split(",") if u.strip()]
    names = [n.strip() for n in os.environ.get("NGS_UPSTREAM_NAME", "").split(",") if n.strip()]

    seeded = []
    for i, url in enumerate(urls):
        if i < len(names):
            name = names[i]
        else:
            try:
                from urllib.parse import urlparse
                name = urlparse(url).hostname or f"upstream-{i + 1}"
            except Exception:
                name = f"upstream-{i + 1}"
        try:
            from nougen_shards import keymaker
            keymaker.register_cloud_node(url, name)
            seeded.append({"name": name, "url": url})
            logging.info("read-through upstream registered: %s -> %s", name, url)
        except Exception as exc:
            # Never block startup on a peer. A node that cannot reach its
            # upstream still serves what it has; it just says so in /health.
            logging.warning("could not register upstream %s (%s): %s", name, url, exc)
    return seeded


def _registered_upstreams() -> list:
    """Read-through peers this node will fan out to, without their secrets."""
    # Local import keeps this helper extractable by the focused AST tests.
    from nougen_shards import core as active_core
    if active_core.active_tenant_id() != "owner":
        return []
    try:
        from nougen_shards import keymaker
        return [
            {"name": row["name"], "url": row["url"]}
            for row in keymaker.list_cloud_nodes()
        ]
    except Exception as exc:
        logging.warning("could not list upstreams: %s", exc)
        return []


@contextlib.asynccontextmanager
async def _lifespan(_app):
    _seed_upstreams()
    # The streamable-HTTP session manager needs a running task group.
    async with node_mcp.session_manager.run():
        yield


# Resolve the bind host once, at import time, so every fail-closed guard below
# (interactive API docs here, the Cortex HUD further down) protects ASGI servers
# that import `app` directly - uvicorn app:app, gunicorn, HF Spaces - where the
# __main__ block never runs.
_on_platform = bind_probe.on_managed_platform()
_bind_host = bind_probe.normalize_host(bind_probe.probed_bind_host()) or "127.0.0.1"
_network_exposed = bind_probe.is_network_exposed()

# Fail closed on the interactive API docs for the same reason as the HUD: /docs,
# /redoc and /openapi.json publish the entire surface - /search, /capture,
# /sync/push and the full-vault /sync/pull export - to anyone who asks. The data
# behind them is token-gated, but handing an unauthenticated caller the map is
# free reconnaissance. On a network-reachable host they are withheld unless the
# operator opts in with NGS_DOCS_PUBLIC=1; on loopback they stay on, because a
# local node is exactly where you want them while developing.
_docs_public = os.environ.get("NGS_DOCS_PUBLIC", "").strip().lower() in ("1", "true", "yes", "on")
_serve_docs = _docs_public or not _network_exposed

app = FastAPI(
    title="NouGenShards Node",
    lifespan=_lifespan,
    docs_url="/docs" if _serve_docs else None,
    redoc_url="/redoc" if _serve_docs else None,
    openapi_url="/openapi.json" if _serve_docs else None,
)
if not _serve_docs:
    print(
        "[WARN] Interactive API docs not mounted: host is network-exposed "
        f"(bind={_bind_host}, managed_platform={_on_platform}). "
        "Set NGS_DOCS_PUBLIC=1 to publish /docs, /redoc and /openapi.json anyway.",
        file=sys.stderr,
    )

# --- Security ---

# A bare "Invalid node token." sent a real diagnosis down the wrong path: the
# Claude connector UI reads a 401 on an MCP endpoint as "this server wants me to
# sign in", tries OAuth dynamic client registration, finds no metadata to
# register against, and reports a sign-in-service failure. The node has no OAuth
# layer and does not need one — it wants a token — so the 401 says so, and names
# the query form, because connectors cannot attach custom headers.
#
# Deliberately NOT accompanied by a `WWW-Authenticate: Bearer` header: that is
# what tells a client to go looking for an authorization server, and there is
# none here. Advertising one would restart the same broken hunt.
_BAD_TOKEN_DETAIL = (
    "Invalid or missing node token. Send it as the X-NGS-Token header, or "
    "append ?token=<node token> to the URL — Claude connectors cannot set "
    "custom headers, so the query form is the path for those."
)


def _credentials_configured() -> bool:
    try:
        return tenants.credentials_configured(NODE_TOKEN)
    except tenants.TenantRegistryError as exc:
        logger.error("tenant registry rejected: %s", exc)
        raise HTTPException(status_code=503, detail="Tenant registry is invalid.") from exc


def _resolve_tenant_credential(supplied: Optional[str]) -> Optional[tenants.Tenant]:
    try:
        return tenants.resolve_token(supplied, NODE_TOKEN, core.GLOBAL_DIR)
    except tenants.TenantRegistryError as exc:
        logger.error("tenant registry rejected: %s", exc)
        raise HTTPException(status_code=503, detail="Tenant registry is invalid.") from exc


def verify_token(
    x_ngs_token: Optional[str] = Header(None, alias="X-NGS-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    shard_gateway_token: Optional[str] = Header(None, alias="Shard_Gateway_Token"),
    shard_gateway_token_dash: Optional[str] = Header(None, alias="Shard-Gateway-Token"),
    x_shard_gateway_token: Optional[str] = Header(None, alias="X-Shard-Gateway-Token"),
    token: Optional[str] = Query(None),
) -> tenants.Tenant:
    if not _credentials_configured():
        raise HTTPException(status_code=503, detail="Node write-auth not configured.")
    supplied = x_ngs_token
    if not supplied and authorization:
        if authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        else:
            supplied = authorization.strip()
    if not supplied:
        supplied = shard_gateway_token or shard_gateway_token_dash or x_shard_gateway_token or token
    tenant = _resolve_tenant_credential(supplied)
    if tenant is None:
        raise HTTPException(status_code=401, detail=_BAD_TOKEN_DETAIL)
    return tenant


async def tenant_vault_context(tenant: tenants.Tenant = Depends(verify_token)):
    """Hold the request's ContextVar binding through the complete handler."""
    tokens = core.bind_active_vault(tenant.vault_dir, tenant.tenant_id)
    try:
        yield tenant
    finally:
        core.reset_active_vault(tokens)

# --- API Endpoints ---

def _substrate_coverage() -> dict:
    """Per-database mount state for the shard grid.

    A caller that gets nothing back needs to know whether the substrate said
    "no match" or "I could not read most of myself". Counting only the
    databases that happen to open reports a number that looks authoritative
    while hiding how much is absent, so every index is accounted for here as
    exactly one of mounted, missing or errored.
    """
    expected = core.MAX_DB_COUNT
    mounted, missing, errored, shards = [], [], [], 0

    for i in range(1, expected + 1):
        path = core.get_db_path(i)
        if not path.exists():
            missing.append(i)
            continue
        try:
            conn = core.get_connection(i)
            try:
                count = conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
            finally:
                conn.close()
        except Exception as exc:
            # Reason, not just the fact - a locked database and a corrupt one
            # need different responses.
            errored.append({"index": i, "error": f"{type(exc).__name__}: {exc}"})
            continue
        mounted.append({"index": i, "shards": count})
        shards += count

    complete = len(mounted) == expected
    upstreams = _registered_upstreams()
    return {
        "complete": complete,
        "databases_expected": expected,
        "databases_mounted": len(mounted),
        "databases_missing": missing,
        "databases_errored": errored,
        "shards": shards,
        # With read-through configured, local shards are a cache in front of
        # the upstream rather than the whole corpus, so an incomplete local
        # grid stops being the only way an answer can be partial.
        "read_through": bool(upstreams),
        "upstreams": upstreams,
        # Recall answers can only be trusted across the part that is mounted -
        # unless an upstream is carrying the corpus, in which case a thin local
        # grid is expected rather than a fault.
        "recall_trustworthy": complete or bool(upstreams),
        "detail": mounted,
    }


def _total_shards() -> int:
    """Shard count across the mounted databases.

    Kept for callers that only want the number; ``_substrate_coverage`` is the
    one to read when the number needs to be interpreted.
    """
    return _substrate_coverage()["shards"]


@app.get("/health")
def health(x_ngs_token: str = Header(None)):
    """Generic readiness when open; tenant-local substrate detail when authed."""
    deploy_sha = None
    try:
        with open(".deploy_sha", encoding="utf-8") as f:
            deploy_sha = f.read().strip() or None
    except OSError:
        pass

    node_token_ok = bool(NODE_TOKEN)
    registry_configured = tenants.tenants_file().exists()
    auth_configured = node_token_ok or registry_configured
    hud_auth_ok = bool(os.environ.get("NGS_HUD_USER") and os.environ.get("NGS_HUD_PASSWORD"))
    # On HF, enabling persistent storage mounts /data as its own filesystem;
    # without it /data is just a directory inside the ephemeral container.
    persistent = os.path.isdir("/data") and os.path.ismount("/data")

    warnings = []
    if not auth_configured:
        warnings.append("No node credentials configured: data API returns 503 (deny-by-default)")
    if not hud_auth_ok:
        warnings.append("NGS_HUD_USER/NGS_HUD_PASSWORD not set: HUD would be open to anyone on a public Space")
    if not persistent:
        warnings.append("persistent storage not detected: memories are wiped on every restart/deploy")
    if _serve_docs and _network_exposed:
        warnings.append(
            "NGS_DOCS_PUBLIC is set on a network-exposed host: /docs, /redoc and "
            "/openapi.json publish the full API map (incl. the /sync/pull export) "
            "to unauthenticated callers"
        )

    result = {
        "status": "ignited",
        "deploy_sha": deploy_sha,
        "storage": os.environ.get("NOUGEN_HOME", "default"),
        "persistent_storage": persistent,
        "node_token_configured": node_token_ok,
        "tenant_registry_configured": registry_configured,
        "hud_auth_configured": hud_auth_ok,
        "api_docs_public": _serve_docs and _network_exposed,
        "public_ready": auth_configured and hud_auth_ok,
        "warnings": warnings,
    }

    # The unauthenticated view intentionally performs no vault reads and does
    # not reveal shard counts, database names, or another tenant's path.
    if not x_ngs_token:
        return result

    tenant = verify_token(x_ngs_token)
    context_tokens = core.bind_active_vault(tenant.vault_dir, tenant.tenant_id)
    try:
        # Vault-keyed so the cache cannot hand one tenant another's coverage.
        coverage = _cached(f"substrate:{tenant.vault_dir}", _substrate_coverage)
    finally:
        core.reset_active_vault(context_tokens)
    result.update({
        "tenant_id": tenant.tenant_id,
        "total_shards": coverage["shards"],
        "substrate": coverage,
    })
    if not coverage["complete"] and not coverage["read_through"]:
        warnings.append(
            f"substrate incomplete: {coverage['databases_mounted']} of "
            f"{coverage['databases_expected']} databases mounted "
            f"(missing {coverage['databases_missing']}, "
            f"errored {[e['index'] for e in coverage['databases_errored']]}) - "
            "an empty recall result cannot be distinguished from an unread shard"
        )
    if not persistent and not coverage["read_through"]:
        warnings.append(
            "no read-through upstream configured on ephemeral storage: this node "
            "is the only home for what it holds, and holds it until the next deploy"
        )
    return result


# --- API models ---

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    # Inclusive ISO era bounds, same convention as _window_search/recall_window:
    # a bare "2026-03" is a whole month, "2026-03-14" a whole day.
    since: Optional[str] = None
    until: Optional[str] = None


class CaptureRequest(BaseModel):
    event_type: str = "KNOWLEDGE"
    title: str
    content: str
    tags: Optional[List[str]] = None
    original_timestamp: Optional[str] = None
    event_time_original: Optional[str] = None
    source_created_at: Optional[str] = None
    source_modified_at: Optional[str] = None
    captured_at: Optional[str] = None
    ai_first_touched_at: Optional[str] = None
    ai_last_touched_at: Optional[str] = None
    migrated_at: Optional[str] = None
    amended_at: Optional[List[str]] = None
    temporal_meta: Optional[dict] = None


class SyncPushRequest(BaseModel):
    shards: List[dict]


# Search-surface payload hygiene. Sync/replication paths must NOT use this:
# they move full-fidelity shards. Search callers get evidence, not archives -
# a 25k-char raw vault body at rank 1 (measured 2026-08-27) is context poison
# for every downstream agent. Caps resolve env-first; constants are fallbacks.
_SEARCH_MAX_CONTENT = int(os.environ.get("NOUGEN_SEARCH_MAX_CONTENT_CHARS", "2800"))
_SEARCH_MAX_FIELD = int(os.environ.get("NOUGEN_SEARCH_MAX_FIELD_CHARS", "400"))
_SEARCH_COMPACT = os.environ.get("NOUGEN_SEARCH_COMPACT", "1") != "0"
_HEAVY_KEY_RE = re.compile(r"embedding|_vector", re.I)
# Identity/provenance fields are never clamped: truncating an id or path breaks
# re-query-by-reference, which is the caller's only recourse after truncation.
_UNCAPPED_KEYS = frozenset({"id", "_db_index", "source", "timestamp", "event_type",
                            "file_path", "path", "shard_id", "db", "table"})
_CONTENT_KEYS = frozenset({"content", "text", "body"})


def _clamp(key: str, value):
    if not isinstance(value, str):
        return value
    cap = _SEARCH_MAX_CONTENT if key in _CONTENT_KEYS else _SEARCH_MAX_FIELD
    if key in _UNCAPPED_KEYS or len(value) <= cap:
        return value
    return value[:cap] + f"...[+{len(value) - cap} chars, requery by id for full body]"


def _json_safe(item: dict) -> dict:
    """Compact a shard row for a search surface: drop raw embedding bytes,
    embedding/vector columns, and nulls; clamp oversized text fields.
    NOUGEN_SEARCH_COMPACT=0 restores the legacy bytes-only filter."""
    if not _SEARCH_COMPACT:
        return {k: v for k, v in item.items() if not isinstance(v, (bytes, bytearray))}
    return {k: _clamp(k, v) for k, v in item.items()
            if v is not None
            and not isinstance(v, (bytes, bytearray))
            and not _HEAVY_KEY_RE.search(k)}


def _extract_effective_ts(row: dict) -> str:
    tm = row.get("temporal_meta")
    if isinstance(tm, dict) and tm.get("event_time_original"):
        return str(tm["event_time_original"])
    if isinstance(tm, str) and tm.strip():
        try:
            tmd = json.loads(tm)
            if isinstance(tmd, dict) and tmd.get("event_time_original"):
                return str(tmd["event_time_original"])
        except Exception:
            pass
    if row.get("event_time_original"):
        return str(row["event_time_original"])
    if row.get("original_timestamp"):
        return str(row["original_timestamp"])
    return str(row.get("effective_timestamp") or row.get("timestamp") or "")


def _in_era(row: dict, since: Optional[str], until: Optional[str]) -> bool:
    """Is this row provably inside the requested era?

    Same lexicographic ISO comparison _window_search does in SQL, with the same
    inclusive upper bound (pad with \\uffff so "2026-03" covers all of March).
    Resolves date bounds against COALESCE(temporal_meta.event_time_original, original_timestamp, timestamp).

    A row whose timestamp is missing or empty is NOT in the era. Federated
    vault lanes hand back rows with no timestamp at all, and those were the
    ones leaking: an undated memory cannot be shown as evidence of what a
    bounded question asked about. It is held back and counted, not silently
    mixed in with dated results.
    """
    ts = _extract_effective_ts(row)
    if not isinstance(ts, str) or not ts.strip():
        return False
    if since and ts < since:
        return False
    if until and ts > until + "\ufffd":
        return False
    return True


def _era_filter(rows: list, since: Optional[str], until: Optional[str]) -> tuple:
    """Split rows into (kept, held_back_count) against inclusive era bounds."""
    kept = [r for r in rows if _in_era(r, since, until)]
    return kept, len(rows) - len(kept)


def _row_key(row: dict):
    """Identity of a shard across arms: same shard from the SQL sweep and the
    federated sweep must merge, not double-count."""
    return (row.get("_db_index"), row.get("source"), row.get("id"))


def _merge_rows(*groups) -> list:
    """Union rows from several arms, first occurrence wins, newest first."""
    seen, merged = set(), []
    for group in groups:
        for row in group:
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
    merged.sort(key=lambda r: _extract_effective_ts(r), reverse=True)
    return merged


# Every data endpoint requires X-NGS-Token (verify_token 503s until
# NGS_NODE_TOKEN is configured, so the node is deny-by-default). This is what
# makes it safe to run the Space public: reads and writes are both gated;
# only /health and the separately-authed HUD are reachable without the token.

@app.post("/search")
def search(req: SearchRequest, response: Response,
           _tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Memory recall for cloud callers (mirrors the connector's POST /search).

    A crash in the full retrieval stack (vector lane, rerank, a bad shard row on
    this node's data) must not 500 the endpoint: federated callers treat any
    non-200 as "node down" and lose the relay entirely. So a failing full
    retrieve degrades to a keyword-only sweep, and a total failure returns an
    empty list rather than an exception.

    since/until bound the era. They are enforced on EVERY arm, not just the SQL
    sweep: federated vault lanes rank on content alone and were returning
    2026-08 rows (and undated rows) to callers asking about 2025-Q1 — the
    connector's ask_griot inherited that leak and reported held_back=0 while
    doing it. Bounded requests therefore also run the timestamp-filtered SQL
    sweep and union the two, so a sparse era still returns its own shards
    instead of losing them to a relevance cut computed over the whole grid.
    Rows dropped for falling outside (or having no) era are counted in the
    X-NouGen-Held-Back response header rather than vanishing unremarked.
    """
    limit = max(1, min(req.limit, 50))
    bounded = bool(req.since or req.until)
    # Over-fetch when bounded: filtering after ranking would otherwise starve
    # the result set down to a handful of in-era rows.
    fetch = min(limit * 5, 250) if bounded else limit
    sweep_report: dict = {}
    try:
        # Federated, not core.retrieve: a remote caller must see the same corpus a
        # local CLI caller does. core.retrieve reads only nougen_shards_1..9.db,
        # so registered sibling vaults (where most of the long-tail material
        # actually lives) were invisible over HTTP while `nougen recall` found
        # them locally — the node answered "not found" about content it holds.
        # federated_retrieve degrades every remote lane independently, so this
        # cannot fail worse than the local-only path did.
        results = federated_retrieve(req.query, limit=fetch, sweep_report=sweep_report)
    except Exception:
        logger.exception("search: full retrieve failed, falling back to keyword-only")
        try:
            results = core._keyword_retrieve(req.query, fetch, None, "*")
        except Exception:
            logger.exception("search: keyword fallback also failed; returning []")
            results = []

    if bounded:
        results, held_back = _era_filter(results, req.since, req.until)
        try:
            # SQL-side sweep: filters before scoring, so a quiet era keeps its
            # shards. Degrade to the filtered federated rows if it raises.
            results = _merge_rows(results,
                                  _window_search(req.query, req.since, req.until, limit))
        except Exception:
            logger.exception("search: windowed sweep failed; era-filtered results only")
        response.headers["X-NouGen-Held-Back"] = str(held_back)

    # Truncate to the caller's limit before the trailer: the over-fetch above is
    # an internal ranking budget, not a promise to return more rows.
    payload = [_json_safe(r) for r in results[:limit]]
    # Coverage honesty: a store that errored or timed out mid-sweep is a hole in
    # the corpus the caller must be able to see. Appended as a shard-shaped
    # trailer (score 0, distinct event_type) so list-consuming clients keep
    # parsing; absent entirely on a clean sweep, so the common path is unchanged.
    if sweep_report.get("errored"):
        payload.append({
            "id": "federation_meta",
            "event_type": "FEDERATION_STATUS",
            "title": (f"federation: {len(sweep_report['errored'])} store(s) "
                      "errored or timed out this sweep"),
            "content": json.dumps({
                "errored": sweep_report["errored"],
                "stores_swept": sweep_report.get("stores_swept"),
                "tier2": sweep_report.get("tier2"),
                "tier2_deferred": sweep_report.get("tier2_deferred"),
            }),
            "tags": json.dumps(["federation_status"]),
            "final_score": 0.0,
            "_db_index": "federation_meta",
        })
    return payload


@app.post("/capture")
def capture_shard(req: CaptureRequest,
                  _tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Single-shard capture for user agents."""
    ok = core.capture(req.event_type, req.title, req.content, tags=req.tags,
                      original_timestamp=req.original_timestamp,
                      event_time_original=req.event_time_original,
                      source_created_at=req.source_created_at,
                      source_modified_at=req.source_modified_at,
                      captured_at=req.captured_at,
                      ai_first_touched_at=req.ai_first_touched_at,
                      ai_last_touched_at=req.ai_last_touched_at,
                      migrated_at=req.migrated_at,
                      amended_at=req.amended_at,
                      temporal_meta=req.temporal_meta)
    return {"status": "ok", "captured": bool(ok)}


@app.post("/sync/push")
def sync_push(req: SyncPushRequest,
              _tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Bulk ingest (contract of connectors.cloud.push_to_cloud)."""
    from nougen_shards import private_vault

    count = 0
    skipped = 0
    for s in req.shards:
        title, content = s.get("title"), s.get("content")
        if not title or not content:
            skipped += 1
            continue
        sensitivity = s.get("sensitivity") or "normal"
        # /sync/pull transports encrypted-at-rest bodies as ngenc1 ciphertext.
        # Replicas share the lane data key, so unwrap before capture() hashes,
        # redacts, embeds and re-encrypts under the receiving machine's DPAPI
        # wrapper. Treating ciphertext as ordinary text silently declassifies it
        # and creates a duplicate whose hash no longer represents the plaintext.
        if private_vault.should_encrypt(sensitivity) and private_vault.is_encrypted(content):
            content = private_vault.decrypt_text(content)
        tags = s.get("tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except ValueError:
                tags = None
        emb = s.get("embedding")
        if emb is not None and not isinstance(emb, list):
            emb = None
        ok = core.capture(
            s.get("event_type") or "KNOWLEDGE", title, content,
            tags=tags, embedding=emb,
            domain_key=s.get("domain_key"),
            density_score=s.get("density_score"),
            sensitivity=sensitivity,
            original_timestamp=s.get("original_timestamp") or s.get("timestamp"),
            event_time_original=s.get("event_time_original"),
            source_created_at=s.get("source_created_at"),
            source_modified_at=s.get("source_modified_at"),
            captured_at=s.get("captured_at"),
            ai_first_touched_at=s.get("ai_first_touched_at"),
            ai_last_touched_at=s.get("ai_last_touched_at"),
            migrated_at=s.get("migrated_at"),
            amended_at=s.get("amended_at"),
            temporal_meta=s.get("temporal_meta"),
        )
        if ok:
            count += 1
        else:
            skipped += 1  # capture() dedups; an already-known shard is a skip
    return {"status": "ok", "count": count, "skipped": skipped}


@app.get("/sync/pull")
def sync_pull(_tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Full export (contract of connectors.cloud.pull_from_cloud)."""
    all_shards = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            for r in conn.execute("SELECT * FROM shards").fetchall():
                d = dict(r)
                emb = d.get("embedding")
                if emb:
                    try:
                        raw = emb.decode() if isinstance(emb, (bytes, bytearray)) else emb
                        d["embedding"] = json.loads(raw)
                    except (AttributeError, ValueError, TypeError, UnicodeDecodeError):
                        d["embedding"] = None
                all_shards.append(d)
        finally:
            conn.close()
    return all_shards


@app.get("/sync/hashes")
def sync_hashes(_tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Compact identity manifest for incremental replica synchronization."""
    hashes = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            hashes.extend(row[0] for row in conn.execute(
                "SELECT file_hash FROM shards WHERE file_hash IS NOT NULL"))
        finally:
            conn.close()
    return {"count": len(hashes), "hashes": hashes}


# --- Rhea-Noir resident agent ---
# NOTE: this block and rhea_noir.py must live in SOURCE, not only on the Space.
# The Space is rebuilt by a "Space deploy: snapshot of <sha>" job that restores
# from source, so anything applied only to the deployed artifact is deleted by
# the next rebuild. That is what removed this route on 2026-08-18.
import rhea_noir


class AgentRequest(BaseModel):
    prompt: str


@app.post("/agent")
def agent_ask(req: AgentRequest,
              _tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Ask Rhea-Noir. Free lane first; her reply names the brain that answered."""
    return rhea_noir.ask(req.prompt)


@node_mcp.tool()
def ask_rhea(prompt: str) -> dict:
    """Ask Rhea-Noir, the grid's resident agent. She recalls from the memory
    grid, gathers provenance-marked history, reads the tracker and relay, and
    captures shards worth keeping. Her reply names which brain answered."""
    return rhea_noir.ask(prompt)


# --- Dav1d Execution Layer ---
from nougen_shards.dav1d_executor import run_dav1d_agy


class Dav1dExecRequest(BaseModel):
    command: str = "agy"
    subcommand: Optional[str] = "mcp list"
    args: Optional[List[str]] = None
    prompt: Optional[str] = None
    timeout: int = 30


@app.post("/dav1d/exec")
def dav1d_exec_endpoint(
    req: Dav1dExecRequest,
    _tenant: tenants.Tenant = Depends(tenant_vault_context)
):
    """Execute bounded tooling on Dav1d. Returns structured runtime proof."""
    return run_dav1d_agy(
        command=req.command,
        args=req.args,
        subcommand=req.subcommand,
        prompt=req.prompt,
        timeout=req.timeout
    )


@app.post("/dav1d/agy")
def dav1d_agy_endpoint(
    req: Dav1dExecRequest,
    _tenant: tenants.Tenant = Depends(tenant_vault_context)
):
    """Invoke Google Antigravity CLI on Dav1d."""
    return run_dav1d_agy(
        command="agy",
        args=req.args,
        subcommand=req.subcommand,
        prompt=req.prompt,
        timeout=req.timeout
    )


@node_mcp.tool()
def dav1d_exec(
    command: str = "agy",
    subcommand: str = "mcp list",
    args: Optional[List[str]] = None,
    prompt: str = ""
) -> dict:
    """Dav1d Execution Layer: Execute bounded AGY CLI operations and toolchain actions
    on Dav1d. Griot reasons/retrieves; Dav1d executes.
    Returns verifiable runtime evidence (machine, host, engine, version, exit_code, output)."""
    return run_dav1d_agy(command=command, args=args, subcommand=subcommand, prompt=prompt)


@node_mcp.tool()
def dav1d_run(
    subcommand: str = "mcp list",
    prompt: Optional[str] = None
) -> dict:
    """Execute an allowlisted AGY CLI subcommand via the Dav1d execution bridge.
    Runs natively on the Blade Stadium with bounded proof and structured JSON return."""
    return run_dav1d_agy(subcommand=subcommand, prompt=prompt)


@node_mcp.tool()
def ask_dav1d(
    prompt: str,
    model: str = ""
) -> str:
    """Ask Dav1d, the autonomous execution and CLI triage agent on this machine."""
    from nougen_shards import agents
    return agents.run_agent("Dav1d", prompt, model=model or None)


@node_mcp.tool()
def ask_david(
    prompt: str,
    model: str = ""
) -> str:
    """Ask David / Dav1d, the autonomous execution and CLI triage agent on this machine."""
    from nougen_shards import agents
    return agents.run_agent("Dav1d", prompt, model=model or None)


@node_mcp.tool()
def agy_ask(
    prompt: str = "",
    subcommand: str = "mcp list",
    args: Optional[List[str]] = None
) -> dict:
    """Invoke the Google Antigravity CLI through Dav1d.

    The CLI version is not stated here; it is resolved from the binary at call time and
    returned in the `version` field of the result.
    Returns structured runtime proof from Dav1d."""
    return run_dav1d_agy(command="agy", args=args, subcommand=subcommand, prompt=prompt)


# --- Cortex HUD UI Logic ---

def get_substrate_map():
    """Generates a visual map of the 9-DB cluster."""
    active_idx = core.get_active_db_index()
    stats = []
    for i in range(1, 10):
        p = core.get_db_path(i)
        size = p.stat().st_size / (1024 * 1024) if p.exists() else 0
        shards_count = 0
        if p.exists():
            try:
                conn = core.get_connection(i)
                shards_count = conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
                conn.close()
            except Exception: pass
        
        status = "🟢 ACTIVE" if i == active_idx else "⚪ READY"
        if size > 900: status = "🔴 FULL"
        
        stats.append(f"### DB #{i} [{status}]\n- {shards_count} shards\n- {size:.2f} MB / 1024 MB")
    
    return stats

def run_recon():
    """Runs a brain scan and returns a summary for the UI."""
    candidates = scan_environment()
    high = [c for c in candidates if c.score_tier == "high"]
    tools = {}
    for c in candidates: tools[c.tool] = tools.get(c.tool, 0) + 1
    
    report = ["### Discovered Memory Sources"]
    for t, count in tools.items():
        if t != "unknown": report.append(f"- **.{t}**: {count} artifacts found")
    
    report.append(f"\n**Total potential shards**: {len(high) * 2}")
    return "\n".join(report)

def gr_search(query):
    results = core.retrieve(query, limit=5)
    if not results: return "No records found."
    
    output = []
    for r in results:
        sentiment = "🌟" if r['utility_score'] > 1.0 else "🌑"
        output.append(f"## {r['title']} {sentiment}\n**ID**: {r['id']} | **Score**: {r['final_score']:.2f}\n\n{r['content']}\n")
    return "\n---\n".join(output)

def get_analytics():
    engine = history.HistoryEngine()
    growth = engine.get_growth_rate("week")
    utility = engine.get_utility_delta("week")
    timeline = engine.get_timeline("week")
    
    stats = f"""
# 📈 Intelligence Growth
- **New Shards (Week)**: {growth['new_shards']}
- **Total Substrate Size**: {growth['total_shards']} shards
- **Usefulness Delta**: {'+' if utility >= 0 else ''}{utility:.2f}
"""
    return stats, timeline


def check_current_transcript():
    log_path = os.path.join(os.getcwd(), "transcript.log")
    if os.path.exists(log_path):
        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                # Read last 100 lines for preview
                lines = f.readlines()
                preview = "".join(lines[-100:])
        except Exception as e:
            preview = f"Error reading log preview: {e}"
        return f"🟢 Transcript exists.\n- **Size**: {size_mb:.2f} MB\n- **Log File**: `{log_path}`", log_path, preview
    return "⚪ No transcript generated yet. Click 'Generate Transcript' below.", None, ""


def generate_transcript():
    script_path = os.path.join(os.getcwd(), "tools", "read_vault_shards.py")
    res = subprocess.run([sys.executable, script_path, "--cluster"], capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 0:
        return check_current_transcript()
    else:
        err_msg = res.stderr or res.stdout or "Unknown execution error."
        return f"🔴 Generation failed:\n```\n{err_msg}\n```", None, ""


# --- The HUD Layout ---

with gr.Blocks(title="NouGenShards Cortex HUD", theme=gr.themes.Soft()) as cortex_hud:
    gr.Markdown("# 🪩 NouGenShards Cortex HUD")
    
    with gr.Tabs():
        with gr.Tab("🔍 Search"):
            search_input = gr.Textbox(label="Query the substrate", placeholder="What do I know about...")
            search_output = gr.Markdown()
            search_btn = gr.Button("Search Memory")
            search_btn.click(fn=gr_search, inputs=search_input, outputs=search_output)
            
        with gr.Tab("📈 History"):
            with gr.Row():
                with gr.Column():
                    stats_output = gr.Markdown()
                with gr.Column():
                    timeline_output = gr.Code(label="Growth Timeline (ASCII)")
            refresh_history = gr.Button("Refresh Analytics")
            refresh_history.click(fn=get_analytics, outputs=[stats_output, timeline_output])
            
        with gr.Tab("🗺️ Substrate"):
            gr.Markdown("## 9-Node SQLite Cluster")
            with gr.Row():
                maps = [gr.Markdown() for _ in range(9)]
            refresh_map = gr.Button("Refresh Substrate Map")
            for i in range(9):
                refresh_map.click(fn=lambda i=i: get_substrate_map()[i], outputs=maps[i])
                
        with gr.Tab("🧠 Recon"):
            recon_output = gr.Markdown("Click to scan local AI history.")
            recon_btn = gr.Button("Run Brain Scan")
            recon_btn.click(fn=run_recon, outputs=recon_output)

        with gr.Tab("📝 Transcript"):
            gr.Markdown("## 🗂️ Local Node Transcripter")
            status_md = gr.Markdown("Checking status...")
            download_file = gr.File(label="Download transcript.log")
            preview_box = gr.Textbox(label="Log Preview (Last 100 lines)", lines=15, interactive=False)
            generate_btn = gr.Button("Generate Transcript")
            
            generate_btn.click(
                fn=generate_transcript,
                inputs=[],
                outputs=[status_md, download_file, preview_box]
            )
            cortex_hud.load(
                fn=check_current_transcript,
                inputs=[],
                outputs=[status_md, download_file, preview_box]
            )


# The Cortex HUD exposes search, recon, substrate maps and full vault transcript
# dumps — none of it behind the write-token. When the node is reachable beyond
# loopback the UI MUST require a login: set NGS_HUD_USER / NGS_HUD_PASSWORD.
_hud_user = os.environ.get("NGS_HUD_USER")
_hud_pass = os.environ.get("NGS_HUD_PASSWORD")
_hud_auth = (_hud_user, _hud_pass) if _hud_user and _hud_pass else None


def _scope_base_url(scope) -> str:
    """Public origin for a raw ASGI scope, mirroring mcp_oauth.public_base_url.

    The 401 is emitted below the FastAPI layer, so there is no Request object
    to hand the shared helper; both paths must agree or the metadata URL in
    WWW-Authenticate points somewhere the client cannot reach.
    """
    configured = os.environ.get("NGS_PUBLIC_URL")
    if configured:
        return configured.rstrip("/")
    headers = {k.decode("latin-1").lower(): v.decode("latin-1")
               for k, v in scope.get("headers", [])}
    proto = headers.get("x-forwarded-proto") or scope.get("scheme") or "https"
    host = headers.get("x-forwarded-host") or headers.get("host") or ""
    return f"{proto}://{host}" if host else ""


class _TokenGatedMCP:
    """ASGI gate for the /mcp mount: same deny-by-default semantics as
    verify_token (503 unconfigured, 401 mismatch), but accepts the token as
    the X-NGS-Token header, an Authorization: Bearer header, or a ?token=
    query parameter - the Claude app's custom connectors cannot attach
    arbitrary headers, so the query form is the pre-baked-URL path while the
    OAuth flow issues tenant-bearing Bearer tokens. Credentials and the tenant
    registry are read at call time so tests and runtime configuration changes
    do not require re-importing the module."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            try:
                configured = tenants.credentials_configured(NODE_TOKEN)
            except tenants.TenantRegistryError:
                await self._reject(send, 503, "Tenant registry is invalid.")
                return
            if not configured:
                await self._reject(send, 503, "Node write-auth not configured.")
                return
            headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                       for k, v in scope.get("headers", [])}
            supplied = headers.get("x-ngs-token")
            if not supplied:
                # OAuth-issued tokens and the fleet Worker both arrive as
                # Bearer; without this branch they get a flat 401 and the
                # Connect flow completes only to fail on its first call.
                auth = headers.get("authorization", "")
                if auth[:7].lower() == "bearer ":
                    supplied = auth[7:].strip()
                elif auth:
                    supplied = auth.strip()
            if not supplied:
                supplied = (
                    headers.get("shard_gateway_token")
                    or headers.get("shard-gateway-token")
                    or headers.get("x-shard-gateway-token")
                )
            if not supplied:
                from urllib.parse import parse_qs
                qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
                supplied = (qs.get("token") or [None])[0]
            tenant = None
            if supplied:
                try:
                    tenant = tenants.resolve_token(supplied, NODE_TOKEN, core.GLOBAL_DIR)
                    if tenant is None:
                        issued_tenant_id = mcp_oauth.issued_token_tenant(supplied)
                        if issued_tenant_id:
                            tenant = tenants.tenant_by_id(issued_tenant_id, core.GLOBAL_DIR)
                except tenants.TenantRegistryError:
                    await self._reject(send, 503, "Tenant registry is invalid.")
                    return
            if tenant is None:
                await self._reject(send, 401, "Invalid node token.",
                                   scope=scope)
                return
            context_tokens = core.bind_active_vault(tenant.vault_dir, tenant.tenant_id)
            try:
                await self.inner(scope, receive, send)
            finally:
                core.reset_active_vault(context_tokens)
            return
        await self.inner(scope, receive, send)

    @staticmethod
    async def _reject(send, status, detail, scope=None):
        body = json.dumps({"detail": detail}).encode("utf-8")
        headers = [(b"content-type", b"application/json"),
                   (b"content-length", str(len(body)).encode())]
        if status == 401 and scope is not None:
            # RFC 9728 section 5.1. Without this pointer the client cannot
            # discover the authorization server, falls back to probing
            # /.well-known/oauth-authorization-server on its own, and reports
            # "couldn't register with the sign-in service" when that 404s.
            base = _scope_base_url(scope)
            headers.append((
                b"www-authenticate",
                f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource"'
                .encode("latin-1"),
            ))
        await send({"type": "http.response.start", "status": status,
                    "headers": headers})
        await send({"type": "http.response.body", "body": body})


# Register the OAuth endpoints BEFORE the Gradio catch-all at "/", or the HUD
# swallows /authorize, /token, /register and the discovery documents.
def _lanes_for_google_email(email: str) -> list:
    """Lanes a verified Google account may grant: owner-listed accounts may
    grant any lane (owner included); otherwise only tenants whose registry
    record names this exact email. Owner emails come from the environment so
    no account ever appears in shipped code."""
    email = (email or "").strip().casefold()
    if not email:
        return []
    owner_emails = {
        e.strip().casefold()
        for e in os.environ.get("NOUGEN_GOOGLE_OWNER_EMAILS", "").split(",")
        if e.strip()
    }
    try:
        records = tenants.load_registry()
    except tenants.TenantRegistryError:
        logger.error("tenant registry rejected during Google lane resolution")
        return []
    if email in owner_emails:
        return ([(tenants.OWNER_TENANT_ID, "Owner")]
                + [(r.tenant_id, r.label) for r in records])
    return [(r.tenant_id, r.label) for r in records if r.google_email == email]


mcp_oauth.install(
    app,
    node_token_getter=lambda: NODE_TOKEN,
    tenant_resolver=lambda token: (
        resolved.tenant_id if (resolved := _resolve_tenant_credential(token)) else None
    ),
    credentials_configured_getter=_credentials_configured,
    lanes_for_email=_lanes_for_google_email,
)

# Mount BEFORE the Gradio catch-all at "/" so /mcp is routed to the MCP app.
app.mount("/mcp", _TokenGatedMCP(_mcp_asgi))
# _on_platform / _bind_host / _network_exposed are resolved once at import time,
# up beside the FastAPI() constructor - the docs guard needs them before `app`
# exists, and one probe keeps both guards agreeing on what "exposed" means.

# Fail closed on the HUD WITHOUT taking the process down. On a network-reachable
# host with no HUD credentials, skip mounting the unauthenticated vault UI (search
# / recon / transcript dumps) but keep the FastAPI app serving — the token-gated
# /mcp endpoint and REST API stay up. Raising here would abort `uvicorn app:app`
# and take /mcp down along with the HUD.
if _hud_auth or not _network_exposed:
    app = gr.mount_gradio_app(app, cortex_hud, path="/", auth=_hud_auth)
else:
    print(
        "[WARN] Cortex HUD not mounted: host is network-exposed "
        f"(bind={_bind_host}, managed_platform={_on_platform}) and "
        "NGS_HUD_USER/NGS_HUD_PASSWORD are unset. "
        "The /mcp endpoint and REST API remain available; set both env vars to "
        "serve the vault UI.",
        file=sys.stderr,
    )

if __name__ == "__main__":
    import uvicorn
    # Host/auth already validated at import (fail-closed guard above): by here we
    # are either on loopback or have HUD auth configured.
    port = int(os.environ.get("NGS_PORT", "4444"))
    uvicorn.run(app, host=_bind_host, port=port)
