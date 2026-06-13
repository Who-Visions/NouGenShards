/** Port of tests/test_graph.py — Graph Memory latent mesh (better-sqlite3 backend). */
import { test } from "node:test";
import assert from "node:assert/strict";
import { isolateEnv } from "./_helpers.js";

isolateEnv("ngs-graph-");
const core = await import("../nougen_shards/core.js");
const graph = await import("../nougen_shards/graph.js");
core.init_db(1);

/**
 * Capture three shards and return [id, db_index] for each. TS tests share one
 * vault (unlike Python's per-test fixture), so each call uses a unique >=3-char
 * tag (single digits would be dropped by the FTS sub-trigram filter) plus a role
 * word, guaranteeing retrieve() resolves the exact shard from this call.
 */
let _n = 0;
function makeThree(): Array<[number, number]> {
  const tag = `mk${String(_n++).padStart(3, "0")}`; // e.g. "mk000" — unique, >=3 chars
  core.capture("FIX", `Fix ${tag}`, `Fixed the JWT expiry check ${tag} fixrole.`);
  core.capture("FILE", `File ${tag}`, `The auth middleware source ${tag} filerole.`);
  core.capture("DECISION", `Decision ${tag}`, `Switch JWT signing to RS256 ${tag} decrole.`);
  const a = core.retrieve(`${tag} fixrole`)[0];
  const b = core.retrieve(`${tag} filerole`)[0];
  const c = core.retrieve(`${tag} decrole`)[0];
  return [
    [a.id, a._db_index],
    [b.id, b._db_index],
    [c.id, c._db_index],
  ];
}

test("link_shards creates an edge and edge_count reflects it", () => {
  const [[a, adb], [b, bdb]] = makeThree();
  const before = graph.edge_count();
  assert.equal(graph.link_shards(a, b, "touches", adb, bdb), true);
  assert.equal(graph.edge_count(), before + 1);
});

test("link is idempotent on (src,dst,relation)", () => {
  const [[a, adb], [b, bdb]] = makeThree();
  assert.equal(graph.link_shards(a, b, "touches", adb, bdb), true);
  assert.equal(graph.link_shards(a, b, "touches", adb, bdb), false);
});

test("self-link is rejected", () => {
  const [[a, adb]] = makeThree();
  assert.equal(graph.link_shards(a, a, "relates", adb, adb), false);
});

test("link to a missing shard is rejected", () => {
  const [[a, adb]] = makeThree();
  assert.equal(graph.link_shards(a, 99999, "relates", adb, 1), false);
});

test("related_shards follows edges in both directions", () => {
  const [[a, adb], [b, bdb], [c, cdb]] = makeThree();
  graph.link_shards(a, b, "touches", adb, bdb);
  graph.link_shards(a, c, "caused_by", adb, cdb);

  const rel = graph.related_shards(a, adb);
  const titles = new Set(rel.map((r) => r.title));
  assert.ok([...titles].some((t) => String(t).startsWith("File ")));
  assert.ok([...titles].some((t) => String(t).startsWith("Decision ")));

  // c has only an inbound edge from a — undirected recall still surfaces a.
  const relC = graph.related_shards(c, cdb);
  assert.ok(relC.some((r) => String(r.title).startsWith("Fix ") && r.direction === "in"));
});

test("related_shards relation filter narrows results", () => {
  const [[a, adb], [b, bdb], [c, cdb]] = makeThree();
  graph.link_shards(a, b, "touches", adb, bdb);
  graph.link_shards(a, c, "caused_by", adb, cdb);

  const onlyTouches = graph.related_shards(a, adb, "touches");
  assert.equal(onlyTouches.length, 1);
  assert.ok(String(onlyTouches[0].title).startsWith("File "));
});

test("bidirectional link writes two edges", () => {
  const [[a, adb], [b, bdb]] = makeThree();
  const before = graph.edge_count();
  assert.equal(graph.link_shards(a, b, "relates", adb, bdb, true), true);
  assert.equal(graph.edge_count(), before + 2);
});
