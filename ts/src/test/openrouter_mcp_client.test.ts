/**
 * Port of tests/test_openrouter_mcp_client.py — OpenRouter MCP bridge.
 *
 * The Python tests patch the MCP `ClientSession`/`stdio_client` and the
 * module-level `call_openrouter`. In the TS port the MCP SDK `Client` and
 * `StdioClientTransport` cannot be spun up live in a unit test, and the module
 * binds `call_openrouter` internally (no monkeypatch seam). So we test at the
 * boundary instead:
 *   - the exported config/allowlist surface (MCP_CONFIG_PATH, MCP_SERVER_ALLOWLIST)
 *   - initialize_servers' "config not found" branch (steered via env)
 *   - get_openai_tool_definitions (pure)
 *   - execute_tool success by injecting a fake session/tools_map
 *   - execute_tool not-found branch
 *   - shutdown by injecting a fake transport with a close() spy
 *   - run_query's no-tool-calls path (fetch mocked; config absent => no tools)
 * The full two-call tool-execution loop in run_query requires a live MCP server
 * session and is covered here only by its no-tool-calls branch (see comment).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import * as path from "node:path";
import { isolateEnv, mockFetch, captureStdout } from "./_helpers.js";

const root = isolateEnv("ngs-ormcp-");
// Force MCP_CONFIG_PATH (resolved at module load) to a guaranteed-missing file so
// initialize_servers / run_query hit the "config not found" branch deterministically.
process.env.NOUGEN_MCP_CONFIG_PATH = path.join(root, "does-not-exist-mcp.json");

const mod = await import("../nougen_shards/openrouter_mcp_client.js");
const { MultiMCPBridge, run_query, MCP_CONFIG_PATH, MCP_SERVER_ALLOWLIST } = mod;

test("config surface and allowlist", () => {
  // MCP_CONFIG_PATH honored the env override.
  assert.equal(MCP_CONFIG_PATH, process.env.NOUGEN_MCP_CONFIG_PATH);
  // Allowlist gates which servers connect (Python test asserted exa in, others out).
  assert.ok(MCP_SERVER_ALLOWLIST.has("exa"));
  assert.ok(!MCP_SERVER_ALLOWLIST.has("ignored_server"));
});

test("initialize_servers_no_file", async () => {
  const bridge = new MultiMCPBridge();
  const out = await captureStdout(async () => {
    await bridge.initialize_servers();
  });
  assert.ok(out.includes("[!] Config not found"));
  // No servers were registered.
  assert.equal(Object.keys(bridge.sessions).length, 0);
  assert.equal(Object.keys(bridge.tools_map).length, 0);
});

test("get_openai_tool_definitions", () => {
  const bridge = new MultiMCPBridge();
  const mock_tool = {
    name: "test_tool",
    description: "test description",
    inputSchema: { properties: { a: {} }, required: ["a"] },
  };
  bridge.tools_map["test_tool"] = ["exa", mock_tool];

  const tools = bridge.get_openai_tool_definitions();
  assert.equal(tools.length, 1);
  assert.equal(tools[0].function.name, "test_tool");
  assert.deepEqual(tools[0].function.parameters.required, ["a"]);
});

test("execute_tool_success", async () => {
  const bridge = new MultiMCPBridge();
  // Inject a fake MCP session at the SDK Client boundary.
  const fake_session: any = {
    callTool: async (_args: any) => ({ content: [{ type: "text", text: "tool output" }] }),
  };
  bridge.sessions["exa"] = fake_session;
  bridge.tools_map["test_tool"] = ["exa", { name: "test_tool" }];

  const result = await bridge.execute_tool("test_tool", { a: "b" });
  assert.equal(result, "tool output");
});

test("execute_tool_not_found", async () => {
  const bridge = new MultiMCPBridge();
  const result = await bridge.execute_tool("missing_tool", {});
  assert.ok(result.includes("not found"));
});

test("shutdown closes transports", async () => {
  const bridge = new MultiMCPBridge();
  let closed = 0;
  const fake_transport: any = {
    close: async () => {
      closed += 1;
    },
  };
  bridge.transports.push(fake_transport);
  await bridge.shutdown();
  assert.equal(closed, 1);
});

test("run_query no-tool-calls path", async () => {
  // Config absent (env-steered) => bridge has zero tools; call_openrouter (fetch)
  // returns a plain assistant message with no tool_calls, so run_query prints the
  // direct response and shuts down. The tool-execution loop requires a live MCP
  // session and is not exercisable without one.
  const restore = mockFetch(() => ({
    status: 200,
    json: { choices: [{ message: { role: "assistant", content: "Final answer", tool_calls: null } }] },
  }));
  try {
    // call_openrouter needs an API key to reach fetch; inject one for the run.
    process.env.OPENROUTER_API_KEY = "fake-key";
    const out = await captureStdout(async () => {
      await run_query("test query");
    });
    assert.ok(out.includes("Final answer"));
  } finally {
    restore();
    delete process.env.OPENROUTER_API_KEY;
  }
});
