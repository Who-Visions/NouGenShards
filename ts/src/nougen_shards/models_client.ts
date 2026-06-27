/**
 * Modular LLM client interface for NouGenShards with embedding support.
 * (TS mimic of models_client.py)
 *
 * Python uses urllib (sync) for HTTP. This port uses the global `fetch` (async),
 * so every network method (chat / embed / list_models, plus ping-based is_alive)
 * returns a Promise. Streaming reads `res.body` as an async iterator, parses SSE
 * `data: ` lines, echoes to process.stdout, and returns the accumulated string.
 */
import * as keymaker from "./keymaker.js";
import * as router from "./router.js";
import * as structured from "./structured.js";

export interface ChatMessage {
  role: string;
  content: string;
  [key: string]: any;
}

/** Abstract base class for all LLM clients. */
export abstract class LLMClient {
  /** Check if the service is reachable/configured. */
  abstract is_alive(): boolean | Promise<boolean>;

  /** Return available model names. */
  abstract list_models(): Promise<string[]>;

  /** Send chat request. */
  abstract chat(model: string, messages: ChatMessage[], stream?: boolean): Promise<string>;

  /** Generate vector embeddings for text. */
  abstract embed(model: string, text: string): Promise<number[]>;
}

/** Abstract base class for local LLM clients. */
export abstract class LocalLLMClient extends LLMClient {
  /** Heuristic for best local model. */
  abstract find_best_edge_model(): Promise<string>;
}

/**
 * Reads a fetch Response body as an async iterator of text lines (SSE style).
 * Mirrors Python's `for line in response` over a urllib response object.
 */
async function* _iter_lines(res: Response): AsyncGenerator<string> {
  const body = res.body;
  if (!body) {
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  // res.body is a web ReadableStream; Node exposes it as async-iterable.
  for await (const chunk of body as unknown as AsyncIterable<Uint8Array>) {
    buffer += decoder.decode(chunk, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 1);
      yield line;
    }
  }
  buffer += decoder.decode();
  if (buffer.length > 0) {
    yield buffer;
  }
}

/** Client for OpenAI (ChatGPT). */
export class OpenAIClient extends LLMClient {
  api_key: string | null;
  base_url: string;

  constructor(api_key: string | null = null) {
    super();
    this.api_key = api_key ?? keymaker.get_secret("OPENAI_API_KEY");
    this.base_url = "https://api.openai.com/v1";
  }

  is_alive(): boolean {
    return Boolean(this.api_key);
  }

  async list_models(): Promise<string[]> {
    return ["gpt-4o", "gpt-4o-mini"];
  }

  async chat(model: string, messages: ChatMessage[], stream = false): Promise<string> {
    if (!this.api_key) {
      return "Error: OpenAI Key missing.";
    }
    const payload = { model, messages, stream };
    try {
      const res = await fetch(`${this.base_url}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.api_key ?? ""}`,
        },
        body: JSON.stringify(payload),
      });
      if (!stream) {
        const resp_data: any = await res.json();
        return resp_data?.choices?.[0]?.message?.content ?? "";
      }
      return await this._stream_chat(res);
    } catch (exc) {
      return `Error: ${exc}`;
    }
  }

  async _stream_chat(response: Response): Promise<string> {
    let full_content = "";
    for await (const line of _iter_lines(response)) {
      const line_str = line.trim();
      if (line_str.startsWith("data: ") && line_str !== "data: [DONE]") {
        try {
          const chunk = JSON.parse(line_str.slice(6));
          const content = chunk?.choices?.[0]?.delta?.content ?? "";
          full_content += content;
          process.stdout.write(content);
        } catch {
          continue;
        }
      }
    }
    return full_content;
  }

  async embed(model: string, text: string): Promise<number[]> {
    if (!this.api_key) {
      return [];
    }
    const payload = { model, input: text };
    try {
      const res = await fetch(`${this.base_url}/embeddings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.api_key ?? ""}`,
        },
        body: JSON.stringify(payload),
      });
      const resp_data: any = await res.json();
      return resp_data?.data?.[0]?.embedding ?? [];
    } catch {
      return [];
    }
  }
}

