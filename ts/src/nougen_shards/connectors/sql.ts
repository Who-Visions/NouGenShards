/**
 * SQL Connector for external databases. (TS mimic of connectors/sql.py)
 *
 * The Python original rides SQLAlchemy and accepts any dialect URI. The TS port
 * natively supports `sqlite:` URIs via node:sqlite; other dialects are skipped
 * gracefully (mirroring the original's silent `continue` on connection failure).
 */
import { existsSync } from "node:fs";
import { createDatabase } from "../_db.js";
import type { Shard } from "../core.js";

/** Strict regex for safe SQL identifiers. */
export function is_valid_identifier(ident: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(ident);
}

function _sqlite_path_from_uri(uri: string): string | null {
  // Accept sqlite:///path, sqlite://path and plain file paths ending in .db/.sqlite
  const m = uri.match(/^sqlite:\/{0,3}(.+)$/i);
  if (m) {
    return m[1];
  }
  if (/\.(db|sqlite)$/i.test(uri)) {
    return uri;
  }
  return null;
}

function _string_hash(s: string): number {
  // Stable non-crypto hash standing in for Python's hash() in synthetic IDs.
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return h;
}

/** Queries external databases and maps results to Shard format. */
export function query_external_dbs(query: string, db_configs: Record<string, any>[], limit: number = 3): Shard[] {
  const results: Shard[] = [];
  let keywords = query.split(/\s+/).filter((w) => /^[A-Za-z0-9]+$/.test(w));
  if (!keywords.length) keywords = [query];

  for (const conf of db_configs) {
    try {
      const table = conf.table_name as string;
      const title_col = conf.title_col as string;
      const content_col = conf.content_col as string;

      // Patch 16.E: Validate identifiers (Module 10: Constraints)
      if (![table, title_col, content_col].every(is_valid_identifier)) {
        continue;
      }

      const db_path = _sqlite_path_from_uri(String(conf.uri));
      if (!db_path || !existsSync(db_path)) {
        continue; // non-sqlite dialects unsupported in the TS port; skip gracefully
      }

      const conn = createDatabase(db_path, { readOnly: true });
      try {
        const where_clauses: string[] = [];
        const params: string[] = [];
        for (const kw of keywords) {
          where_clauses.push(`(${title_col} LIKE ? OR ${content_col} LIKE ?)`);
          params.push(`%${kw}%`, `%${kw}%`);
        }

        const where_sql = where_clauses.join(" OR ");
        const sql_text = `SELECT ${title_col} AS title, ${content_col} AS content FROM ${table} WHERE ${where_sql} LIMIT ?`;
        const rows = conn.prepare(sql_text).all(...params, limit) as Record<string, any>[];

        for (const item of rows) {
          results.push({
            id: `ext_${conf.id}_${Math.abs(_string_hash(String(item.title)))}`,
            event_type: "EXTERNAL_DB",
            title: item.title,
            content: item.content,
            tags: '["external"]',
            utility_score: 1.0,
            access_count: 0,
            file_hash: String(_string_hash(String(item.content))),
            bm25_score: 0.0,
            final_score: 0.5,
            _db_index: `ext_${conf.id}`,
          });
        }
      } finally {
        conn.close();
      }
    } catch {
      continue;
    }
  }
  return results;
}
