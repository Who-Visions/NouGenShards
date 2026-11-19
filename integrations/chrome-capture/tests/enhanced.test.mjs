import test from "node:test";
import assert from "node:assert/strict";
import { buildPayload } from "../capture.js";
import { checkNodeHealth, searchShards } from "../nougen.js";

test("buildPayload includes extraTags and author metadata", () => {
  const p = buildPayload({
    selection: "Agentic intelligence running live.",
    url: "https://nougen.ai/doc",
    title: "Doc Title",
    extraTags: ["custom-tag", "chrome-capture"], // duplicate should be deduplicated
    author: "Dav3",
    now: new Date("2026-10-07T00:00:00Z"),
  });
  assert.ok(p);
  assert.equal(p.tags.includes("custom-tag"), true);
  assert.equal(p.tags.filter((t) => t === "chrome-capture").length, 1);
  assert.ok(p.content.includes("Author: Dav3"));
  assert.ok(p.content.includes("Kind: selection"));
});

test("checkNodeHealth parses status payload correctly", async () => {
  const mockFetch = async (url) => {
    return {
      ok: true,
      status: 200,
      json: async () => ({ status: "ignited", node: "KushBoyGroups-Mac-mini" }),
    };
  };
  const res = await checkNodeHealth("http://127.0.0.1:4444", "tok", mockFetch);
  assert.equal(res.ok, true);
  assert.equal(res.data.status, "ignited");
  assert.equal(res.data.node, "KushBoyGroups-Mac-mini");
});

test("checkNodeHealth handles offline/unreachable node gracefully", async () => {
  const mockFetch = async () => {
    throw new Error("fetch failed ECONNREFUSED");
  };
  const res = await checkNodeHealth("http://127.0.0.1:9999", "tok", mockFetch);
  assert.equal(res.ok, false);
  assert.ok(res.error.includes("ECONNREFUSED"));
});

test("searchShards calls search_shards tool and returns list", async () => {
  const mockFetch = async (_url, init) => {
    const body = JSON.parse(init.body);
    assert.equal(body.method, "tools/call");
    assert.equal(body.params.name, "search_shards");
    return {
      ok: true,
      headers: { get: () => "application/json" },
      text: async () => JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: {
          content: [{ type: "text", text: JSON.stringify([{ id: 42, title: "Test Shard", content: "Memory" }]) }]
        }
      })
    };
  };
  const results = await searchShards("http://127.0.0.1:4444", "tok", "test query", mockFetch);
  assert.equal(results.length, 1);
  assert.equal(results[0].id, 42);
  assert.equal(results[0].title, "Test Shard");
});
