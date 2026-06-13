/**
 * NouGenShards: Advanced Memory-Core Substrate. (TS mimic of core.py)
 * Logic: SQLite + FTS5 + BM25 + Trigram (n-gram) + Vector Embeddings + Bayesian Reranking.
 * Architecture: Reverse Epistemics (Manifesto of Bayesian Orchestration).
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { createDatabase, type DatabaseSync } from "./_db.js";
import * as history from "./history.js";

// Configuration (Module 10: Integrate Constraints)
export const MAX_DB_SIZE = 1 * 1024 * 1024 * 1024; // 1GB Safety Limit per DB
export const MAX_DB_COUNT = 9;

function resolve_vault_dir(): string {
  let vault_dir = process.env.NOUGEN_VAULT_DIR;
  if (!vault_dir) {
    const local_vault = ".vault";
    if (existsSync(local_vault) && statSync(local_vault).isDirectory()) {
      vault_dir = local_vault;
    } else {
      vault_dir = path.join(homedir(), ".nougen", "shards");
    }
  }
  return vault_dir;
}

export const GLOBAL_DIR = resolve_vault_dir();

/** A shard row plus retrieval metadata, dict-shaped to mirror sqlite3.Row. */
export type Shard = Record<string, any>;

/** Returns the path for a specific database index (Module 11: Transform Architecture). */
export function get_db_path(index: number): string {
  const local_name = index > 1 ? `shards_${index}.db` : "shards.db";
  if (existsSync(local_name)) {
    return local_name;
  }
  mkdirSync(GLOBAL_DIR, { recursive: true });
  return path.join(GLOBAL_DIR, `nougen_shards_${index}.db`);
}

/** Checks if a database file has reached its 1GB constraint. */
export function is_db_full(index: number): boolean {
  const p = get_db_path(index);
  if (!existsSync(p)) {
    return false;
  }
  try {
    return statSync(p).size >= MAX_DB_SIZE;
  } catch {
    return true;
  }
}

/**
 * Module 4: Surface Leverage (Intelligent Scaling).
 * Deterministic Hash-Based Routing ensures O(1) deduplication and uniform distribution.
 * Distributes load evenly across the 9-DB cluster.
 */
export function get_routing_index(fhash: string): number {
  // Python: int(fhash, 16) % MAX_DB_COUNT — use BigInt for the 128-bit md5 value.
  return Number(BigInt(`0x${fhash}`) % BigInt(MAX_DB_COUNT)) + 1;
}

/**
 * Resolves the destination DB for a new shard (Module 4: Surface Leverage).
 * Routes deterministically by content hash for uniform O(1) distribution across
 * the 9-DB cluster, then skips any database that has hit its 1GB constraint.
 */
export function get_write_index(fhash: string): number {
  const start = get_routing_index(fhash);
  for (let offset = 0; offset < MAX_DB_COUNT; offset++) {
    const idx = ((start - 1 + offset) % MAX_DB_COUNT) + 1;
    if (!is_db_full(idx)) {
      return idx;
    }
  }
  return start; // All databases full; fall back to the hash target.
}

/** Legacy alias, preserved for cli.ts compatibility. */
export function get_active_db_index(): number {
  return get_routing_index(createHash("md5").update("default").digest("hex"));
}

/** Establishes an SQLite connection with WAL enabled (Module 19: Stabilize Reasoning). */
export function get_connection(index: number): DatabaseSync {
  const p = get_db_path(index);
  return createDatabase(p);
}

/** Initializes the substrate schema (Module 6: Copy Successful Topology). */
export function init_db(index: number = 1): void {
  const conn = get_connection(index);

  // Main table for shards (Module 3: Deep Grep Latent Structure)
  conn.exec(`
        CREATE TABLE IF NOT EXISTS shards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            utility_score REAL DEFAULT 1.0, -- Bayesian Prior (Module 20)
            access_count INTEGER DEFAULT 0,
            file_hash TEXT UNIQUE NOT NULL
        );
    `);

  // Add embedding column if missing (Module 11: Transform Architecture)
  try {
    conn.exec("ALTER TABLE shards ADD COLUMN embedding BLOB;");
  } catch {
    /* column already exists */
  }

  // FTS5 with Trigram for fuzzy recall (Module 1: Metamers)
  try {
    conn.exec(`
            CREATE VIRTUAL TABLE IF NOT EXISTS shards_fts USING fts5(
                title,
                content,
                content='shards',
                content_rowid='id',
                tokenize='trigram'
            );
        `);
  } catch {
    conn.exec(`
            CREATE VIRTUAL TABLE IF NOT EXISTS shards_fts USING fts5(
                title,
                content,
                content='shards',
                content_rowid='id'
            );
        `);
  }

  // Sync triggers (Module 18: Reconstruct Coherence)
  conn.exec("DROP TRIGGER IF EXISTS shards_ai");
  conn.exec(`
        CREATE TRIGGER shards_ai AFTER INSERT ON shards BEGIN
            INSERT INTO shards_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
        END;
    `);

  conn.close();
}

