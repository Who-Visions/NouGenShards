"""
NouGenShards Production Node & Cortex HUD.
Architecture: FastAPI + Persistent Storage (/data) + Token Auth + Multi-tab Gradio UI.
"""
import os
import sys
import json
import logging
import hashlib
import sqlite3
import datetime
import contextlib
from typing import List, Optional

logger = logging.getLogger(__name__)
from fastapi import FastAPI, Header, HTTPException, Depends, Response, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import gradio as gr
import subprocess


# Add src to path for absolute imports
sys.path.append(os.path.join(os.getcwd(), 'src'))

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
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

# mcp 2.x renamed FastMCP to MCPServer and moved the HTTP transport options
# (stateless_http, json_response, streamable_http_path, transport_security)
# off the constructor and onto streamable_http_app() - they are passed at the
# _mcp_asgi call below, not here.
node_mcp = MCPServer(
    "NouGenShards",
    instructions=(
        "Persistent memory node. Use recall_memory before reasoning from "
        "scratch and capture_experience to store durable learnings."
    ),
)


@node_mcp.tool()
def recall_memory(query: str, limit: int = 5) -> list:
    """Search the memory substrate. Returns ranked shards (fuzzy recall
    included when exact matching misses). Long shard bodies are returned as
    SNIPPETS with a truncation marker naming get_shard(shard_id, db_index) -
    call that for a full body. Held context is what recall costs a caller
    (98%+ of fleet spend is cache re-read, ~1.5% is output), so the default
    injects handles-plus-snippets, not full documents."""
    # Federated for the same reason as POST /search below: a remote MCP client
    # should not get a narrower corpus than the local CLI.
    results = federated_retrieve(query, limit=max(1, min(limit, 20)))
    return [_slim_shard(r) for r in results]


def _recall_snippet_chars() -> int:
    """Snippet budget per recalled shard body. Env-first; 0 disables slimming."""
    raw = os.environ.get("NOUGEN_RECALL_SNIPPET_CHARS", "")
    try:
        n = int(raw) if raw.strip() else 700
    except ValueError:
        logger.warning("NOUGEN_RECALL_SNIPPET_CHARS=%r invalid; using 700", raw)
        n = 700
    return max(0, n)


def _slim_shard(r: dict) -> dict:
    """Strip bytes fields and truncate long bodies to a snippet + fetch handle.

    Every character recall injects is held and re-read by the caller for the
    rest of its session - measured fleet-wide at ~66x the cost of the same
    character as output. Recall therefore ships a snippet with an explicit
    pointer to get_shard for the full body, instead of the whole document.
    """
    out = {k: v for k, v in r.items() if not isinstance(v, (bytes, bytearray))}
    budget = _recall_snippet_chars()
    body = out.get("content")
    if budget and isinstance(body, str) and len(body) > budget:
        clipped = body[:budget].rsplit(" ", 1)[0] if " " in body[:budget] else body[:budget]
        out["content"] = (
            f"{clipped} ... [snippet: {len(body) - len(clipped)} more chars in the "
            f"full shard - get_shard(shard_id={out.get('id', '?')}, "
            f"db_index={out.get('_db_index', '?')})]"
        )
        out["content_truncated"] = True
        out["content_full_chars"] = len(body)
    return out


@node_mcp.tool()
def get_shard(shard_id: int, db_index: int | None = None) -> dict:
    """Fetch ONE shard's full body by id - the on-demand counterpart to
    recall_memory's snippets. Pass the db_index a recall result carried
    (_db_index); omit it to search all grid databases for the id."""
    indexes = [db_index] if db_index else list(range(1, core.MAX_DB_COUNT + 1))
    for i in indexes:
        if not core.get_db_path(i).exists():
            continue
        conn = None
        try:
            conn = core.get_connection(i)
            row = conn.execute(
                "SELECT * FROM shards WHERE id = ?", (shard_id,)).fetchone()
            if row is None:
                continue
            item = core.hydrate(dict(row))
            item["_db_index"] = i
            return {k: v for k, v in item.items()
                    if not isinstance(v, (bytes, bytearray))}
        except Exception as exc:  # sqlite3.DatabaseError et al - one bad DB must not kill the lookup
            logger.error("get_shard: DB %s unreadable, skipping: %s: %s",
                         i, type(exc).__name__, exc)
            continue
        finally:
            if conn is not None:
                conn.close()
    return {"found": False, "shard_id": shard_id,
            "searched": indexes,
            "hint": "id not present (or its DB is unreadable); ids are per-DB - "
                    "pass the _db_index from the recall result"}


