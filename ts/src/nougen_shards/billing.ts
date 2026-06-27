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

// Estimated provider list prices in USD per 1M tokens: [input, output].
// Override via NOUGEN_PRICING_JSON. Unknown / ":free" models cost 0.0.
const _DEFAULT_PRICING: Record<string, [number, number]> = {
  ":free": [0.0, 0.0],
  "claude-3.5-sonnet": [3.0, 15.0],
  "claude-3-opus": [15.0, 75.0],
  "claude-3-haiku": [0.25, 1.25],
  "gpt-4o-mini": [0.15, 0.6],
  "gpt-4o": [2.5, 10.0],
};

function _loadPricing(): Record<string, [number, number]> {
  const pricing: Record<string, [number, number]> = { ..._DEFAULT_PRICING };
  const raw = process.env.NOUGEN_PRICING_JSON;
  if (raw) {
    try {
      const obj = JSON.parse(raw);
      for (const [key, val] of Object.entries(obj)) {
        pricing[key.toLowerCase()] = [Number((val as any)[0]), Number((val as any)[1])];
      }
    } catch {
      /* ignore malformed override */
    }
  }
  return pricing;
}

function _priceFor(model: string): [number, number] {
  const m = (model ?? "").toLowerCase();
  for (const [key, price] of Object.entries(_loadPricing())) {
    if (m.includes(key)) return price;
  }
  return [0.0, 0.0];
}

/** Estimate USD cost for a request. Cached prompt tokens are billed at 10% of
 *  the input rate; free/unknown models cost 0.0. */
export function compute_cost(model: string, usage: UsagePayload): number {
  const [inPrice, outPrice] = _priceFor(model);
  const prompt = usage.prompt_tokens ?? 0;
  const completion = usage.completion_tokens ?? 0;
  const cached = Math.min(usage.cached_tokens ?? 0, prompt);
  const billablePrompt = prompt - cached;
  const cost =
    (billablePrompt / 1_000_000) * inPrice +
    (cached / 1_000_000) * inPrice * 0.1 +
    (completion / 1_000_000) * outPrice;
  return Math.round(cost * 1e8) / 1e8;
}

function _periodKey(isoTs: string): string {
  return isoTs ? isoTs.slice(0, 7) : "";
}

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
            monthly_limit INTEGER DEFAULT 1000000, -- 1M tokens default
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

    // Roll over the monthly counter when the billing period changes.
    let used = row.used_this_month;
    const now = new Date().toISOString();
    if (_periodKey(row.last_reset) !== _periodKey(now)) {
      conn
        .prepare("UPDATE subscriptions SET used_this_month = 0, last_reset = ? WHERE user_token = ?")
        .run(now, token);
      used = 0;
    }

    if (row.status !== "active") {
      return { status: row.status, message: "Subscription is not active." };
    }

    if (used >= row.monthly_limit) {
      return { status: "over_limit", message: "Monthly token limit reached." };
    }

    return { status: "active", used, limit: row.monthly_limit };
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

/** Meters the request, stores the estimated cost, and updates the monthly
 *  balance. Returns the estimated USD cost of the request. */
export function log_usage(token: string, provider: string, model: string, usage: UsagePayload): number {
  if (!existsSync(BILLING_DB)) {
    init_billing();
  }
  const timestamp = new Date().toISOString();
  const prompt = usage.prompt_tokens ?? 0;
  const completion = usage.completion_tokens ?? 0;
  // Fall back to prompt+completion when the provider omits total_tokens.
  const total = usage.total_tokens ?? prompt + completion;
  const cached = usage.cached_tokens ?? 0;
  const cost = compute_cost(model, usage);

  const conn = createDatabase(BILLING_DB);
  try {
    // 1. Log detailed record (now including the estimated cost)
    conn
      .prepare(`
            INSERT INTO usage_logs (user_token, timestamp, provider, model, prompt_tokens, completion_tokens, total_tokens, cached_tokens, estimated_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        `)
      .run(token, timestamp, provider, model, prompt, completion, total, cached, cost);

    // 2. Update monthly balance. Ensure a subscription row exists so usage is
    //    always counted; new rows are 'inactive' to preserve fail-closed auth.
    const res = conn
      .prepare(`
            UPDATE subscriptions
            SET used_this_month = used_this_month + ?
            WHERE user_token = ?
        `)
      .run(total, token);
    if (res.changes === 0) {
      conn
        .prepare(`
            INSERT INTO subscriptions (user_token, status, used_this_month, last_reset)
            VALUES (?, 'inactive', ?, ?)
        `)
        .run(token, total, timestamp);
    }
  } finally {
    conn.close();
  }
  return cost;
}
