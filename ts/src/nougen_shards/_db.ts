/**
 * SQLite backend adapter for the NouGenShards TS port.
 *
 * Centralizes the database driver so every module opens connections the same
 * way. Backed by better-sqlite3 (stable, synchronous, no experimental flag),
 * with WAL + busy-timeout applied to writable handles — mirroring the PRAGMA
 * setup the Python `sqlite3` connections use.
 *
 * `DatabaseSync` is re-exported as the connection type so call sites that were
 * written against node:sqlite keep their annotations unchanged.
 */
import Database from "better-sqlite3";

export type DatabaseSync = Database.Database;

export interface OpenOptions {
  readOnly?: boolean;
}

/** Open a SQLite connection. Writable handles get WAL + a 10s busy timeout. */
export function createDatabase(path: string, opts: OpenOptions = {}): Database.Database {
  const db = new Database(path, opts.readOnly ? { readonly: true } : {});
  if (!opts.readOnly) {
    // PRAGMAs that write to the db header — only valid on a writable handle.
    db.pragma("busy_timeout = 10000");
    db.pragma("journal_mode = WAL");
  }
  return db;
}
