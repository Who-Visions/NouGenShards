/**
 * OpenRouter Production Router for NouGenShards. (TS mimic of router.py)
 * Handles model fallback, session sticky routing, and prompt caching.
 */
import { createHash } from "node:crypto";

export interface ChatMessage {
  role: string;
  content: string;
  [key: string]: any;
}

/** Configuration for an OpenRouter request. (dataclass mimic) */
export interface RouterConfig {
  primary_model: string;
  fallback_models: string[];
  session_id: string | null;
  enable_response_healing: boolean;
  structured: boolean;
  json_schema: Record<string, any> | null;
  temperature: number | null;
  max_tokens: number | null;
  stream: boolean;
  extra_body: Record<string, any>;
}

export function make_router_config(overrides: Partial<RouterConfig> = {}): RouterConfig {
  return {
    primary_model: "openrouter/auto",
    fallback_models: [
      "anthropic/claude-3.5-sonnet",
      "google/gemini-2.0-flash-001",
      "deepseek/deepseek-chat",
      "openai/gpt-4o-mini",
    ],
    session_id: null,
    enable_response_healing: true,
    structured: false,
    json_schema: null,
    temperature: null,
    max_tokens: null,
    stream: false,
    extra_body: {},
    ...overrides,
  };
}

/**
 * Module 19: Stabilize Reasoning.
 * Constructs a message list optimized for prompt caching.
 * Ensures stable prefix (System prompt) is at the front.
 */
export function build_cache_friendly_messages(
  system_prompt: string,
  task_messages: ChatMessage[],
): ChatMessage[] {
  const messages: ChatMessage[] = [];
  // 1. Permanent System Instruction (The Anchor)
  if (system_prompt) {
    messages.push({ role: "system", content: system_prompt });
  }

  // 2. Append Task-Specific Messages
  messages.push(...task_messages);

  return messages;
}

/**
 * Generates a stable session_id for sticky provider routing.
 * Format: nougen:{project}:{agent}:{thread_hash}
 */
export function make_session_id(project: string, agent: string, thread: string | null = null): string {
  const base = `nougen:${project}:${agent}`;
  if (thread) {
    const thread_hash = createHash("sha256").update(thread).digest("hex").slice(0, 8);
    return `${base}:${thread_hash}`;
  }
  return base;
}
