// Node client helpers. No chrome.* so they unit-test under plain node (fetch is injected).
export const TUBE_HOSTS = ["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"];

export function isYouTube(url) {
  try {
    const u = new URL(url);
    return (u.protocol === "https:" || u.protocol === "http:") && TUBE_HOSTS.includes(u.hostname.toLowerCase());
  } catch { return false; }
}

// MCP streamable-HTTP replies are JSON or an SSE frame; take the last `data:` JSON.
export function parseMcpBody(text, contentType = "") {
  if (contentType.includes("text/event-stream") || /^\s*(event|data):/m.test(text)) {
    const datas = text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim());
    return JSON.parse(datas[datas.length - 1] || "{}");
  }
  return JSON.parse(text);
}

// Returns the tool's JSON result. Throws on transport, protocol or tool errors.
export async function mcpCall(origin, token, name, args, fetchImpl = fetch, timeoutMs = 90000) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const resp = await fetchImpl(`${origin}/mcp/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream", "X-NGS-Token": token },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }),
      signal: ctl.signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const msg = parseMcpBody(await resp.text(), resp.headers?.get?.("content-type") || "");
    if (msg.error) throw new Error(msg.error.message || "mcp error");
    const res = msg.result || {};
    const text = res.content?.[0]?.text ?? "";
    if (res.isError) throw new Error(text || `tool ${name} failed`);
    try { return JSON.parse(text); } catch { return { text }; }
  } finally { clearTimeout(timer); }
}

// A shard reference the destiny linker accepts: "db:id" or "id".
export function shardRef(result) {
  if (!result || result.captured !== true || result.shard_id == null) return null;
  return result.db_index != null ? `${result.db_index}:${result.shard_id}` : String(result.shard_id);
}
