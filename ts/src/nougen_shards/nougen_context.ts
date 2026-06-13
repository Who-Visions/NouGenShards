/**
 * NouGenContext core database and sandbox management. (TS mimic of nougen_context.py)
 * session.db: ctx_events + FTS5 ctx_events_fts + trigger, ctx_sandbox, ctx_session.
 */
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { createDatabase, type DatabaseSync } from "./_db.js";

export const NOUGEN_CONTEXT_DIR = path.join(homedir(), ".nougen", "context");
export const SESSION_DB_PATH = path.join(NOUGEN_CONTEXT_DIR, "session.db");

/** Establishes an SQLite connection for the session context with WAL enabled. */
export function get_context_connection(): DatabaseSync {
  mkdirSync(path.dirname(SESSION_DB_PATH), { recursive: true });
  return createDatabase(SESSION_DB_PATH);
}

/** Initializes the ephemeral session database schema. */
export function init_context_db(clean_slate: boolean = true): void {
  if (clean_slate && existsSync(SESSION_DB_PATH)) {
    // Clean-slate rule: wipe session.db unless continuing
    for (const p of [SESSION_DB_PATH, `${SESSION_DB_PATH}-wal`, `${SESSION_DB_PATH}-shm`]) {
      try {
        rmSync(p, { force: true });
      } catch {
        /* mirror OSError pass */
      }
    }
  }

  const conn = get_context_connection();
  try {
    // ctx_events: every file edit, git op, error, and decision
    conn.exec(`
        CREATE TABLE IF NOT EXISTS ctx_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT
        );
    `);

    // ctx_events_fts: FTS5 for fast recall
    conn.exec(`
        CREATE VIRTUAL TABLE IF NOT EXISTS ctx_events_fts USING fts5(
            content,
            content='ctx_events',
            content_rowid='id'
        );
    `);

    // Triggers for ctx_events synchronization
    conn.exec(`
        CREATE TRIGGER IF NOT EXISTS ctx_events_ai AFTER INSERT ON ctx_events BEGIN
            INSERT INTO ctx_events_fts(rowid, content) VALUES (new.id, new.content);
        END;
    `);

    // ctx_sandbox: large raw outputs keyed by handle
    conn.exec(`
        CREATE TABLE IF NOT EXISTS ctx_sandbox (
            handle TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            data TEXT NOT NULL,
            summary TEXT
        );
    `);

    // ctx_session: current working set (open files, last task, etc)
    conn.exec(`
        CREATE TABLE IF NOT EXISTS ctx_session (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    `);
  } finally {
    conn.close();
  }
}

/** Logs an event into the session context. */
export function log_event(
  event_type: string,
  content: string,
  metadata: Record<string, any> | null = null,
): void {
  const timestamp = new Date().toISOString();
  const metadata_str = JSON.stringify(metadata ?? {});
  const conn = get_context_connection();
  try {
    conn
      .prepare("INSERT INTO ctx_events (timestamp, type, content, metadata) VALUES (?, ?, ?, ?)")
      .run(timestamp, event_type, content, metadata_str);
  } finally {
    conn.close();
  }
}

/** Searches session context using BM25. */
export function search_context(query: string, limit: number = 5): Record<string, any>[] {
  const conn = get_context_connection();
  try {
    const rows = conn
      .prepare(`
        SELECT e.id, e.timestamp, e.type, e.content, e.metadata
        FROM ctx_events e
        JOIN ctx_events_fts f ON e.id = f.rowid
        WHERE ctx_events_fts MATCH ?
        ORDER BY bm25(ctx_events_fts) ASC
        LIMIT ?
    `)
      .all(query, limit) as Record<string, any>[];
    return rows.map((row) => ({ ...row }));
  } finally {
    conn.close();
  }
}

/** Retrieves a specific event from the context by ID. */
export function get_event(event_id: number): Record<string, any> | null {
  const conn = get_context_connection();
  try {
    const row = conn
      .prepare("SELECT id, type, content, timestamp, metadata FROM ctx_events WHERE id = ?")
      .get(event_id);
    return row ? { ...row } : null;
  } finally {
    conn.close();
  }
}

/** Stores large tool output in the sandbox. */
export function store_sandbox(handle: string, data: string, summary: string = ""): void {
  const timestamp = new Date().toISOString();
  const conn = get_context_connection();
  try {
    conn
      .prepare("INSERT OR REPLACE INTO ctx_sandbox (handle, timestamp, data, summary) VALUES (?, ?, ?, ?)")
      .run(handle, timestamp, data, summary);
  } finally {
    conn.close();
  }
}

/** Retrieves data from the sandbox by handle. */
export function fetch_sandbox(handle: string): string | null {
  const conn = get_context_connection();
  try {
    const row = conn.prepare("SELECT data FROM ctx_sandbox WHERE handle = ?").get(handle) as
      | Record<string, any>
      | undefined;
    return row ? (row.data as string) : null;
  } finally {
    conn.close();
  }
}

/** Searches context events by content, event type, or metadata. */
export function search_events(query: string, limit: number = 5): Record<string, any>[] {
  const conn = get_context_connection();
  try {
    const pattern = `%${query}%`;
    const rows = conn
      .prepare(`
            SELECT id, type, content as description, timestamp, metadata
            FROM ctx_events
            WHERE content LIKE ? OR type LIKE ? OR metadata LIKE ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
        `)
      .all(pattern, pattern, pattern, limit) as Record<string, any>[];
    return rows.map((r) => ({
      id: r.id,
      event_type: r.type,
      description: r.description,
      timestamp: r.timestamp,
      metadata: r.metadata,
    }));
  } finally {
    conn.close();
  }
}
