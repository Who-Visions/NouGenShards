/**
 * Port of tests/test_openrouter_router.py — OpenRouter production router.
 *
 * Python's RouterConfig dataclass is `make_router_config()` here (factory mimic).
 * The pure functions (build_cache_friendly_messages, make_session_id) need no
 * env isolation. The OpenRouterClient.chat_with_fallback test mocks global fetch
 * (the TS port uses async fetch instead of Python's urllib).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { isolateEnv, mockFetch } from "./_helpers.js";

// Isolate before importing modules that resolve the vault/home at load time
// (models_client -> keymaker reads NOUGEN_VAULT_DIR). The router pure fns don't
// need it, but the OpenRouterClient construction touches keymaker.get_secret.
isolateEnv("ngs-router-");
const router = await import("../nougen_shards/router.js");
const { OpenRouterClient } = await import("../nougen_shards/models_client.js");

test("router_config_defaults", () => {
  const config = router.make_router_config();
  assert.equal(config.primary_model, "openrouter/auto");
  assert.ok(config.fallback_models.includes("anthropic/claude-3.5-sonnet"));
  assert.equal(config.enable_response_healing, true);
});

test("cache_friendly_messages", () => {
  const sys_prompt = "Permanent System Prompt";
  const task_msgs = [{ role: "user", content: "Task message" }];
  const messages = router.build_cache_friendly_messages(sys_prompt, task_msgs);

  assert.equal(messages.length, 2);
  assert.equal(messages[0].role, "system");
  assert.equal(messages[0].content, sys_prompt);
  assert.equal(messages[1].content, "Task message");
});

test("make_session_id", () => {
  const sid = router.make_session_id("project-x", "agent-y");
  assert.equal(sid, "nougen:project-x:agent-y");

  const sid_with_thread = router.make_session_id("project-x", "agent-y", "thread-z");
  assert.ok(sid_with_thread.startsWith("nougen:project-x:agent-y:"));
  assert.equal(sid_with_thread.length, "nougen:project-x:agent-y:".length + 8);
});

test("openrouter_chat_with_fallback", async () => {
  // Mirror the Python mock: urlopen -> fetch. Capture the request body to assert
  // the outgoing payload (model + non-empty fallback models list).
  let captured_body: any = null;
  const restore = mockFetch((_url, init) => {
    captured_body = JSON.parse(init.body);
    return {
      status: 200,
      json: {
        choices: [{ message: { content: "Hello" }, finish_reason: "stop" }],
        model: "anthropic/claude-3.5-sonnet",
        usage: { total_tokens: 10 },
      },
    };
  });
  try {
    // Inject the api_key directly so OpenRouterClient is "alive" without a vault.
    const client = new OpenRouterClient("fake-key");
    const res = await client.chat_with_fallback("openrouter/auto", [{ role: "user", content: "Hi" }]);

    assert.equal(res.content, "Hello");
    assert.equal(res.model, "anthropic/claude-3.5-sonnet");
    assert.equal(res.usage.total_tokens, 10);

    // Verify the outgoing request payload.
    assert.equal(captured_body.model, "openrouter/auto");
    assert.ok("models" in captured_body);
    assert.ok(captured_body.models.length > 0);
  } finally {
    restore();
  }
});
