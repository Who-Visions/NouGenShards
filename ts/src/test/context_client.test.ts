/**
 * Port of tests/test_context_client.py — context-mode MCP client.
 *
 * Python patches stdio_client / ClientSession and (for the dispatch tests)
 * `client._call_tool`. The TS port builds the MCP `Client`/`StdioClientTransport`
 * inside `_call_tool`, so we can't inject a fake session there. Adaptations:
 *   - The five dispatch tests (execute/execute_file/search/stats/insight) override
 *     the instance's `_call_tool` (the faithful equivalent of patch.object) and
 *     assert the return value plus the tool name + arguments dispatched.
 *   - The Python success path (`test_call_tool_success`) requires a live MCP
 *     session; it is covered here by the dispatch-argument assertions instead.
 *   - The two Python error-path tests both collapse to the TS single catch, which
 *     returns "Unexpected error in Context Mode: <message>". One test drives the
 *     real catch by pointing params at an unspawnable command. (TS has no separate
 *     "Error: Context Mode failed:" RuntimeError branch.)
 *   - CONTEXT_MODE_PARAMS construction (start.mjs path resolution) is asserted.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import * as path from "node:path";
import { isolateEnv } from "./_helpers.js";

isolateEnv("ngs-ctx-");
const { ContextClient, CONTEXT_MODE_PARAMS } = await import("../nougen_shards/context_client.js");

test("CONTEXT_MODE_PARAMS construction", () => {
  // node <start.mjs> <watchtower_root>
  assert.equal(CONTEXT_MODE_PARAMS.command, "node");
  assert.equal(CONTEXT_MODE_PARAMS.args?.length, 2);
  assert.ok(String(CONTEXT_MODE_PARAMS.args?.[0]).endsWith("start.mjs"));
});

test("execute dispatches ctx_execute", async () => {
  const client: any = new ContextClient();
  let call: any = null;
  client._call_tool = async (tool: string, args: Record<string, any>) => {
    call = { tool, args };
    return "executed";
  };
  const res = await client.execute("print(1)");
  assert.equal(res, "executed");
  assert.equal(call.tool, "ctx_execute");
  assert.equal(call.args.code, "print(1)");
});

test("execute_file dispatches ctx_execute_file", async () => {
  const client: any = new ContextClient();
  let call: any = null;
  client._call_tool = async (tool: string, args: Record<string, any>) => {
    call = { tool, args };
    return "file executed";
  };
  const res = await client.execute_file("test.js");
  assert.equal(res, "file executed");
  assert.equal(call.tool, "ctx_execute_file");
  assert.equal(call.args.path, "test.js");
});

test("search dispatches ctx_search", async () => {
  const client: any = new ContextClient();
  let call: any = null;
  client._call_tool = async (tool: string, args: Record<string, any>) => {
    call = { tool, args };
    return "found results";
  };
  const res = await client.search("query");
  assert.equal(res, "found results");
  assert.equal(call.tool, "ctx_search");
  assert.equal(call.args.query, "query");
});

test("stats dispatches ctx_stats", async () => {
  const client: any = new ContextClient();
  let call: any = null;
  client._call_tool = async (tool: string, args: Record<string, any>) => {
    call = { tool, args };
    return "stats data";
  };
  const res = await client.stats();
  assert.equal(res, "stats data");
  assert.equal(call.tool, "ctx_stats");
});

test("insight dispatches ctx_insight", async () => {
  const client: any = new ContextClient();
  let call: any = null;
  client._call_tool = async (tool: string, args: Record<string, any>) => {
    call = { tool, args };
    return "architectural insight";
  };
  const res = await client.insight("how it works");
  assert.equal(res, "architectural insight");
  assert.equal(call.tool, "ctx_insight");
  assert.equal(call.args.query, "how it works");
});

test("_call_tool returns the context-mode error string on connect failure", async () => {
  // Point params at an unspawnable command so the real transport connect fails and
  // the single catch returns the "Unexpected error in Context Mode:" string.
  // (TS collapses the Python RuntimeError + general-Exception branches into one.)
  const client: any = new ContextClient({
    command: path.join("definitely", "missing", "nougen-no-such-binary"),
    args: [],
  });
  const result = await client._call_tool("ctx_stats", {});
  assert.ok(result.includes("Unexpected error in Context Mode:"));
});
