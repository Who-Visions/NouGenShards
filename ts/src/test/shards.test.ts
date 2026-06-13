/** Port of tests/test_shards.py — advanced memory substrate (better-sqlite3 backend). */
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { isolateEnv } from "./_helpers.js";

isolateEnv("ngs-shards-");
const shards = await import("../nougen_shards/core.js");
shards.init_db(1);

test("init_db creates trigram FTS5 table", () => {
  assert.ok(existsSync(shards.get_db_path(1)));
  const conn = shards.get_connection(1);
  const res = conn
    .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='shards_fts'")
    .get();
  assert.notEqual(res, undefined);
  conn.close();
});

test("capture and retrieve with Bayesian scoring", () => {
  shards.capture("KNOWLEDGE", "Important Tool", "This tool works perfectly for automation.");
  const res = shards.retrieve("automation");
  assert.ok(res.length >= 1);

  shards.mark_shard(res[0].id, true); // raise Bayesian prior

  shards.capture("KNOWLEDGE", "New Tool", "This is another tool for automation.");
  const results = shards.retrieve("automation");
  assert.ok(results.length >= 2);
  // Higher utility prior should rank "Important Tool" first.
  assert.equal(results[0].title, "Important Tool");
  assert.ok("final_score" in results[0]);
});

test("trigram n-gram substring recall", () => {
  shards.capture("TECH", "Substrate", "The underlying infrastructure is a substrate.");
  const results = shards.retrieve("substrate");
  assert.ok(results.length >= 1);
  assert.ok(results[0].title.includes("Substrate"));
});

test("vector similarity via embeddings", () => {
  shards.capture("VEC", "Vector A", "Content A", null, [1.0, 0.0, 0.0]);
  shards.capture("VEC", "Vector B", "Content B", null, [0.9, 0.1, 0.0]);
  shards.capture("VEC", "Vector C", "Content C", null, [0.0, 1.0, 0.0]);
  const results = shards.retrieve("Content", 3, [1.0, 0.1, 0.0]);
  assert.ok(results.length >= 2);
  const titles = results.map((r) => r.title);
  assert.ok(titles.includes("Vector A"));
  assert.ok(titles.includes("Vector B"));
});

test("multi-db deterministic routing exposes _db_index", () => {
  shards.capture("ROUTE", "Alpha", "Unique experience Alpha");
  shards.capture("ROUTE", "Beta", "Unique experience Beta");
  const res1 = shards.retrieve("Alpha")[0];
  const res2 = shards.retrieve("Beta")[0];
  assert.ok("_db_index" in res1);
  assert.ok("_db_index" in res2);
});

test("mark_shard outcome loop raises utility prior", () => {
  shards.capture("TEST", "Status", "Success scenario");
  const res = shards.retrieve("scenario")[0];
  const initial = res.utility_score;
  shards.mark_shard(res.id, true);
  const updated = shards.retrieve("scenario")[0];
  assert.ok(updated.utility_score > initial);
});

test("multi-word FTS query matches via real BM25 (bm25(shards_fts) fix)", () => {
  // Regression guard: retrieve() used bm25(f) on a table alias, which threw and
  // silently fell back to LIKE — so multi-word queries (a non-contiguous phrase)
  // returned nothing. With bm25(shards_fts) the FTS5 path runs and ANDs the terms.
  shards.capture("DOC", "River Fox Note", "The quick brown fox jumps over the lazy dog near the river bank.");
  const found = shards.retrieve("brown fox river");
  assert.ok(found.length >= 1, "multi-word FTS query should match");
  assert.ok(found[0].content.includes("brown"));
});
