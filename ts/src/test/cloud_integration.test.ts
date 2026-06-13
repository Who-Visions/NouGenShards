/**
 * Port of tests/test_cloud_integration.py — cloud LLM clients and auth logic.
 *
 * Python mocks urllib.request.urlopen; the TS port uses async fetch, so each
 * test installs a mockFetch responder and awaits the async chat() method.
 * The "no key" test relies on env isolation: with no api_key passed and an empty
 * isolated vault, keymaker.get_secret() returns null (DB doesn't exist), so the
 * clients report not-alive and return the "Error: ... Key missing." strings.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { isolateEnv, mockFetch } from "./_helpers.js";

isolateEnv("ngs-cloud-");
const { OpenAIClient, AnthropicClient, GeminiClient, HuggingFaceClient } = await import(
  "../nougen_shards/models_client.js"
);

test("openai_client_chat", async () => {
  const restore = mockFetch(() => ({
    status: 200,
    json: { choices: [{ message: { content: "Hello from OpenAI" } }] },
  }));
  try {
    const client = new OpenAIClient("test-key");
    const resp = await client.chat("gpt-4o", [{ role: "user", content: "hi" }]);
    assert.equal(resp, "Hello from OpenAI");
  } finally {
    restore();
  }
});

test("anthropic_client_chat", async () => {
  const restore = mockFetch(() => ({
    status: 200,
    json: { content: [{ text: "Hello from Anthropic" }] },
  }));
  try {
    const client = new AnthropicClient("test-key");
    const resp = await client.chat("claude-3-5-sonnet-latest", [{ role: "user", content: "hi" }]);
    assert.equal(resp, "Hello from Anthropic");
  } finally {
    restore();
  }
});

test("gemini_client_chat", async () => {
  const restore = mockFetch(() => ({
    status: 200,
    json: { candidates: [{ content: { parts: [{ text: "Hello from Gemini" }] } }] },
  }));
  try {
    const client = new GeminiClient("test-key");
    const resp = await client.chat("gemini-1.5-flash", [{ role: "user", content: "hi" }]);
    assert.equal(resp, "Hello from Gemini");
  } finally {
    restore();
  }
});

test("huggingface_client_chat", async () => {
  const restore = mockFetch(() => ({
    status: 200,
    json: [{ generated_text: "Hello from Hugging Face" }],
  }));
  try {
    const client = new HuggingFaceClient("test-key");
    const resp = await client.chat("meta-llama/Llama-3.2-3B-Instruct", [{ role: "user", content: "hi" }]);
    assert.equal(resp, "Hello from Hugging Face");
  } finally {
    restore();
  }
});

test("cloud_clients_no_key", async () => {
  // No api_key passed; isolated env => keymaker.get_secret returns null.
  const clients = [new OpenAIClient(), new AnthropicClient(), new GeminiClient(), new HuggingFaceClient()];
  for (const client of clients) {
    assert.equal(client.is_alive(), false);
    const resp = await client.chat("any-model", []);
    assert.ok(resp.includes("Error:"));
    assert.ok(resp.includes("Key missing"));
  }
});