/** Client for Anthropic (Claude). */
export class AnthropicClient extends LLMClient {
  api_key: string | null;
  base_url: string;

  constructor(api_key: string | null = null) {
    super();
    this.api_key = api_key ?? keymaker.get_secret("ANTHROPIC_API_KEY");
    this.base_url = "https://api.anthropic.com/v1";
  }

  is_alive(): boolean {
    return Boolean(this.api_key);
  }

  async list_models(): Promise<string[]> {
    return ["claude-3-5-sonnet-latest"];
  }

  async chat(model: string, messages: ChatMessage[], stream = false): Promise<string> {
    if (!this.api_key) {
      return "Error: Anthropic Key missing.";
    }
    const system_msg = messages.find((m) => m.role === "system")?.content ?? "";
    const user_msgs = messages.filter((m) => m.role !== "system");
    const payload = {
      model,
      messages: user_msgs,
      max_tokens: 4096,
      system: system_msg,
      stream,
    };
    try {
      const res = await fetch(`${this.base_url}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": this.api_key ?? "",
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify(payload),
      });
      if (!stream) {
        const resp_data: any = await res.json();
        return resp_data?.content?.[0]?.text ?? "";
      }
      return await this._stream_chat(res);
    } catch (exc) {
      return `Error: ${exc}`;
    }
  }

  async _stream_chat(response: Response): Promise<string> {
    let full_content = "";
    for await (const line of _iter_lines(response)) {
      const line_str = line.trim();
      if (line_str.startsWith("data: ")) {
        try {
          const chunk = JSON.parse(line_str.slice(6));
          if (chunk?.type === "content_block_delta") {
            const content = chunk?.delta?.text ?? "";
            full_content += content;
            process.stdout.write(content);
          }
        } catch {
          continue;
        }
      }
    }
    return full_content;
  }

  async embed(_model: string, _text: string): Promise<number[]> {
    return [];
  }
}

/** Client for Google (Gemini). */
export class GeminiClient extends LLMClient {
  api_key: string | null;
  base_url: string;

  constructor(api_key: string | null = null) {
    super();
    this.api_key = api_key ?? keymaker.get_secret("GOOGLE_API_KEY");
    this.base_url = "https://generativelanguage.googleapis.com/v1beta/models";
  }

  is_alive(): boolean {
    return Boolean(this.api_key);
  }

  async list_models(): Promise<string[]> {
    return ["gemini-1.5-pro", "gemini-1.5-flash"];
  }

  async chat(model: string, messages: ChatMessage[], stream = false): Promise<string> {
    if (!this.api_key) {
      return "Error: Google Key missing.";
    }
    const contents: any[] = [];
    for (const msg of messages) {
      const role = msg.role === "user" || msg.role === "system" ? "user" : "model";
      contents.push({ role, parts: [{ text: msg.content }] });
    }
    const endpoint = stream ? "streamGenerateContent" : "generateContent";
    const url = `${this.base_url}/${model}:${endpoint}?key=${this.api_key}`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contents }),
      });
      if (!stream) {
        const resp_data: any = await res.json();
        return resp_data?.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
      }
      return await this._stream_chat(res);
    } catch (exc) {
      return `Error: ${exc}`;
    }
  }

  async _stream_chat(response: Response): Promise<string> {
    let full_content = "";
    for await (const line of _iter_lines(response)) {
      let line_str = line.trim();
      if (!line_str) {
        continue;
      }
      if (line_str.startsWith("[")) {
        line_str = line_str.slice(1);
      }
      if (line_str.endsWith("]")) {
        line_str = line_str.slice(0, -1);
      }
      if (line_str.endsWith(",")) {
        line_str = line_str.slice(0, -1);
      }
      try {
        const chunk = JSON.parse(line_str);
        const content = chunk?.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
        full_content += content;
        process.stdout.write(content);
      } catch {
        continue;
      }
    }
    return full_content;
  }

  async embed(model: string, text: string): Promise<number[]> {
    if (!this.api_key) {
      return [];
    }
    const url = `${this.base_url}/${model}:embedContent?key=${this.api_key}`;
    const payload = { content: { parts: [{ text }] } };
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const resp_data: any = await res.json();
      return resp_data?.embedding?.values ?? [];
    } catch {
      return [];
    }
  }
}

/** Client for Hugging Face Inference API. */
export class HuggingFaceClient extends LLMClient {
  api_key: string | null;
  base_url: string;

  constructor(api_key: string | null = null) {
    super();
    this.api_key = api_key ?? keymaker.get_secret("HUGGINGFACE_API_KEY");
    this.base_url = "https://api-inference.huggingface.co/models";
  }

  is_alive(): boolean {
    return Boolean(this.api_key);
  }

  async list_models(): Promise<string[]> {
    return ["meta-llama/Llama-3.2-3B-Instruct"];
  }

  async chat(model: string, messages: ChatMessage[], stream = false): Promise<string> {
    if (!this.api_key) {
      return "Error: HF Key missing.";
    }
    let prompt = "";
    for (const msg of messages) {
      prompt += `${msg.role.toUpperCase()}: ${msg.content}\n`;
    }
    prompt += "ASSISTANT: ";
    const payload = { inputs: prompt, parameters: { max_new_tokens: 1024 }, stream };
    try {
      const res = await fetch(`${this.base_url}/${model}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.api_key ?? ""}`,
        },
        body: JSON.stringify(payload),
      });
      if (!stream) {
        const result: any = await res.json();
        if (Array.isArray(result)) {
          return result[0]?.generated_text ?? "";
        }
        return String(result);
      }
      return await this._stream_chat(res);
    } catch (exc) {
      return `Error: ${exc}`;
    }
  }

  async _stream_chat(response: Response): Promise<string> {
    let full_content = "";
    for await (const line of _iter_lines(response)) {
      const line_str = line.trim();
      if (line_str.startsWith("data: ")) {
        try {
          const chunk = JSON.parse(line_str.slice(6));
          const content = chunk?.token?.text ?? "";
          full_content += content;
          process.stdout.write(content);
        } catch {
          continue;
        }
      }
    }
    return full_content;
  }

  async embed(_model: string, _text: string): Promise<number[]> {
    return [];
  }
}

/** Client for OpenRouter (Unified API). */
// Confirmed-free OpenRouter model IDs. Used ONLY as an offline seed when live
// discovery (get_free_models) cannot reach the OpenRouter API. The live roster is
// the source of truth and returns the FULL set of free models at runtime.
export const FREE_MODEL_SEED: string[] = [
  "nousresearch/hermes-3-llama-3.1-405b:free",
  "google/gemma-4-31b-it:free",
  "google/gemma-3-27b-it:free",
];
const _FREE_MODELS_CACHE: { ts: number; models: string[] } = { ts: 0, models: [] };
const _FREE_MODELS_TTL = 3600 * 1000; // ms

export class OpenRouterClient extends OpenAIClient {
  constructor(api_key: string | null = null) {
    super(api_key ?? keymaker.get_secret("OPENROUTER_API_KEY"));
    this.base_url = "https://openrouter.ai/api/v1";
  }

  /**
   * Discover the FULL set of free OpenRouter models live from the API. Filters
   * the catalogue to every model that is actually free (`:free` suffix or zero
   * prompt+completion pricing), cached for `_FREE_MODELS_TTL`. Falls back to
   * `FREE_MODEL_SEED` only when the API is unreachable so the roster is never empty.
   */
  async get_free_models(refresh = false): Promise<string[]> {
    const now = Date.now();
    if (!refresh && _FREE_MODELS_CACHE.models.length && now - _FREE_MODELS_CACHE.ts < _FREE_MODELS_TTL) {
      return [..._FREE_MODELS_CACHE.models];
    }
    const isZero = (v: any): boolean => {
      const n = typeof v === "number" ? v : parseFloat(v);
      return !Number.isNaN(n) && n === 0;
    };
    try {
      const headers: Record<string, string> = {
        "HTTP-Referer": "https://whovisions.com",
        "X-OpenRouter-Title": "NouGenShards",
      };
      if (this.api_key) headers.Authorization = `Bearer ${this.api_key}`;
      const res = await fetch(`${this.base_url}/models`, { method: "GET", headers });
      const data: any = await res.json();
      const free: string[] = [];
      for (const model of data?.data ?? []) {
        const mid: string = model?.id ?? "";
        if (!mid) continue;
        const pricing = model?.pricing ?? {};
        if (mid.endsWith(":free") || (isZero(pricing.prompt) && isZero(pricing.completion))) {
          free.push(mid);
        }
      }
      if (free.length) {
        _FREE_MODELS_CACHE.models = free;
        _FREE_MODELS_CACHE.ts = now;
        return [...free];
      }
    } catch {
      /* fall through to offline seed */
    }
    return [...FREE_MODEL_SEED];
  }

  override async list_models(): Promise<string[]> {
    // The roster IS the full live set of free OpenRouter models.
    return this.get_free_models();
  }

  override async chat(model: string, messages: ChatMessage[], stream = false): Promise<string> {
    if (!this.api_key) {
      return "Error: OR Key missing.";
    }
    const payload = { model, messages, stream };
    try {
      const res = await fetch(`${this.base_url}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.api_key ?? ""}`,
          "HTTP-Referer": "https://whovisions.com",
          "X-OpenRouter-Title": "NouGenShards",
        },
        body: JSON.stringify(payload),
      });
      if (!stream) {
        const resp_data: any = await res.json();
        return resp_data?.choices?.[0]?.message?.content ?? "";
      }
      return await this._stream_chat(res);
    } catch (exc) {
      return `Error: ${exc}`;
    }
  }

  /** Executes a chat request with OpenRouter model fallback. */
  async chat_with_fallback(
    model: string,
    messages: ChatMessage[],
    fallback_models: string[] | null = null,
    session_id: string | null = null,
    stream = false,
    kwargs: { temperature?: number | null; max_tokens?: number | null } = {},
  ): Promise<Record<string, any>> {
    if (!this.api_key) {
      return { content: "Error: OR Key missing.", model: "unknown" };
    }

    const payload: Record<string, any> = {
      model,
      messages,
      stream,
      // Default to the FULL live free roster so fallback routes across every
      // free model OpenRouter offers, not a curated handful.
      models: fallback_models ?? (await this.get_free_models()),
    };

    if (session_id) {
      payload.session_id = session_id;
    }

    // Add optional params
    for (const key of ["temperature", "max_tokens"] as const) {
      if (key in kwargs && kwargs[key] !== null && kwargs[key] !== undefined) {
        payload[key] = kwargs[key];
      }
    }

    try {
      const res = await fetch(`${this.base_url}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.api_key ?? ""}`,
          "HTTP-Referer": "https://whovisions.com",
          "X-OpenRouter-Title": "NouGenShards",
        },
        body: JSON.stringify(payload),
      });
      if (!stream) {
        const resp_data: any = await res.json();
        const choice = resp_data?.choices?.[0] ?? {};
        return {
          content: choice?.message?.content ?? "",
          model: resp_data?.model ?? model,
          usage: this._extract_usage_metadata(resp_data),
          finish_reason: choice?.finish_reason ?? null,
        };
      }
      return { content: await this._stream_chat(res), model };
    } catch (exc) {
      return { content: `Error: ${exc}`, model: "error" };
    }
  }

  /** Executes a request for structured JSON output with response healing. */
  async structured_chat(
    model: string,
    messages: ChatMessage[],
    schema: Record<string, any>,
    fallback_models: string[] | null = null,
    session_id: string | null = null,
    healing = true,
    strict = true,
  ): Promise<Record<string, any>> {
    if (!this.api_key) {
      return { error: "OR Key missing." };
    }

    const payload: Record<string, any> = {
      model,
      messages,
      models: fallback_models ?? [],
      stream: false,
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "nougen_schema",
          strict,
          schema,
        },
      },
    };

    if (session_id) {
      payload.session_id = session_id;
    }

    if (healing) {
      payload.plugins = [{ id: "response-healing" }];
    }

    try {
      const res = await fetch(`${this.base_url}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.api_key ?? ""}`,
          "HTTP-Referer": "https://whovisions.com",
          "X-OpenRouter-Title": "NouGenShards",
        },
        body: JSON.stringify(payload),
      });
      const resp_data: any = await res.json();
      const content = resp_data?.choices?.[0]?.message?.content ?? "";

      let data: Record<string, any>;
      try {
        data = structured.parse_json_content(content);
      } catch (e) {
        return { error: `JSON Parse Failed: ${e}`, raw: content };
      }

      const [valid, errors] = structured.validate_against_schema(data, schema);

      return {
        data,
        valid,
        errors,
        model: resp_data?.model,
        usage: this._extract_usage_metadata(resp_data),
      };
    } catch (exc) {
      return { error: `Request Failed: ${exc}` };
    }
  }

  /** Normalizes OpenRouter usage data including cached tokens. */
  _extract_usage_metadata(response_json: Record<string, any>): Record<string, any> {
    const usage = response_json?.usage ?? {};
    const details = usage?.prompt_tokens_details ?? {};
    return {
      prompt_tokens: usage?.prompt_tokens ?? 0,
      completion_tokens: usage?.completion_tokens ?? 0,
      total_tokens: usage?.total_tokens ?? 0,
      cached_tokens: details?.cached_tokens ?? 0,
      cache_write_tokens: details?.cache_write_tokens ?? 0,
    };
  }
}

/**
 * Client for Who Visions Hosted Cloud Brain.
 * Securely bridges local CLI to remote node for metered inference.
 */
export class WhoVisionsCloudClient extends LLMClient {
  node_url: string | null;
  user_token: string | null;

  constructor(node_url: string | null = null, user_token: string | null = null) {
    super();
    this.node_url = node_url ?? process.env.NGS_CLOUD_URL ?? null;
    this.user_token = user_token ?? process.env.NGS_CLOUD_TOKEN ?? null;
  }

  is_alive(): boolean {
    return Boolean(this.node_url && this.user_token);
  }

  async list_models(): Promise<string[]> {
    // Return canonical cloud models
    return ["whovisions/brain-v1", "openrouter/auto"];
  }

  async chat(model: string, messages: ChatMessage[], stream = false): Promise<string> {
    if (!this.is_alive()) {
      return "Error: Who Visions Cloud not configured. Use: nougen auth set-key cloud <url>,<token>";
    }

    const payload = { model, messages, stream };
    try {
      const res = await fetch(`${this.node_url ? this.node_url.replace(/\/+$/, "") : ""}/cloud/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-NGS-Token": this.user_token ?? "",
        },
        body: JSON.stringify(payload),
      });
      const resp_data: any = await res.json();
      return resp_data?.content ?? "";
    } catch (exc) {
      return `Error: ${exc}`;
    }
  }

  async embed(_model: string, _text: string): Promise<number[]> {
    // Future: implement remote embedding gateway
    return [];
  }
}