/** Measures semantic alignment (Module 7: Transpose Patterns). */
export function cosine_similarity(vec1: number[], vec2: number[]): number {
  if (!vec1?.length || !vec2?.length || vec1.length !== vec2.length) {
    return 0.0;
  }
  let dot_product = 0;
  let mag1_sq = 0;
  let mag2_sq = 0;
  for (let i = 0; i < vec1.length; i++) {
    dot_product += vec1[i] * vec2[i];
    mag1_sq += vec1[i] * vec1[i];
    mag2_sq += vec2[i] * vec2[i];
  }
  const mag1 = Math.sqrt(mag1_sq);
  const mag2 = Math.sqrt(mag2_sq);
  if (!mag1 || !mag2) {
    return 0.0;
  }
  return dot_product / (mag1 * mag2);
}

/** Saves a unit of experience (Module 5: Extract Invariants). */
export function capture(
  event_type: string,
  title: string,
  content: string,
  tags: string[] | null = null,
  embedding: number[] | null = null,
): boolean {
  const fhash = createHash("md5").update(content, "utf-8").digest("hex");

  // Global Deduplication (The Invariant Check)
  for (let i = 1; i <= MAX_DB_COUNT; i++) {
    if (!existsSync(get_db_path(i))) {
      continue;
    }
    const conn = get_connection(i);
    try {
      const row = conn.prepare("SELECT id FROM shards WHERE file_hash = ?").get(fhash);
      if (row) {
        return false;
      }
    } catch {
      /* table may not exist yet; mirror OperationalError pass */
    } finally {
      conn.close();
    }
  }

  const target_idx = get_write_index(fhash);
  init_db(target_idx);

  const emb_blob = embedding ? Buffer.from(JSON.stringify(embedding)) : null;
  const tags_str = JSON.stringify(tags ?? []);
  const timestamp = new Date().toISOString();

  const conn = get_connection(target_idx);
  try {
    const result = conn
      .prepare(`
            INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        `)
      .run(timestamp, event_type, title, content, tags_str, fhash, emb_blob);

    // Log CREATED event
    history.log_event(Number(result.lastInsertRowid) || 0, target_idx, "CREATED", null, 1.0);

    return true;
  } catch {
    return false; // mirror sqlite3.IntegrityError
  } finally {
    conn.close();
  }
}

// Bayesian Ranking Config (Module 20)
export const WEIGHT_BM25 = 0.4;
export const WEIGHT_SEMANTIC = 0.6;
export const WEIGHT_LIKELIHOOD = 0.7;
export const WEIGHT_PRIOR = 0.3;

/** Helper to process a single FTS result with Bayesian math. */
function _process_fts_result(row: Shard, db_index: number, query_embedding: number[] | null): Shard {
  const item: Shard = { ...row };
  item._db_index = db_index;
  // 1. Likelihood Part A: BM25 (The Adjacency Score)
  const norm_bm25 = 1.0 / (1.0 + Math.abs(item.bm25_score));

  // 2. Likelihood Part B: Semantic (The Latent Score)
  let sem_score = 0.0;
  if (query_embedding && item.embedding) {
    sem_score = cosine_similarity(query_embedding, JSON.parse(Buffer.from(item.embedding).toString()));
  }

  // Synthesize Coherent Likelihood (Module 9)
  const likelihood = norm_bm25 * WEIGHT_BM25 + sem_score * WEIGHT_SEMANTIC;

  // 3. Bayesian Posterior = Likelihood * Prior (utility_score)
  item.final_score = likelihood * WEIGHT_LIKELIHOOD + item.utility_score * WEIGHT_PRIOR;
  return item;
}

/**
 * Build a safe FTS5 MATCH expression from arbitrary user input.
 *
 * Every word is treated as a literal phrase: each token is double-quoted (any
 * embedded quote doubled, per FTS5 escaping), so query text can never be parsed
 * as FTS5 operators (AND/OR/NOT/NEAR/*, bare quotes, parentheses). Without this,
 * inputs like `c++`, `foo"bar`, or a lone `AND` throw and the search silently
 * degrades to a LIKE substring scan. Tokens shorter than 3 chars are dropped
 * because the trigram tokenizer cannot index them. Returns null when nothing
 * matchable remains (caller then uses the LIKE fallback).
 */
function _build_fts_match_query(query: string): string | null {
  const tokens = query.split(/\s+/).filter((t) => t.length >= 3);
  if (!tokens.length) {
    return null;
  }
  return tokens.map((t) => `"${t.replace(/"/g, '""')}"`).join(" ");
}

/**
 * Advanced Retrieval and Bayesian Orchestration (Module 21).
 * Synthesizes BM25 (Adjacency) and Semantic (Latent) signals.
 */
