/**
 * Port of tests/test_nougen_context.py — session context DB + sandbox execution.
 *
 * nougen_context.ts resolves SESSION_DB_PATH from homedir() at module-load time
 * (under ~/.nougen/context/session.db), and the sandbox capability tests need
 * NOUGEN_ENABLE_SANDBOX=1 — the TS analogue of the Python autouse `mock_db_path`
 * fixture (tmp_path + monkeypatch.setattr SESSION_DB_PATH + setenv). So we set
 * the env BEFORE importing the modules.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { isolateEnv } from "./_helpers.js";

isolateEnv("ngs-ctx-");
// Mirror the autouse fixture: enable the sandbox gate for the capability tests.
process.env.NOUGEN_ENABLE_SANDBOX = "1";

const nougen_context = await import("../nougen_shards/nougen_context.js");
const nougen_sandbox = await import("../nougen_shards/nougen_sandbox.js");

test("test_sandbox_disabled_by_default", () => {
  // By default the sandbox refuses to run arbitrary code (security gate).
  const prev = process.env.NOUGEN_ENABLE_SANDBOX;
  delete process.env.NOUGEN_ENABLE_SANDBOX;
  try {
    const result = nougen_sandbox.execute_sandboxed("print('should not run')", "python");
    assert.ok(result.includes("disabled by default"));
  } finally {
    process.env.NOUGEN_ENABLE_SANDBOX = prev;
  }
});

test("test_sandbox_trusted_bypasses_gate", () => {
  // Trusted internal callers may run even when the gate is off.
  const prev = process.env.NOUGEN_ENABLE_SANDBOX;
  delete process.env.NOUGEN_ENABLE_SANDBOX;
  try {
    // Use JavaScript so the always-present Node runtime executes it (the Python
    // interpreter isn't guaranteed on PATH in the sandbox's minimal env).
    const result = nougen_sandbox.execute_sandboxed("console.log('trusted ok')", "javascript", 10, true);
    assert.equal(result, "trusted ok");
  } finally {
    process.env.NOUGEN_ENABLE_SANDBOX = prev;
  }
});

test("test_init_context_db", () => {
  nougen_context.init_context_db(true);
  assert.ok(existsSync(nougen_context.SESSION_DB_PATH));

  const conn = nougen_context.get_context_connection();
  const rows = conn
    .prepare("SELECT name FROM sqlite_master WHERE type='table';")
    .all() as Record<string, any>[];
  const tables = rows.map((row) => row.name);
  assert.ok(tables.includes("ctx_events"));
  assert.ok(tables.includes("ctx_sandbox"));
  assert.ok(tables.includes("ctx_session"));
  conn.close();
});

test("test_log_and_search_event", () => {
  nougen_context.init_context_db(true);
  nougen_context.log_event("test_type", "Unique content for search", { meta: "data" });

  const results = nougen_context.search_context("Unique");
  assert.equal(results.length, 1);
  assert.equal(results[0].content, "Unique content for search");
  assert.equal(results[0].type, "test_type");
});

test("test_search_events_filters_query", () => {
  nougen_context.init_context_db(true);
  nougen_context.log_event("alpha_type", "needle context payload");
  nougen_context.log_event("beta_type", "irrelevant payload");

  const results = nougen_context.search_events("needle", 10);

  assert.equal(results.length, 1);
  assert.equal(results[0].event_type, "alpha_type");
  assert.equal(results[0].description, "needle context payload");
});

test("test_sandbox_store_fetch", () => {
  nougen_context.init_context_db(true);
  const test_data = "large raw output data";
  nougen_context.store_sandbox("handle_1", test_data, "small summary");

  const fetched_data = nougen_context.fetch_sandbox("handle_1");
  assert.equal(fetched_data, test_data);

  // Test OR REPLACE
  const new_data = "new updated data";
  nougen_context.store_sandbox("handle_1", new_data);
  assert.equal(nougen_context.fetch_sandbox("handle_1"), new_data);
});

test("test_execute_sandboxed_python", () => {
  const code = "print('hello from python')";
  const result = nougen_sandbox.execute_sandboxed(code, "python");
  // Requires a python interpreter on PATH; skip if absent (no TS analogue otherwise).
  if (!nougen_sandbox._is_tool_available("python") && !nougen_sandbox._is_tool_available("python3")) {
    return; // node:test treats a returning test as passing (pytest.skip analogue)
  }
  assert.equal(result, "hello from python");
});

test("test_execute_sandboxed_unsupported", () => {
  const result = nougen_sandbox.execute_sandboxed("code", "brainfuck");
  assert.ok(result.includes("Error: Unsupported language"));
});

test("test_execute_sandboxed_timeout", () => {
  // A 2s sleep against a 1s timeout should trip the timeout guard.
  if (!nougen_sandbox._is_tool_available("python") && !nougen_sandbox._is_tool_available("python3")) {
    return; // no python interpreter -> cannot exercise the timeout path
  }
  const code = "import time; time.sleep(2)";
  const result = nougen_sandbox.execute_sandboxed(code, "python", 1);
  assert.ok(result.includes("Error: Execution timed out"));
});

test("test_execute_sandboxed_javascript", () => {
  // Test JavaScript execution if node/bun is available.
  if (nougen_sandbox._is_tool_available("node") || nougen_sandbox._is_tool_available("bun")) {
    const code = "console.log('hello from js')";
    const result = nougen_sandbox.execute_sandboxed(code, "javascript");
    assert.equal(result, "hello from js");
  }
  // else: pytest.skip analogue — nothing to assert without a JS runtime.
});
