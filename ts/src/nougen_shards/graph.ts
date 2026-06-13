/**
 * Graph Memory: link shards (fixes, files, commands, decisions) into a latent mesh.
 * (TS mimic of graph.py)
 *
 * Edges live in a dedicated graph.db inside the vault (honors NOUGEN_VAULT_DIR via
 * core.GLOBAL_DIR). Nodes are identified by file_hash, not the per-DB autoincrement
 * `id` (the 9-DB cluster gives each database its own id sequence, so id alone is not
 * unique across the mesh; file_hash is, since capture() dedups globally). The public
 * API takes shard ids for ergonomics, with a db_index (recall's `_db_index`) to say
 * which database the id lives in (default 1, the common single-DB case).
 */
import { existsSync, mkdirSync } from "node:fs";
import * as path from "node:path";
import { createDatabase, type DatabaseSync } from "./_db.js";
import * as core from "./core.js";
import type { Shard } from "./core.js";

/** Path to the graph edge store (alongside the shard cluster in the vault). */
export function get_graph_db_path(): string {
  mkdirSync(core.GLOBAL_DIR, { recursive: true });
  return path.join(core.GLOBAL_DIR, "graph.db");
}

function get_graph_connection(): DatabaseSync {
  return createDatabase(get_graph_db_path());
}

/** Initialize the shard_edges table and lookup indexes. */
export function init_graph_db(): void {
  const conn = get_graph_connection();
  conn.exec(`
        CREATE TABLE IF NOT EXISTS shard_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src_hash TEXT NOT NULL,
            dst_hash TEXT NOT NULL,
            relation TEXT NOT NULL DEFAULT 'relates',
            created_at TEXT NOT NULL,
            UNIQUE(src_hash, dst_hash, relation)
        )
    `);
  conn.exec("CREATE INDEX IF NOT EXISTS idx_edges_src ON shard_edges(src_hash)");
  conn.exec("CREATE INDEX IF NOT EXISTS idx_edges_dst ON shard_edges(dst_hash)");
  conn.close();
}

/** Resolve (id, db_index) -> file_hash, the global node identity. */
function _hash_for(shard_id: number, db_index: number): string | null {
  const shard = core.get_shard_by_id(shard_id, db_index);
  return shard ? (shard.file_hash as string) : null;
}

/** Resolve a file_hash back to its shard dict by scanning the cluster. */
function _shard_for_hash(file_hash: string): Shard | null {
  for (let i = 1; i <= core.MAX_DB_COUNT; i++) {
    if (!existsSync(core.get_db_path(i))) {
      continue;
    }
    const conn = core.get_connection(i);
    try {
      const row = conn.prepare("SELECT * FROM shards WHERE file_hash = ?").get(file_hash) as Shard | undefined;
      if (row) {
        const item: Shard = { ...row };
        item._db_index = i;
        return item;
      }
    } catch {
      /* table may not exist yet */
    } finally {
      conn.close();
    }
  }
  return null;
}

/**
 * Create an edge src -> dst labelled `relation` (e.g. 'fixes', 'touches',
 * 'caused_by', 'relates'). Both shards must exist. Idempotent on
 * (src_hash, dst_hash, relation). bidirectional=true also stores dst -> src.
 * Returns true if at least one new edge was written.
 */
export function link_shards(
  src_id: number,
  dst_id: number,
  relation: string = "relates",
  src_db: number = 1,
  dst_db: number = 1,
  bidirectional: boolean = false,
): boolean {
  const src_hash = _hash_for(src_id, src_db);
  const dst_hash = _hash_for(dst_id, dst_db);
  if (!src_hash || !dst_hash || src_hash === dst_hash) {
    return false;
  }

  init_graph_db();
  const timestamp = new Date().toISOString();
  const conn = get_graph_connection();
  try {
    let written = conn
      .prepare(
        "INSERT OR IGNORE INTO shard_edges (src_hash, dst_hash, relation, created_at) VALUES (?, ?, ?, ?)",
      )
      .run(src_hash, dst_hash, relation, timestamp).changes;
    if (bidirectional) {
      written += conn
        .prepare(
          "INSERT OR IGNORE INTO shard_edges (src_hash, dst_hash, relation, created_at) VALUES (?, ?, ?, ?)",
        )
        .run(dst_hash, src_hash, relation, timestamp).changes;
    }
    return Number(written) > 0;
  } finally {
    conn.close();
  }
}

/**
 * Return shards connected to (shard_id, db_index) — undirected: follows edges in
 * either direction — optionally filtered to a single relation. Each result is the
 * neighbour shard dict enriched with `relation` and `direction` ('out'/'in').
 */
export function related_shards(
  shard_id: number,
  db_index: number = 1,
  relation: string | null = null,
  limit: number = 10,
): Shard[] {
  const node_hash = _hash_for(shard_id, db_index);
  if (!node_hash || !existsSync(get_graph_db_path())) {
    return [];
  }

  const conn = get_graph_connection();
  let out_rows: Array<{ nhash: string; relation: string }>;
  let in_rows: Array<{ nhash: string; relation: string }>;
  try {
    const rel_sql = relation ? " AND relation = ?" : "";
    const out_params = relation ? [node_hash, relation] : [node_hash];
    out_rows = conn
      .prepare(`SELECT dst_hash AS nhash, relation FROM shard_edges WHERE src_hash = ?${rel_sql}`)
      .all(...out_params) as Array<{ nhash: string; relation: string }>;
    const in_params = relation ? [node_hash, relation] : [node_hash];
    in_rows = conn
      .prepare(`SELECT src_hash AS nhash, relation FROM shard_edges WHERE dst_hash = ?${rel_sql}`)
      .all(...in_params) as Array<{ nhash: string; relation: string }>;
  } finally {
    conn.close();
  }

  const neighbours: Shard[] = [];
  const seen = new Set<string>();
  const tagged = [
    ...out_rows.map((r) => ({ row: r, direction: "out" })),
    ...in_rows.map((r) => ({ row: r, direction: "in" })),
  ];
  for (const { row, direction } of tagged) {
    const key = `${row.nhash}|${row.relation}|${direction}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    const shard = _shard_for_hash(row.nhash);
    if (shard) {
      shard.relation = row.relation;
      shard.direction = direction;
      neighbours.push(shard);
    }
    if (neighbours.length >= limit) {
      break;
    }
  }
  return neighbours;
}

/** Total number of edges in the mesh (0 if the graph store is absent). */
export function edge_count(): number {
  if (!existsSync(get_graph_db_path())) {
    return 0;
  }
  const conn = get_graph_connection();
  try {
    return (conn.prepare("SELECT COUNT(*) AS c FROM shard_edges").get() as { c: number }).c;
  } catch {
    return 0;
  } finally {
    conn.close();
  }
}