export function retrieve(query: string, limit: number = 3, query_embedding: number[] | null = null): Shard[] {
  const all_results: Shard[] = [];
  for (let i = 1; i <= MAX_DB_COUNT; i++) {
    if (!existsSync(get_db_path(i))) {
      continue;
    }
    const conn = get_connection(i);
    try {
      let fts_worked = false;
      const fts_query = _build_fts_match_query(query);
      if (fts_query !== null) {
        try {
          const res = conn
            .prepare(`
                        SELECT s.id, s.title, s.content, s.utility_score, s.embedding,
                               s.tags, bm25(shards_fts) as bm25_score
                        FROM shards s JOIN shards_fts ON s.id = shards_fts.rowid
                        WHERE shards_fts MATCH ?
                        ORDER BY bm25_score ASC LIMIT 20
                    `)
            .all(fts_query) as Shard[];
          if (res.length) {
            for (const row of res) {
              // Log ACCESSED event
              history.log_event(row.id, i, "ACCESSED");
              all_results.push(_process_fts_result(row, i, query_embedding));
            }
            fts_worked = true;
          }
        } catch {
          /* mirror sqlite3.OperationalError pass */
        }
      }

      if (!fts_worked) {
        // Fallback to LIKE (Module 1: Resolving Metamers for small query strings)
        const like_query = `%${query}%`;
        const rows = conn
          .prepare(`
                    SELECT id, title, content, utility_score, embedding, tags
                    FROM shards
                    WHERE title LIKE ? OR content LIKE ?
                    ORDER BY utility_score DESC LIMIT 20
                `)
          .all(like_query, like_query) as Shard[];
        for (const row of rows) {
          const item: Shard = { ...row };
          item._db_index = i;
          history.log_event(item.id, i, "ACCESSED");
          let sem_score = 0.0;
          if (query_embedding && item.embedding) {
            sem_score = cosine_similarity(query_embedding, JSON.parse(Buffer.from(item.embedding).toString()));
          }
          const likelihood = query_embedding ? sem_score : 0.5;
          item.final_score = likelihood * 0.5 + item.utility_score * 0.5;
          all_results.push(item);
        }
      }
    } finally {
      conn.close();
    }
  }

  all_results.sort((a, b) => b.final_score - a.final_score);
  return all_results.slice(0, limit);
}

/** Retrieves a specific shard by ID from a specific DB index. */
export function get_shard_by_id(shard_id: number, db_index: number): Shard | null {
  if (!existsSync(get_db_path(db_index))) return null;
  const conn = get_connection(db_index);
  try {
    const row = conn.prepare("SELECT * FROM shards WHERE id = ?").get(shard_id);
    return row ? ({ ...row } as Shard) : null;
  } finally {
    conn.close();
  }
}

/** Bayesian Inversion: Updates the Prior (utility_score) based on outcome evidence. */
export function mark_shard(shard_id: number, worked: boolean): boolean {
  for (let i = 1; i <= MAX_DB_COUNT; i++) {
    if (!existsSync(get_db_path(i))) {
      continue;
    }
    const conn = get_connection(i);
    const row = conn.prepare("SELECT id, utility_score FROM shards WHERE id = ?").get(shard_id) as
      | Shard
      | undefined;
    if (row) {
      const old_score = row.utility_score as number;
      const val = worked ? 1.0 : -0.5;
      const new_score = old_score + val;
      conn.prepare("UPDATE shards SET utility_score = ? WHERE id = ?").run(new_score, shard_id);
      conn.close();

      // Log UTILITY_CHANGE event
      history.log_event(shard_id, i, "UTILITY_CHANGE", old_score, new_score);

      return true;
    }
    conn.close();
  }
  return false;
}

/**
 * Module 19: Stabilize Reasoning.
 * Applies a decay factor to all utility scores to prevent stale dominance.
 */
export function decay_utility_scores(factor: number = 0.95): boolean {
  for (let i = 1; i <= MAX_DB_COUNT; i++) {
    if (!existsSync(get_db_path(i))) {
      continue;
    }
    const conn = get_connection(i);
    try {
      conn.prepare("UPDATE shards SET utility_score = utility_score * ?").run(factor);
    } finally {
      conn.close();
    }
  }
  return true;
}

/** Synthesis of retrieved experience into a coherent context packet (Module 18). */
export function compile_recall_packet(shards: Shard[]): string {
  if (!shards.length) {
    return "<!-- NO RELEVANT MEMORY RECALLED -->";
  }
  const output = ["=== NOUGENSHARDS RECALL PACKET [BAYESIAN SYNTHESIS] ==="];
  for (const s of shards) {
    output.push(`--- RECORD #${s.id} [Posterior: ${(s.final_score as number).toFixed(2)}] ---`);
    output.push(`Title: ${s.title}\n${s.content}\n`);
  }
  return output.join("\n");
}
