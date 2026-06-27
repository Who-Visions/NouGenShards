/**
 * Tests for billing cost computation, monthly reset, and usage metering.
 * (TS mirror of tests/test_billing.py)
 */
import { isolateEnv } from "./_helpers.js";
isolateEnv("ngs-billing-");

import test from "node:test";
import assert from "node:assert/strict";
import { createDatabase } from "../nougen_shards/_db.js";

const billing = await import("../nougen_shards/billing.js");
billing.init_billing();

test("compute_cost free model is zero", () => {
  const usage = { prompt_tokens: 1000, completion_tokens: 1000, cached_tokens: 0 };
  assert.equal(billing.compute_cost("google/gemma-4-31b-it:free", usage), 0.0);
});

test("compute_cost paid model", () => {
  const usage = { prompt_tokens: 1_000_000, completion_tokens: 1_000_000, cached_tokens: 0 };
  assert.equal(billing.compute_cost("anthropic/claude-3.5-sonnet", usage), 18.0);
});

test("compute_cost cached discount", () => {
  const usage = { prompt_tokens: 1_000_000, completion_tokens: 0, cached_tokens: 1_000_000 };
  assert.equal(billing.compute_cost("anthropic/claude-3.5-sonnet", usage), 0.3);
});

test("log_usage stores cost and counts usage", () => {
  const token = "user-1";
  const cost = billing.log_usage(token, "openrouter", "anthropic/claude-3.5-sonnet", {
    prompt_tokens: 1_000_000,
    completion_tokens: 0,
    total_tokens: 1_000_000,
    cached_tokens: 0,
  });
  assert.equal(cost, 3.0);
  const conn = createDatabase(billing.BILLING_DB);
  const log = conn.prepare("SELECT * FROM usage_logs WHERE user_token = ?").get(token) as any;
  const sub = conn.prepare("SELECT * FROM subscriptions WHERE user_token = ?").get(token) as any;
  conn.close();
  assert.equal(log.estimated_cost, 3.0);
  assert.equal(sub.used_this_month, 1_000_000);
  assert.equal(sub.status, "inactive");
});

test("total_tokens fallback to prompt+completion", () => {
  const token = "user-2";
  billing.log_usage(token, "openrouter", "x:free", { prompt_tokens: 10, completion_tokens: 5 });
  const conn = createDatabase(billing.BILLING_DB);
  const sub = conn.prepare("SELECT * FROM subscriptions WHERE user_token = ?").get(token) as any;
  conn.close();
  assert.equal(sub.used_this_month, 15);
});

test("monthly reset rolls over the counter", () => {
  const token = "user-3";
  const conn = createDatabase(billing.BILLING_DB);
  conn
    .prepare(
      "INSERT INTO subscriptions (user_token, status, monthly_limit, used_this_month, last_reset) VALUES (?, 'active', 1000, 999, ?)",
    )
    .run(token, "2000-01-01T00:00:00Z");
  conn.close();
  const res = billing.check_subscription(token);
  assert.equal(res.status, "active");
  assert.equal(res.used, 0);
});
