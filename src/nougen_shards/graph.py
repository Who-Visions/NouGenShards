"""
Graph Memory: link shards (fixes, files, commands, decisions) into a latent mesh.

Edges live in a dedicated graph.db inside the request-local active vault, so a
fix can point at the file it touched, a command at the
decision that prompted it, and recall can walk those links.

Nodes are identified by file_hash, not by the per-DB autoincrement `id`: the
9-DB cluster gives each database its own id sequence, so id alone is not unique
across the mesh, but file_hash is (capture() dedups globally before writing).
The public API still takes shard ids for ergonomics, with a db_index to say
which database the id lives in (default 1, the common single-DB case; recall
results carry it as `_db_index`).
"""
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Optional

from . import core



def get_graph_db_path():
    """Path to the graph edge store (alongside the shard cluster in the vault)."""
    vault = core.active_vault_dir()
    vault.mkdir(parents=True, exist_ok=True, mode=0o700)
    return vault / "graph.db"


def get_graph_connection():
    """SQLite connection to the graph store, WAL-enabled (Module 19)."""
    conn = sqlite3.connect(str(get_graph_db_path()), timeout=core.sqlite_timeout_s())
    mode = core.get_vault_journal_mode()
    conn.execute(f"PRAGMA journal_mode={mode};")
    conn.row_factory = sqlite3.Row
    return conn


