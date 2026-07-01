/**
 * Reversed Hooks Lane for NouGenShards. (TS mimic of hooks.py)
 * Intercepts and compacts message history into high-signal Semantic Anchors.
 */
export interface ChatMessage {
  role: string;
  content: any;
  [key: string]: any;
}

// Patterns for high-signal architectural markers (mirrors hooks.py, re.IGNORECASE
// -> /i; /g is required so matchAll can iterate every occurrence).
const _PATTERNS: RegExp[] = [
  /(?:type|interface|class|def|function)\s+([a-zA-Z0-9_]+)/gi,
  /(?:endpoint|url|path|api)\s*[:=]\s*['"]([^'"]+)['"]/gi,
  /(?:directive|mandate|rule)\s*[:=]\s*([^.\n]+)/gi,
  /database\s+schema\s*[:=]\s*([^.\n]+)/gi,
];

/** Semantic Extraction: regex-parse messages for structural invariants. */
export function extract_invariants(messages: ChatMessage[]): string {
  const invariants: string[] = [];
  const seen = new Set<string>();

  for (const msg of messages) {
    const content = msg.content;
    if (typeof content !== "string") {
      continue;
    }
    for (const p of _PATTERNS) {
      for (const m of content.matchAll(p)) {
        const marker = m[1];
        if (marker && !seen.has(marker)) {
          invariants.push(marker);
          seen.add(marker);
        }
      }
    }
  }

  // Limit to top invariants to keep under token budget.
  const summary = invariants.slice(0, 20).join(", ");
  return invariants.length ? `Structural Invariants: ${summary}` : "No new invariants detected.";
}

/** Cache Alignment: replace raw chronological history with a compact anchor. */
export function inject_semantic_anchors(messages: ChatMessage[]): ChatMessage[] {
  if (messages.length <= 3) {
    return messages; // Don't compact short sessions
  }

  // 1. Preserve System Prompt (The Anchor)
  const system_msgs = messages.filter((m) => m.role === "system");

  // 2. Extract Invariants from the entire buffer
  const anchors_text = extract_invariants(messages);

  // 3. Compact anchor message replacing the middle 'tail'
  const compact_anchor: ChatMessage = {
    role: "user",
    content: `[REVERSED_HOOK] Semantic Anchor (History Virtualized): ${anchors_text}`,
  };

  // 4. Keep the most recent user request (The Execution Shard)
  const recent_msgs = messages.filter((m) => m.role !== "system").slice(-2);

  return [...system_msgs, compact_anchor, ...recent_msgs];
}

/** Main entry point for Play 2: Pointer Compaction. */
export function pre_tool_use_hook(message_payload: ChatMessage[]): ChatMessage[] {
  return inject_semantic_anchors(message_payload);
}