/** Client for local Ollama instance. */
export class OllamaClient extends LocalLLMClient {
  base_url: string;

  constructor(base_url = "http://127.0.0.1:11434") {
    super();
    this.base_url = base_url;
  }

  async is_alive(): Promise<boolean> {
    try {
      const ctl = AbortSignal.timeout(1000);
      const res = await fetch(`${this.base_url}/api/version`, { signal: ctl });
      return res.status === 200;
    } catch {
      return false;
    }
  }

  async list_models(): Promise<string[]> {
    try {
      const res = await fetch(`${this.base_url}/api/tags`, { signal: AbortSignal.timeout(3000) });
      const data: any = await res.json();
      return (data?.models ?? []).map((m: any) => m.name);
    } catch {
      return [];
    }
  }

  async chat(model: string, messages: ChatMessage[], stream = false): Promise<string> {
    const payload = { model, messages, stream };
    try {
      const res = await fetch(`${this.base_url}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!stream) {
        const resp_data: any = await res.json();
        return resp_data?.message?.content ?? "";
      }
      let full = "";
      for await (const line of _iter_lines(res)) {
        if (!line.trim()) {
          continue;
        }
        const chunk = JSON.parse(line);
        const content = chunk?.message?.content ?? "";
        full += content;
        process.stdout.write(content);
      }
      return full;
    } catch (exc) {
      return `Error: ${exc}`;
    }
  }

  async embed(model: string, text: string): Promise<number[]> {
    const payload = { model, prompt: text };
    try {
      const res = await fetch(`${this.base_url}/api/embeddings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data: any = await res.json();
      return data?.embedding ?? [];
    } catch {
      return [];
    }
  }

  async find_best_edge_model(): Promise<string> {
    const models = await this.list_models();
    for (const prefix of ["dav1d:e2b", "rhea-noir:e2b", "sol-ai:e2b"]) {
      for (const model of models) {
        if (model.startsWith(prefix)) {
          return model;
        }
      }
    }
    return models.length > 0 ? models[0] : "";
  }

  /** Ollama-specific: pull model. */
  async pull_model(model_name: string): Promise<boolean> {
    const url = `${this.base_url}/api/pull`;
    const payload = JSON.stringify({ model: model_name, stream: true });
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      });
      for await (const line of _iter_lines(res)) {
        if (line) {
          const chunk = JSON.parse(line);
          const status = chunk?.status ?? "";
          const completed = chunk?.completed;
          const total = chunk?.total;
          if (total && completed) {
            const pct = (completed / total) * 100;
            process.stdout.write(`\r[*] Pulling ${model_name}: ${pct.toFixed(1)}% (${status})`);
          } else if (status) {
            process.stdout.write(`\r[*] ${status}...`);
          }
        }
      }
      console.log("\n✅ Model pull complete.");
      return true;
    } catch (exc) {
      console.log(`\n[ERR] Failed to pull model: ${exc}`);
      return false;
    }
  }
}

