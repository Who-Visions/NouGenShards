import test from "node:test";
import assert from "node:assert/strict";
import { isYouTube, parseMcpBody, mcpCall, shardRef } from "../nougen.js";

const reply = (body, { ok = true, status = 200, ct = "application/json" } = {}) => async () => ({
  ok, status, headers: { get: () => ct }, text: async () => body,
});
const result = (obj, isError = false) => JSON.stringify({ jsonrpc: "2.0", id: 1, result: { content: [{ type: "text", text: JSON.stringify(obj) }], isError } });

test("isYouTube accepts youtube hosts only", () => {
  assert.ok(isYouTube("https://www.youtube.com/watch?v=abc"));
  assert.ok(isYouTube("https://youtu.be/abc"));
  assert.ok(!isYouTube("https://evil.example/?u=youtube.com"));
  assert.ok(!isYouTube("not a url"));
});
test("parseMcpBody reads plain JSON and SSE frames", () => {
  assert.equal(parseMcpBody('{"a":1}').a, 1);
  assert.equal(parseMcpBody('event: message\ndata: {"a":2}\n\n', "text/event-stream").a, 2);
});
test("mcpCall returns the parsed tool result", async () => {
  const out = await mcpCall("https://h", "t", "x", {}, reply(result({ id: 7 })));
  assert.equal(out.id, 7);
});
test("mcpCall throws on tool errors, protocol errors and HTTP errors (negative controls)", async () => {
  await assert.rejects(() => mcpCall("https://h", "t", "x", {}, reply(result({ e: 1 }, true))));
  await assert.rejects(() => mcpCall("https://h", "t", "x", {}, reply(JSON.stringify({ error: { message: "boom" } }))), /boom/);
  await assert.rejects(() => mcpCall("https://h", "t", "x", {}, reply("{}", { ok: false, status: 401 })), /401/);
});
test("mcpCall sends the token header and tools/call body", async () => {
  let seen;
  await mcpCall("https://h", "tok", "create_destiny", { a: 1 }, async (url, init) => { seen = { url, init }; return reply(result({}))(); });
  assert.equal(seen.url, "https://h/mcp/");
  assert.equal(seen.init.headers["X-NGS-Token"], "tok");
  assert.equal(JSON.parse(seen.init.body).params.name, "create_destiny");
});
test("shardRef needs captured:true and a shard id", () => {
  assert.equal(shardRef({ captured: true, shard_id: 5, db_index: 3 }), "3:5");
  assert.equal(shardRef({ captured: true, shard_id: 5 }), "5");
  assert.equal(shardRef({ captured: false, shard_id: 5 }), null);
  assert.equal(shardRef({ captured: true }), null);
});