@node_mcp.tool()
def capture_experience(title: str, content: str, event_type: str = "KNOWLEDGE",
                       tags: list[str] | None = None,
                       original_timestamp: str | None = None) -> dict:
    """Store a unit of experience as a shard (deduplicated by content).

    `original_timestamp` (ISO-8601) stamps migrated content at its true era
    instead of capture time; invalid values fall back to now.

    The answer is always branchable: `captured` true/false, plus `shard_id` and
    `db_index` when a row was written, or `reason`/`error` when none was. A
    genuine write fault is not reported here at all - it raises, and the client
    sees a tool error rather than a quiet false."""
    result = core.capture(event_type, title, content, tags=tags,
                          original_timestamp=original_timestamp)
    return dict(result)


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
    grid. Timestamps are ISO-8601 (2026-08-09T15:27:40.728875Z), which sorts
    and compares lexicographically -- so a bare date like "2026-03" or
    "2026-03-14" works as a bound with no parsing.
    """
    where, params = [], []
    if since:
        where.append("timestamp >= ?")
        params.append(since)
    if until:
        # Inclusive: "2026-03" should cover all of March, and "2026-03-14"
        # the whole day, so pad the bound to the end of whatever precision
        # the caller gave rather than cutting at midnight.
        params.append(until + "￿")
        where.append("timestamp <= ?")

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
            if q:
                # Trigram FTS: match on the phrase, quoted so punctuation in the
                # query cannot be read as FTS operator syntax.
                clauses.append("id IN (SELECT rowid FROM shards_fts WHERE shards_fts MATCH ?)")
                args.append('"' + q.replace('"', '""') + '"')
            sql = ("SELECT id, timestamp, event_type, title, content, tags, utility_score "
                   "FROM shards")
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY timestamp DESC LIMIT ?"
            args.append(limit)
            for r in conn.execute(sql, args):
                rows.append({"id": r[0], "timestamp": r[1], "event_type": r[2],
                             "title": r[3], "content": r[4], "tags": r[5],
                             "utility_score": r[6], "_db_index": i})
        except Exception:
            # A malformed FTS query or a bad shard row on one DB must not sink
            # the whole sweep -- the other eight still have answers.
            continue
        finally:
            conn.close()

    rows.sort(key=lambda x: x["timestamp"], reverse=True)
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
            for (ts,) in conn.execute("SELECT timestamp FROM shards WHERE timestamp IS NOT NULL"):
                ts = str(ts)
                per_month[ts[:7]] += 1
                total += 1
                if lo is None or ts < lo:
                    lo = ts
                if hi is None or ts > hi:
                    hi = ts
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
    return {"total_shards": total,
            "span": {"earliest": lo, "latest": hi},
            "months": dict(sorted(per_month.items())),
            "empty_months": gaps,
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


_mcp_asgi = node_mcp.streamable_http_app(
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
    # Heal the grid before anything scans it: malformed DB files are renamed
    # aside (kept for forensics) and recreated empty, so healthy indices and
    # their rows survive instead of a whole-volume wipe. Gated by
    # NOUGEN_QUARANTINE_MALFORMED_ON_BOOT; see core.quarantine_malformed_dbs.
    for q in core.quarantine_malformed_dbs():
        logger.warning("boot quarantine: grid DB %(index)s -> %(moved_to)s "
                       "(%(reason)s)", q)
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
try:
    from space_router import router as _inference_router
    app.include_router(_inference_router)
except Exception as _router_err:
    print(f"[WARN] Inference router not mounted: {_router_err}", file=sys.stderr)
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


def _verify_token_sync(
    x_ngs_token: Optional[str] = None,
    authorization: Optional[str] = None,
    shard_gateway_token: Optional[str] = None,
    shard_gateway_token_dash: Optional[str] = None,
    x_shard_gateway_token: Optional[str] = None,
    token: Optional[str] = None,
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


async def verify_token(
    x_ngs_token: Optional[str] = Header(None, alias="X-NGS-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    shard_gateway_token: Optional[str] = Header(None, alias="Shard_Gateway_Token"),
    shard_gateway_token_dash: Optional[str] = Header(None, alias="Shard-Gateway-Token"),
    x_shard_gateway_token: Optional[str] = Header(None, alias="X-Shard-Gateway-Token"),
    token: Optional[str] = Query(None),
) -> tenants.Tenant:
    """Async so auth never queues behind the shared sync-endpoint threadpool
    (registry read + sha256 are cheap enough for the event loop)."""
    return _verify_token_sync(x_ngs_token, authorization, shard_gateway_token,
                              shard_gateway_token_dash, x_shard_gateway_token, token)


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

    # recall_trustworthy used to be `complete or bool(upstreams)`, which called
    # recall trustworthy while a database was CORRUPT - the single most
    # dangerous answer in this stack, because this tool's own description tells
    # callers to check it "before concluding a recall miss means the memory does
    # not exist". On 2026-08-29 it answered true with index 5 malformed and both
    # ranked read paths returning zero rows, so anyone who did the responsible
    # thing and checked coverage first was told to conclude data loss.
    #
    # An errored database is a fault, never a thin-cache-in-front-of-an-upstream
    # situation: its rows are dark and no upstream flag changes that. And the
    # upstream escape hatch itself was resting on an unchecked premise - this
    # function never probes whether the upstream ANSWERS. The one configured
    # that day was returning 530. So say which case it is instead of collapsing
    # all of them into one boolean.
    if errored:
        trustworthy = False
        reason = ("databases_errored is non-empty: those shards are unreadable, "
                  "so a recall miss cannot distinguish absent from unreadable")
    elif complete:
        trustworthy = True
        reason = "every expected database is mounted and readable"
    elif upstreams:
        trustworthy = True
        reason = ("local grid is incomplete but read-through is configured; "
                  "NOTE this does not verify the upstream actually answers")
    else:
        trustworthy = False
        reason = "local grid is incomplete and no read-through upstream is configured"

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
        # grid is expected rather than a fault. A corrupt database is neither:
        # see the block above.
        "recall_trustworthy": trustworthy,
        "recall_trustworthy_reason": reason,
        "detail": mounted,
    }


def _total_shards() -> int:
    """Shard count across the mounted databases.

    Kept for callers that only want the number; ``_substrate_coverage`` is the
    one to read when the number needs to be interpreted.
    """
    return _substrate_coverage()["shards"]


@app.get("/health")
async def health(x_ngs_token: str = Header(None)):
    """Generic readiness when open; tenant-local substrate detail when authed.

    async def on purpose (2026-09-01). Every heavy endpoint here (/search,
    /sync/*, /agent, /dav1d/*) is sync-def, so they all dispatch through the
    same default anyio threadpool (~40 threads). A handful of wedged /agent
    or slow federated /search calls exhausts it, and a sync-def /health then
    QUEUES behind them -- observed at the shards.nougenai.com front door as
    /health hanging 30-120s with zero bytes while unknown paths 404ed
    instantly (routing never touches the pool). The unauthenticated probe is
    pure cheap local reads, so it now runs on the event loop and always
    answers; only the authed, vault-touching tail goes to the pool, where it
    may honestly wait its turn.
    """
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
    return await run_in_threadpool(
        _health_authed, result, warnings, persistent, x_ngs_token)


def _health_authed(result: dict, warnings: list, persistent: bool,
                   x_ngs_token: str) -> dict:
    """Vault-touching half of /health; runs in the threadpool by design.

    `warnings` is the same list `result["warnings"]` points at, so appends
    here still land in the response -- same aliasing the inline code relied on.
    """
    tenant = _verify_token_sync(x_ngs_token)
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


class SyncPushRequest(BaseModel):
    shards: List[dict]


def _json_safe(item: dict) -> dict:
    """Drop non-JSON-serializable fields (raw embedding bytes) from a shard row."""
    return {k: v for k, v in item.items() if not isinstance(v, (bytes, bytearray))}


def _in_era(row: dict, since: Optional[str], until: Optional[str]) -> bool:
    """Is this row provably inside the requested era?

    Same lexicographic ISO comparison _window_search does in SQL, with the same
    inclusive upper bound (pad with \\uffff so "2026-03" covers all of March).

    A row whose timestamp is missing or empty is NOT in the era. Federated
    vault lanes hand back rows with no timestamp at all, and those were the
    ones leaking: an undated memory cannot be shown as evidence of what a
    bounded question asked about. It is held back and counted, not silently
    mixed in with dated results.
    """
    ts = row.get("timestamp") or ""
    if not isinstance(ts, str) or not ts.strip():
        return False
    if since and ts < since:
        return False
    if until and ts > until + "￿":
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
    merged.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
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
    """Single-shard capture for user agents.

    `status` stays "ok" for the HTTP contract; whether a shard was actually
    written is `captured`, with `shard_id` when it was and `error` when it was
    not - a caller must never have to guess which of the two happened.
    """
    result = core.capture(req.event_type, req.title, req.content, tags=req.tags,
                          original_timestamp=req.original_timestamp)
    return {"status": "ok", **dict(result)}


@app.post("/sync/push")
def sync_push(req: SyncPushRequest,
              _tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Bulk ingest (contract of connectors.cloud.push_to_cloud)."""
    from nougen_shards import private_vault

    count = 0
    skipped = 0
    errored = 0
    for s in req.shards:
        # The ENTIRE per-shard body sits in one guard: decrypt, tag parsing,
        # AND capture. This is the second time this protection ships - #148
        # added a capture-only guard that a later merge silently dropped, and
        # the regression resurfaced 2026-08-31 as deterministic 500 cascades
        # on /sync/push (a row whose ngenc1 body fails cross-machine decrypt
        # raises BEFORE capture, killing the whole 100-row batch, three
        # retries each). One bad row is one `errored` tick, never a 500.
        try:
            title, content = s.get("title"), s.get("content")
            if not title or not content:
                skipped += 1
                continue
            sensitivity = s.get("sensitivity") or "normal"
            # /sync/pull transports encrypted-at-rest bodies as ngenc1
            # ciphertext. Replicas share the lane data key, so unwrap before
            # capture() hashes, redacts, embeds and re-encrypts under the
            # receiving machine's DPAPI wrapper. Treating ciphertext as
            # ordinary text silently declassifies it and creates a duplicate
            # whose hash no longer represents the plaintext.
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
                # Bulk ingest must stamp a shard at its TRUE era, exactly as
                # /capture does. Dropping this silently re-dated every pushed
                # shard to ingest time -- and because capture() dedups on a
                # content hash, a re-push with the right date is a no-op, so
                # the original era was unrecoverable. `timestamp` is the
                # fallback because /sync/pull exports rows under that key,
                # which makes pull -> push round-trip era-preserving instead
                # of flattening history to the migration date.
                original_timestamp=s.get("original_timestamp") or s.get("timestamp"),
            )
        except Exception as exc:  # pylint: disable=broad-except
            errored += 1
            logger.error("sync_push: shard %r failed: %s: %s",
                         (s.get("title") or "")[:80], type(exc).__name__, exc)
            continue
        if ok:
            count += 1
        else:
            skipped += 1  # capture() dedups; an already-known shard is a skip
    return {"status": "ok", "count": count, "skipped": skipped, "errored": errored}


@app.get("/sync/pull")
def sync_pull(response: Response,
              _tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Full export (contract of connectors.cloud.pull_from_cloud).

    One malformed grid DB must not 500 the whole export: the corruption that
    makes an index unreadable is precisely when a puller needs everything the
    OTHER indices still hold. The response stays a bare list (pull_from_cloud's
    contract); degraded state is surfaced in the X-NGS-Degraded-DBs header and
    the DB_DEGRADED history event, mirroring core's per-DB scan guard.
    """
    all_shards = []
    degraded = []
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
        except (sqlite3.DatabaseError, OSError) as exc:
            degraded.append(i)
            logger.error("grid DB %s unreadable during sync/pull, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            with contextlib.suppress(Exception):
                history.log_event(0, i, "DB_DEGRADED",
                                  metadata={"error": f"{type(exc).__name__}: {exc}",
                                            "route": "/sync/pull"})
        finally:
            conn.close()
    if degraded:
        response.headers["X-NGS-Degraded-DBs"] = ",".join(str(i) for i in degraded)
    return all_shards


@app.get("/sync/hashes")
def sync_hashes(_tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Compact identity manifest for incremental replica synchronization.

    Guarded per DB like /sync/pull: a malformed index is reported in
    databases_skipped (additive field) instead of failing the manifest.
    """
    hashes = []
    degraded = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            hashes.extend(row[0] for row in conn.execute(
                "SELECT file_hash FROM shards WHERE file_hash IS NOT NULL"))
        except (sqlite3.DatabaseError, OSError) as exc:
            degraded.append(i)
            logger.error("grid DB %s unreadable during sync/hashes, skipping it: %s: %s",
                         i, type(exc).__name__, exc)
            with contextlib.suppress(Exception):
                history.log_event(0, i, "DB_DEGRADED",
                                  metadata={"error": f"{type(exc).__name__}: {exc}",
                                            "route": "/sync/hashes"})
        finally:
            conn.close()
    return {"count": len(hashes), "hashes": hashes, "databases_skipped": degraded}


# --- Rhea-Noir resident agent ---
# NOTE: this block and rhea_noir.py must live in SOURCE, not only on the Space.
# The Space is rebuilt by a "Space deploy: snapshot of <sha>" job that restores
# from source, so anything applied only to the deployed artifact is deleted by
# the next rebuild. That is what removed this route on 2026-08-18.
import rhea_noir

# Rhea gets her own worker pool: sync endpoints share the framework's default
# threadpool, and threads stuck scanning an unhealthy grid volume exhaust it,
# starving /agent before ask() even starts (observed 2026-09-01: /health in
# 0.2s while a no-tool /agent hung 120s). The hard cap answers inside the
# ~100s edge cut with a diagnosable error instead of an opaque 524.
import asyncio
import concurrent.futures
import contextvars

_RHEA_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.environ.get("NOUGEN_RHEA_WORKERS", "4")),
    thread_name_prefix="rhea")
_RHEA_HARD_CAP_S = float(os.environ.get("NOUGEN_RHEA_HARD_CAP_S", "92"))


class AgentRequest(BaseModel):
    prompt: str


async def _ask_rhea_bounded(prompt: str) -> dict:
    loop = asyncio.get_running_loop()
    # The tenant's vault binding lives in ContextVars on this request's task;
    # a bare executor thread would silently run Rhea in the owner vault.
    ctx = contextvars.copy_context()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_RHEA_POOL, ctx.run, rhea_noir.ask, prompt),
            timeout=_RHEA_HARD_CAP_S)
    except asyncio.TimeoutError:
        return {"answer": "(rhea hard cap hit - the node is overloaded, "
                          "likely stuck grid-volume scans; retry after a "
                          "restart or ask without grid tools)",
                "brain": "none", "tools_used": [], "error": "hard_cap"}


@app.post("/agent")
async def agent_ask(req: AgentRequest,
                    _tenant: tenants.Tenant = Depends(tenant_vault_context)):
    """Ask Rhea-Noir. Free lane first; her reply names the brain that answered."""
    return await _ask_rhea_bounded(req.prompt)


@node_mcp.tool()
async def ask_rhea(prompt: str) -> dict:
    """Ask Rhea-Noir, the grid's resident agent. She recalls from the memory
    grid, gathers provenance-marked history, reads the tracker and relay, and
    captures shards worth keeping. Her reply names which brain answered."""
    return await _ask_rhea_bounded(prompt)


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
def agy_ask(
    prompt: str = "",
    subcommand: str = "mcp list",
    args: Optional[List[str]] = None
) -> dict:
    """Invoke the Google Antigravity CLI through Dav1d.
    Returns structured runtime proof from Dav1d."""
    return run_dav1d_agy(command="agy", args=args, subcommand=subcommand, prompt=prompt)


@node_mcp.tool()
def ask_dav1d(
    prompt: str,
    subcommand: str = "mcp list",
    args: Optional[List[str]] = None
) -> dict:
    """Canonical Dav1d connector alias.

    The fleet connector calls this name. Keep it on the same bounded executor
    as ``agy_ask`` so the remote surface cannot silently fall back to a
    simulated response or gain a second, less-safe execution path.
    """
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
mcp_oauth.install(
    app,
    node_token_getter=lambda: NODE_TOKEN,
    tenant_resolver=lambda token: (
        resolved.tenant_id if (resolved := _resolve_tenant_credential(token)) else None
    ),
    credentials_configured_getter=_credentials_configured,
)

# Mount BEFORE the Gradio catch-all at "/" so /mcp is routed to the MCP app.
class _McpSlashNormalizer:
    """Serve `/mcp` exactly like `/mcp/`.

    `/mcp` is the documented public front door - a healthy node answers GET
    with 405, never 404. But Starlette's Mount hands the inner ASGI app an
    EMPTY path for the bare mount point, every inner route misses it, and the
    door reports 404 while `/mcp/` serves fine in the same process. Clients
    that omit the trailing slash were being told the front door does not
    exist (2026-09-01 retrieval incident). Rewriting the path BEFORE routing
    fixes it for the mount, the token gate, and the inner app at once;
    normalizing inside the gate cannot work, because routing 404s first.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


app.mount("/mcp", _TokenGatedMCP(_mcp_asgi))
# Added as middleware, not as a wrapper around `app`: the middleware stack runs
# ahead of the router (which is what 404s the bare path) while `app` stays a
# FastAPI instance for every route registered after this line.
app.add_middleware(_McpSlashNormalizer)
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
