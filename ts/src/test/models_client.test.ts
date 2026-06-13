/**
 * Port of tests/test_models_client.py — local LLM clients (Ollama, LM Studio)
 * and best-available client detection.
 *
 * Python mocks urllib.request.urlopen. This TS port mocks the global `fetch`.
 * Network methods here are async (fetch-based), so every call is awaited.
 *
 * Non-streaming responses use `mockFetch` from _helpers (json/status/text).
 * Streaming responses (`chat(..., stream=true)` and `pull_model`) read
 * `res.body` as a ReadableStream of newline-delimited bytes, so those tests
 * install a local `mockStreamFetch` that supplies a real ReadableStream body.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { mockFetch, captureStdout } from "./_helpers.js";
import {
  OllamaClient,
  LMStudioClient,
  get_best_available_client,
} from "../nougen_shards/models_client.js";

/**
 * Install a fake global fetch whose Response exposes a real ReadableStream
 * `body` of the given lines (each newline-terminated, UTF-8 encoded).
 * Mirrors the Python urlopen mock whose response object iterates byte lines.
 * Returns a restore fn.
 */
function mockStreamFetch(lines: string[]): () => void {
  const orig = globalThis.fetch;
  globalThis.fetch = async () => {
    const enc = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const ln of lines) {
          controller.enqueue(enc.encode(ln + "\n"));
        }
        controller.close();
      },
    });
    return {
      ok: true,
      status: 200,
      json: async () => ({}),
      text: async () => "",
      body,
    } as any;
  };
  return () => {
    globalThis.fetch = orig;
  };
}

/** Install a fetch that always throws (the URLError / ConnectionRefused analogue). */
function mockThrowFetch(): () => void {
  const orig = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("failed");
  };
  return () => {
    globalThis.fetch = orig;
  };
}

// ---------------------------------------------------------------------------
// OllamaClient
// ---------------------------------------------------------------------------

test("ollama_is_alive", async () => {
  // Alive: /api/version returns 200.
  let restore = mockFetch(() => ({ status: 200, json: {} }));
  try {
    const client = new OllamaClient();
    assert.equal(await client.is_alive(), true);
  } finally {
    restore();
  }
  // Dead: fetch throws (ConnectionRefused analogue).
  restore = mockThrowFetch();
  try {
    const client = new OllamaClient();
    assert.equal(await client.is_alive(), false);
  } finally {
    restore();
  }
});

test("ollama_list_models", async () => {
  const restore = mockFetch(() => ({
    json: { models: [{ name: "mdl1" }, { name: "mdl2" }] },
  }));
  try {
    const client = new OllamaClient();
    assert.deepEqual(await client.list_models(), ["mdl1", "mdl2"]);
  } finally {
    restore();
  }
});

test("ollama_chat_no_stream", async () => {
  const restore = mockFetch(() => ({ json: { message: { content: "hello" } } }));
  try {
    const client = new OllamaClient();
    const resp = await client.chat("mdl", [{ role: "user", content: "hi" }], false);
    assert.equal(resp, "hello");
  } finally {
    restore();
  }
});

test("ollama_chat_stream", async () => {
  const restore = mockStreamFetch([
    JSON.stringify({ message: { content: "he" } }),
    JSON.stringify({ message: { content: "llo" } }),
  ]);
  try {
    const client = new OllamaClient();
    let resp = "";
    await captureStdout(async () => {
      resp = await client.chat("mdl", [{ role: "user", content: "hi" }], true);
    });
    assert.equal(resp, "hello");
  } finally {
    restore();
  }
});

test("ollama_chat_error", async () => {
  const restore = mockThrowFetch();
  try {
    const client = new OllamaClient();
    const resp = await client.chat("mdl", [], false);
    assert.ok(resp.includes("Error"));
  } finally {
    restore();
  }
});

test("ollama_find_best_edge_model", async () => {
  const restore = mockFetch(() => ({
    json: { models: [{ name: "llama3" }, { name: "dav1d:e2b" }] },
  }));
  try {
    const client = new OllamaClient();
    assert.equal(await client.find_best_edge_model(), "dav1d:e2b");
  } finally {
    restore();
  }
});

test("ollama_pull_model", async () => {
  const restore = mockStreamFetch([
    JSON.stringify({ status: "downloading", completed: 50, total: 100 }),
    JSON.stringify({ status: "success" }),
  ]);
  try {
    const client = new OllamaClient();
    let ok = false;
    await captureStdout(async () => {
      ok = await client.pull_model("mdl");
    });
    assert.equal(ok, true);
  } finally {
    restore();
  }
});

