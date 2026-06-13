/**
 * NouGenShards: History Substrate & Event Logging. (TS mimic of history.py)
 * Tracks machine experience evolution across multiple horizons.
 */
import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { createDatabase, type DatabaseSync } from "./_db.js";
import * as core from "./core.js";

// Configuration
export const HISTORY_DIR = path.join(homedir(), ".nougen", "shards");
export const DB_PATH = path.join(HISTORY_DIR, "history.db");

/** Establishes a connection to the history substrate with WAL enabled. */
export function get_history_connection(): DatabaseSync {
  mkdirSync(HISTORY_DIR, { recursive: true });
  return createDatabase(DB_PATH);
}

/** Initializes the shard_events table and optimized indexes. */
export function init_history_db(): void {
  const conn = get_history_connection();

  // Module 3: Deep Grep Latent Structure (Tracking evolution)
  conn.exec(`
        CREATE TABLE IF NOT EXISTS shard_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shard_id INTEGER NOT NULL,
            db_index INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            old_score REAL,
            new_score REAL,
            timestamp TEXT NOT NULL,
            metadata JSON
        );
    `);

  // Module 10: Integrate Constraints (Performance Indexes)
  conn.exec("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON shard_events(timestamp);");
  conn.exec("CREATE INDEX IF NOT EXISTS idx_history_shard ON shard_events(shard_id, db_index);");

  conn.close();
}

/** Writes a historical event to the substrate. */
export function log_event(
  shard_id: number,
  db_index: number,
  event_type: string,
  old_score: number | null = null,
  new_score: number | null = null,
  metadata: Record<string, any> | null = null,
): void {
  // Lazy init to prevent side-effects on import
  if (!existsSync(DB_PATH)) {
    init_history_db();
  }

  const timestamp = new Date().toISOString();
  const meta_json = JSON.stringify(metadata ?? {});

  const conn = get_history_connection();
  try {
    conn
      .prepare(`
            INSERT INTO shard_events (shard_id, db_index, event_type, old_score, new_score, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        `)
      .run(shard_id, db_index, event_type, old_score, new_score, timestamp, meta_json);
  } catch (exc) {
    // Module 10: Graceful Degradation (Log failure but don't crash main memory)
    console.log(`[Warning] Failed to log history event: ${exc}`);
  } finally {
    conn.close();
  }
}

/** Module 2: Activate Orchestration (Analytical Control Loop). */
export class HistoryEngine {
  /** Maps friendly period names to millisecond deltas (Python timedelta mimic). */
  static get_period_delta(period: string): number {
    const HOUR = 3600 * 1000;
    const DAY = 24 * HOUR;
    const mapping: Record<string, number> = {
      "24h": 24 * HOUR,
      week: 7 * DAY,
      month: 30 * DAY,
      quarter: 90 * DAY,
      year: 365 * DAY,
    };
    return mapping[period] ?? mapping.week;
  }

  /** Calculates memory growth in the specified window. */
  static get_growth_rate(period: string = "week"): { period: string; new_shards: number; total_shards: number } {
    const delta = HistoryEngine.get_period_delta(period);
    const cutoff = new Date(Date.now() - delta).toISOString();

    const conn = get_history_connection();
    try {
      const count = (
        conn
          .prepare("SELECT COUNT(*) AS c FROM shard_events WHERE event_type = 'CREATED' AND timestamp > ?")
          .get(cutoff) as { c: number }
      ).c;

      const total = (
        conn.prepare("SELECT COUNT(*) AS c FROM shard_events WHERE event_type = 'CREATED'").get() as { c: number }
      ).c;
      return { period, new_shards: count, total_shards: total };
    } catch {
      return { period, new_shards: 0, total_shards: 0 };
    } finally {
      conn.close();
    }
  }

  /** Measures the net change in usefulness across the fabric. */
  static get_utility_delta(period: string = "week"): number {
    const delta = HistoryEngine.get_period_delta(period);
    const cutoff = new Date(Date.now() - delta).toISOString();

    const conn = get_history_connection();
    try {
      const res = conn
        .prepare(`
                SELECT SUM(new_score - old_score) AS s FROM shard_events
                WHERE event_type = 'UTILITY_CHANGE' AND timestamp > ?
            `)
        .get(cutoff) as { s: number | null };
      return res.s ?? 0.0;
    } catch {
      return 0.0;
    } finally {
      conn.close();
    }
  }

  /** Alias for get_utility_delta (used by tests). */
  static get_utility_stats(period: string = "week"): number {
    return HistoryEngine.get_utility_delta(period);
  }

  /** Identifies top shards by utility growth in the period. */
  static get_top_shards(period: string = "week", limit: number = 5): Record<string, any>[] {
    const delta = HistoryEngine.get_period_delta(period);
    const cutoff = new Date(Date.now() - delta).toISOString();

    const conn = get_history_connection();
    try {
      // Query for net positive utility changes
      const query = `
                SELECT shard_id, db_index, SUM(new_score - old_score) as growth
                FROM shard_events
                WHERE event_type = 'UTILITY_CHANGE' AND timestamp > ?
                GROUP BY shard_id, db_index
                ORDER BY growth DESC
                LIMIT ?
            `;
      const rows = conn.prepare(query).all(cutoff, limit) as Record<string, any>[];

      // Enrich with titles from core
      const enriched: Record<string, any>[] = [];
      for (const r of rows) {
        const item = { ...r };
        const shard = core.get_shard_by_id(item.shard_id, item.db_index);
        if (shard) {
          item.title = shard.title;
          item.utility_score = shard.utility_score;
        } else {
          item.title = "Unknown Shard";
          item.utility_score = 0.0;
        }
        enriched.push(item);
      }
      return enriched;
    } catch {
      return [];
    } finally {
      conn.close();
    }
  }

  /** Consolidates all stats into a single JSON packet. */
  static export_stats_json(period: string = "week"): string {
    return JSON.stringify(
      {
        period,
        growth: HistoryEngine.get_growth_rate(period),
        utility_delta: HistoryEngine.get_utility_delta(period),
        top_shards: HistoryEngine.get_top_shards(period),
      },
      null,
      2,
    );
  }

  /** Generates a simple ASCII timeline of memory growth. */
  static get_timeline(period: string = "week"): string {
    const delta = HistoryEngine.get_period_delta(period);
    const now = Date.now();
    const steps = 10;
    const step_delta = delta / steps;

    let buckets: number[] = [];
    const conn = get_history_connection();
    try {
      for (let i = 0; i < steps; i++) {
        const start = new Date(now - delta + i * step_delta).toISOString();
        const end = new Date(now - delta + (i + 1) * step_delta).toISOString();
        const count = (
          conn
            .prepare(
              "SELECT COUNT(*) AS c FROM shard_events WHERE event_type = 'CREATED' AND timestamp >= ? AND timestamp < ?",
            )
            .get(start, end) as { c: number }
        ).c;
        buckets.push(count);
      }
    } catch {
      buckets = new Array(steps).fill(0);
    } finally {
      conn.close();
    }

    const m_val = buckets.length && Math.max(...buckets) > 0 ? Math.max(...buckets) : 1;
    const normalized = buckets.map((b) => Math.floor((b / m_val) * 5));

    let chart = "";
    for (let h = 5; h > 0; h--) {
      let line = "  ";
      for (const val of normalized) {
        line += val >= h ? "█ " : "  ";
      }
      chart += line + "\n";
    }

    return chart + `  ${period} growth timeline`;
  }
}
