/** Port of tests/test_history_engine.py — HistoryEngine growth/utility analytics. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { isolateEnv } from "./_helpers.js";

isolateEnv("ngs-history-");
const shards = await import("../nougen_shards/core.js");
const { HistoryEngine } = await import("../nougen_shards/history.js");
shards.init_db(1);

test("history engine tracks capture/mark and reports stats", () => {
  shards.capture(
    "RESEARCH",
    "History Test Shard",
    "This is a unit of experience for history tracking verification.",
    ["test", "history"],
  );

  const results = shards.retrieve("history tracking", 1);
  assert.ok(results.length >= 1, "expected a retrievable shard");

  const shardId = results[0].id;
  shards.mark_shard(shardId, true);

  const growth = HistoryEngine.get_growth_rate("24h");
  assert.ok(growth.new_shards >= 1);
  assert.ok(growth.total_shards >= 1);

  // A worked-mark produces a positive utility delta in the window.
  const utility = HistoryEngine.get_utility_stats("24h");
  assert.ok(utility > 0);

  const top = HistoryEngine.get_top_shards("24h");
  assert.ok(Array.isArray(top));

  // export_stats_json returns valid JSON with the period echoed back.
  const exported = JSON.parse(HistoryEngine.export_stats_json("24h"));
  assert.equal(exported.period, "24h");
});