/** Client for local LM Studio. */
export class LMStudioClient extends LocalLLMClient {
  base_url: string;

  constructor(base_url = "http://127.0.0.1:1234/v1") {
    super();
    this.base_url = base_url;
  }

  async is_alive(): Promise<boolean> {
    try {
      const res = await fetch(`${this.base_url}/models`, { signal: AbortSignal.timeout(1000) });
      return res.status === 200;
    } catch {
      return false;
    }
  }

  async list_models(): Promise<string[]> {
    try {
      const res = await fetch(`${this.base_url}/models`, { signal: AbortSignal.timeout(3000) });
      const data: any = await res.json();
      return (data?.data ?? []).map((m: any) => m.id);
    } catch {
      return [];
    }
  }

  async chat(model: string, messages: ChatMessage[], stream = false): Promise<string> {
    const payload = { model, messages, stream };
    try {
      const res = await fetch(`${this.base_url}/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!stream) {
        const resp_data: any = await res.json();
        return resp_data?.choices?.[0]?.message?.content ?? "";
      }
      return await this._stream_chat(res);
    } catch (exc) {
      return `Error: ${exc}`;
    }
  }

  async _stream_chat(response: Response): Promise<string> {
    let full = "";
    for await (const line of _iter_lines(response)) {
      const line_str = line.trim();
      if (line_str.startsWith("data: ") && line_str !== "data: [DONE]") {
        try {
          const chunk = JSON.parse(line_str.slice(6));
          const content = chunk?.choices?.[0]?.delta?.content ?? "";
          full += content;
          process.stdout.write(content);
        } catch {
          continue;
        }
      }
    }
    return full;
  }

  async embed(_model: string, _text: string): Promise<number[]> {
    return [];
  }

  async find_best_edge_model(): Promise<string> {
    const models = await this.list_models();
    return models.length > 0 ? models[0] : "";
  }
}

/** Detects and returns the best available local LLM provider. */
export async function get_best_available_client(): Promise<LocalLLMClient> {
  const ollama = new OllamaClient();
  if (await ollama.is_alive()) {
    return ollama;
  }
  const lm_client = new LMStudioClient();
  if (await lm_client.is_alive()) {
    return lm_client;
  }
  return ollama;
}

// `router` is imported to mirror the Python module surface (parity with models_client.py).
void router;