test("ollama_pull_model_fail", async () => {
  const restore = mockThrowFetch();
  try {
    const client = new OllamaClient();
    let ok = true;
    await captureStdout(async () => {
      ok = await client.pull_model("mdl");
    });
    assert.equal(ok, false);
  } finally {
    restore();
  }
});

test("ollama_list_models_empty", async () => {
  const restore = mockFetch(() => ({ json: {} }));
  try {
    const client = new OllamaClient();
    assert.deepEqual(await client.list_models(), []);
  } finally {
    restore();
  }
});

test("ollama_find_best_edge_model_no_pref", async () => {
  const restore = mockFetch(() => ({ json: { models: [{ name: "random" }] } }));
  try {
    const client = new OllamaClient();
    assert.equal(await client.find_best_edge_model(), "random");
  } finally {
    restore();
  }
});

test("ollama_find_best_edge_model_none", async () => {
  const restore = mockFetch(() => ({ json: { models: [] } }));
  try {
    const client = new OllamaClient();
    assert.equal(await client.find_best_edge_model(), "");
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// LMStudioClient
// ---------------------------------------------------------------------------

test("lmstudio_is_alive", async () => {
  const restore = mockFetch(() => ({ status: 200, json: {} }));
  try {
    const client = new LMStudioClient();
    assert.equal(await client.is_alive(), true);
  } finally {
    restore();
  }
});

test("lmstudio_list_models", async () => {
  const restore = mockFetch(() => ({ json: { data: [{ id: "mdl1" }] } }));
  try {
    const client = new LMStudioClient();
    assert.deepEqual(await client.list_models(), ["mdl1"]);
  } finally {
    restore();
  }
});

test("lmstudio_chat_no_stream", async () => {
  const restore = mockFetch(() => ({
    json: { choices: [{ message: { content: "hi" } }] },
  }));
  try {
    const client = new LMStudioClient();
    assert.equal(await client.chat("mdl", [], false), "hi");
  } finally {
    restore();
  }
});

test("lmstudio_chat_stream", async () => {
  const restore = mockStreamFetch([
    "data: " + JSON.stringify({ choices: [{ delta: { content: "h" } }] }),
    "data: " + JSON.stringify({ choices: [{ delta: { content: "i" } }] }),
    "data: [DONE]",
  ]);
  try {
    const client = new LMStudioClient();
    let resp = "";
    await captureStdout(async () => {
      resp = await client.chat("mdl", [], true);
    });
    assert.equal(resp, "hi");
  } finally {
    restore();
  }
});

test("lmstudio_find_best_edge_model", async () => {
  const restore = mockFetch(() => ({
    json: { data: [{ id: "path/to/model-2b-q4" }] },
  }));
  try {
    const client = new LMStudioClient();
    assert.equal(await client.find_best_edge_model(), "path/to/model-2b-q4");
  } finally {
    restore();
  }
});

test("lm_studio_chat_error", async () => {
  const restore = mockThrowFetch();
  try {
    const client = new LMStudioClient();
    assert.ok((await client.chat("mdl", [])).includes("Error"));
  } finally {
    restore();
  }
});

test("lm_studio_list_models_error", async () => {
  const restore = mockThrowFetch();
  try {
    const client = new LMStudioClient();
    assert.deepEqual(await client.list_models(), []);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// get_best_available_client
// ---------------------------------------------------------------------------

test("get_best_available_client", async () => {
  // Ollama alive -> OllamaClient. is_alive() hits /api/version.
  let restore = mockFetch((url) => {
    if (url.includes("/api/version")) {
      return { status: 200, json: {} };
    }
    return { status: 200, json: {} };
  });
  try {
    const client = await get_best_available_client();
    assert.ok(client instanceof OllamaClient);
  } finally {
    restore();
  }

  // Ollama dead, LM Studio alive -> LMStudioClient.
  // Ollama is_alive() probes /api/version; LM Studio is_alive() probes /v1/models.
  restore = mockFetch((url) => {
    if (url.includes("/api/version")) {
      return { status: 503, json: {} }; // ollama not 200 -> not alive
    }
    if (url.includes("/v1/models") || url.endsWith("/models")) {
      return { status: 200, json: {} }; // lm studio alive
    }
    return { status: 503, json: {} };
  });
  try {
    const client = await get_best_available_client();
    assert.ok(client instanceof LMStudioClient);
  } finally {
    restore();
  }
});