def init_graph_db():
    """Initialize the shard_edges table and lookup indexes."""
    conn = get_graph_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shard_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src_hash TEXT NOT NULL,
            dst_hash TEXT NOT NULL,
            relation TEXT NOT NULL DEFAULT 'relates',
            created_at TEXT NOT NULL,
            UNIQUE(src_hash, dst_hash, relation)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON shard_edges(src_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON shard_edges(dst_hash)")
    conn.commit()
    conn.close()


def _hash_for(shard_id: int, db_index: int) -> Optional[str]:
    """Resolve (id, db_index) -> file_hash, the global node identity."""
    shard = core.get_shard_by_id(shard_id, db_index)
    return shard["file_hash"] if shard else None


def _shard_for_hash(file_hash: str) -> Optional[Dict]:
    """Resolve a file_hash back to its shard dict by scanning the cluster."""
    return _shards_for_hashes([file_hash]).get(file_hash)


def _shards_for_hashes(file_hashes: List[str]) -> Dict[str, Dict]:
    """Resolve many file_hashes to shard dicts with one query per DB (lowest db_index wins).

    Avoids the per-hash cluster rescan: a single pass over the (up to) 9 DBs
    resolves every requested hash, so callers pay at most one connection per DB
    instead of one per (hash, DB) pair.
    """
    remaining = list(dict.fromkeys(file_hashes))  # de-dup, preserve order
    resolved: Dict[str, Dict] = {}
    for i in range(1, core.MAX_DB_COUNT + 1):
        if not remaining:
            break
        if not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            placeholders = ",".join("?" * len(remaining))
            rows = conn.execute(
                f"SELECT * FROM shards WHERE file_hash IN ({placeholders})", remaining
            ).fetchall()
            for row in rows:
                item = dict(row)
                fhash = item["file_hash"]
                if fhash not in resolved:  # first (lowest-index) DB wins
                    item["_db_index"] = i
                    resolved[fhash] = item
            remaining = [h for h in remaining if h not in resolved]
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
    return resolved


def link_shards(src_id: int, dst_id: int, relation: str = "relates",
                src_db: int = 1, dst_db: int = 1, bidirectional: bool = False) -> bool:
    """
    Create an edge src -> dst labelled `relation` (e.g. 'fixes', 'touches',
    'caused_by', 'relates'). Both shards must exist. Idempotent on
    (src_hash, dst_hash, relation). bidirectional=True also stores dst -> src.
    Returns True if at least one new edge was written.
    """
    src_hash = _hash_for(src_id, src_db)
    dst_hash = _hash_for(dst_id, dst_db)
    if not src_hash or not dst_hash or src_hash == dst_hash:
        return False

    init_graph_db()
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    conn = get_graph_connection()
    try:
        written = conn.execute(
            "INSERT OR IGNORE INTO shard_edges (src_hash, dst_hash, relation, created_at) "
            "VALUES (?, ?, ?, ?)", (src_hash, dst_hash, relation, timestamp)).rowcount
        if bidirectional:
            written += conn.execute(
                "INSERT OR IGNORE INTO shard_edges (src_hash, dst_hash, relation, created_at) "
                "VALUES (?, ?, ?, ?)", (dst_hash, src_hash, relation, timestamp)).rowcount
        conn.commit()
        return written > 0
    finally:
        conn.close()


def related_shards(shard_id: int, db_index: int = 1, relation: Optional[str] = None,
                   limit: int = 10) -> List[Dict]:
    """
    Return shards connected to (shard_id, db_index) — undirected: follows edges in
    either direction — optionally filtered to a single relation. Each result is the
    neighbour shard dict enriched with 'relation' and 'direction' ('out'/'in').
    """
    node_hash = _hash_for(shard_id, db_index)
    if not node_hash or not get_graph_db_path().exists():
        return []

    conn = get_graph_connection()
    try:
        rel_sql = " AND relation = ?" if relation else ""
        out_params: list = [node_hash] + ([relation] if relation else [])
        out_rows = conn.execute(
            f"SELECT dst_hash AS nhash, relation FROM shard_edges WHERE src_hash = ?{rel_sql}",
            out_params).fetchall()
        in_params: list = [node_hash] + ([relation] if relation else [])
        in_rows = conn.execute(
            f"SELECT src_hash AS nhash, relation FROM shard_edges WHERE dst_hash = ?{rel_sql}",
            in_params).fetchall()
    finally:
        conn.close()

    ordered = [(r, "out") for r in out_rows] + [(r, "in") for r in in_rows]
    hash_map = _shards_for_hashes([row["nhash"] for row, _ in ordered])

    neighbours: List[Dict] = []
    seen = set()
    for row, direction in ordered:
        key = (row["nhash"], row["relation"], direction)
        if key in seen:
            continue
        seen.add(key)
        shard = hash_map.get(row["nhash"])
        if shard:
            shard = dict(shard)  # copy: same hash may recur with a different relation/direction
            shard["relation"] = row["relation"]
            shard["direction"] = direction
            neighbours.append(shard)
        if len(neighbours) >= limit:
            break
    return neighbours


def dependency_shards(shard_id: int, db_index: int, limit: int = 21) -> List[Dict]:
    """Read outgoing depends_on edges, preserving unresolved prerequisites.

    Unlike related_shards, incoming edges never consume the dependency budget.
    One overflow entry lets the caller reject a closure exceeding its ceiling.
    """
    node_hash = _hash_for(shard_id, db_index)
    if not node_hash or not get_graph_db_path().exists():
        return []
    conn = get_graph_connection()
    try:
        rows = conn.execute(
            "SELECT dst_hash FROM shard_edges WHERE src_hash = ? AND relation = ? "
            "ORDER BY dst_hash LIMIT ?", (node_hash, "depends_on", limit)).fetchall()
    finally:
        conn.close()
    hashes = [row['dst_hash'] for row in rows]
    resolved = _shards_for_hashes(hashes)
    return [dict(resolved[h]) if h in resolved else
            {"id": "unresolved:" + h, "_db_index": db_index, "unresolved": True}
            for h in hashes]


def edge_count() -> int:
    """Total number of edges in the mesh (0 if the graph store is absent)."""
    if not get_graph_db_path().exists():
        return 0
    conn = get_graph_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM shard_edges").fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def get_node_centrality(file_hash: str) -> int:
    """Returns the total number of connections (degree centrality) for a given node hash."""
    if not get_graph_db_path().exists():
        return 0
    conn = get_graph_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM shard_edges WHERE src_hash = ? OR dst_hash = ?",
            (file_hash, file_hash)
        ).fetchone()
        return row[0] if row else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def shard_bundle(seeds: List[tuple], depth: int = 1, token_budget: int = 4000,
                 per_node_links: int = 8) -> Dict:
    """Read-only constellation: seed shards plus their linked neighbourhood, rendered
    as Markdown under a token budget. Each shard appears once (keyed by file_hash),
    with provenance (id@db, timestamp, event type) so a caller can cite it.

    seeds: list of (shard_id, db_index). depth: link hops from the seeds (0 = seeds only).
    The budget is characters/4 (a rough token estimate); nodes past it are listed by
    id only, so nothing is silently dropped.
    """
    seen: Dict[str, Dict] = {}
    frontier = []
    for sid, dbi in seeds:
        sh = core.get_shard_by_id(sid, dbi)
        if sh is None:
            continue
        h = _hash_for(sid, dbi)
        if h and h not in seen:
            seen[h] = {**dict(sh), "_db_index": dbi, "_hop": 0}
            frontier.append((sid, dbi))
    for hop in range(1, depth + 1):
        nxt = []
        for sid, dbi in frontier:
            for nb in related_shards(sid, dbi, limit=per_node_links):
                nh = nb.get("file_hash") or _hash_for(nb.get("id"), nb.get("_db_index", dbi))
                if not nh or nh in seen or isinstance(nb.get("id"), str):
                    continue
                seen[nh] = {**nb, "_hop": hop}
                nxt.append((nb["id"], nb.get("_db_index", dbi)))
        frontier = nxt
    ordered = sorted(seen.values(), key=lambda s: (s["_hop"], s.get("timestamp") or ""))
    lines, spent, omitted = [], 0, []
    for s in ordered:
        body = str(s.get("content") or "")
        head = (f"### {s.get('title') or '(untitled)'}\n"
                f"- ref: {s.get('id')}@db{s.get('_db_index')} · {s.get('timestamp')} · "
                f"{s.get('event_type')} · hop {s['_hop']}\n")
        block = head + body.strip() + chr(10)
        room = (token_budget - spent) * 4 - len(head) - len(" ...[truncated]") - 2
        if room <= 0:
            omitted.append(f"{s.get('id')}@db{s.get('_db_index')}")
            continue
        if len(block) // 4 > token_budget - spent:
            block = head + body.strip()[:room] + chr(32) + "...[truncated]" + chr(10)
        lines.append(block)
        spent += len(block) // 4
    return {"markdown": "\n".join(lines), "included": len(lines),
            "omitted_refs": omitted, "approx_tokens": spent}
