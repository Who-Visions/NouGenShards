/**
 * NouGenShards Billing and Usage Metering. (TS mimic of billing.py)
 * Handles subscription status and token counting for the Cloud Gateway.
 */
import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { createDatabase } from "./_db.js";

// Configuration for the Node
export const NOUGEN_HOME = process.env.NOUGEN_HOME ?? path.join(homedir(), ".nougen");
export const BILLING_DB = path.join(NOUGEN_HOME, "billing.db");

/** Initializes the billing and usage substrate. */
export function init_billing(): void {
  mkdirSync(NOUGEN_HOME, { recursive: true });
  const conn = createDatabase(BILLING_DB);

  // Usage table (Module 20: Quantify Intelligence)
  conn.exec(`
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_token TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            cached_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0.0
        );
    `);

  // Subscription table
  conn.exec(`
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_token TEXT PRIMARY KEY,
            status TEXT DEFAULT 'active', -- active, inactive, over_limit
            monthly_limit INTEGER DEFAULT 1000000, -- 100k tokens default
            used_this_month INTEGER DEFAULT 0,
            last_reset TEXT NOT NULL
        );
    `);

  conn.close();
}

export interface SubscriptionStatus {
  status: string;
  message?: string;
  used?: number;
  limit?: number;
}

/** Verifies user status and usage limits. */
export function check_subscription(token: string): SubscriptionStatus {
  if (!existsSync(BILLING_DB)) {
    init_billing();
  }

  const conn = createDatabase(BILLING_DB);
  try {
    const row = conn.prepare("SELECT * FROM subscriptions WHERE user_token = ?").get(token) as
      | Record<string, any>
      | undefined;
    if (!row) {
      // First time user? Default to active for testing, or inactive for production
      // (Module 10: Fail Closed)
      return { status: "inactive", message: "No active subscription found." };
    }

    if (row.status !== "active") {
      return { status: row.status, message: "Subscription is not active." };
    }

    if (row.used_this_month >= row.monthly_limit) {
      return { status: "over_limit", message: "Monthly token limit reached." };
    }

    return { status: "active", used: row.used_this_month, limit: row.monthly_limit };
  } finally {
    conn.close();
  }
}

export interface UsagePayload {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cached_tokens?: number;
}

/** Meters the request and updates the subscription balance. */
export function log_usage(token: string, provider: string, model: string, usage: UsagePayload): void {
  const timestamp = new Date().toISOString();
  const prompt = usage.prompt_tokens ?? 0;
  const completion = usage.completion_tokens ?? 0;
  const total = usage.total_tokens ?? 0;
  const cached = usage.cached_tokens ?? 0;

  const conn = createDatabase(BILLING_DB);
  try {
    // 1. Log detailed record
    conn
      .prepare(`
            INSERT INTO usage_logs (user_token, timestamp, provider, model, prompt_tokens, completion_tokens, total_tokens, cached_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        `)
      .run(token, timestamp, provider, model, prompt, completion, total, cached);

    // 2. Update monthly balance
    conn
      .prepare(`
            UPDATE subscriptions
            SET used_this_month = used_this_month + ?
            WHERE user_token = ?
        `)
      .run(total, token);
  } finally {
    conn.close();
  }
}
