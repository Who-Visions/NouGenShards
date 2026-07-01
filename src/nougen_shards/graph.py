"""
Graph Memory: link shards (fixes, files, commands, decisions) into a latent mesh.

Edges live in a dedicated graph.db inside the vault (honors NOUGEN_VAULT_DIR via
core.GLOBAL_DIR), so a fix can point at the file it touched, a command at the
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
from typing import List, Dict, Optional, Tuple

from . import core


def get_graph_db_path():
    """Path to the graph edge store (alongside the shard cluster in the vault)."""
    core.GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    return core.GLOBAL_DIR / "graph.db"


def get_graph_connection():
    """SQLite connection to the graph store, WAL-enabled (Module 19)."""
    conn = sqlite3.connect(str(get_graph_db_path()), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
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
