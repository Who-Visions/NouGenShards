// Pure helpers: no chrome.* here so they unit-test under plain node.
export const MAX_CONTENT = 20000;
export const TAG = "chrome-capture";

export function hostOf(url) {
  try { return new URL(url).hostname || ""; } catch { return ""; }
}

// Endpoint must be http(s); strip trailing slashes and any path/query/credentials.
export function normalizeEndpoint(raw) {
  let u;
  try { u = new URL(String(raw || "").trim()); } catch { return null; }
  if (u.protocol !== "https:" && u.protocol !== "http:") return null;
  if (u.protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(u.hostname)) return null;
  return u.origin;
}

export function buildPayload({ selection, pageText, url, title, extraTags = [], author = "", now = new Date() }) {
  const body = String(selection || "").trim() || String(pageText || "").trim();
  if (!body) return null;
  const clipped = body.length > MAX_CONTENT;
  const text = clipped ? body.slice(0, MAX_CONTENT) : body;
  const host = hostOf(url);
  const kind = String(selection || "").trim() ? "selection" : "page";
  const headerLines = [
    `Source: ${url || "unknown"}`,
    `Captured: ${now.toISOString()}`,
    `Kind: ${kind}${clipped ? " (truncated)" : ""}`
  ];
  if (author && String(author).trim()) {
    headerLines.push(`Author: ${String(author).trim()}`);
  }
  const header = headerLines.join("\n");
  const tags = [TAG, kind];
  if (host) tags.push(host);
  if (Array.isArray(extraTags)) {
    for (const t of extraTags) {
      const clean = String(t || "").trim();
      if (clean && !tags.includes(clean)) tags.push(clean);
    }
  }
  return {
    event_type: "KNOWLEDGE",
    title: `Web: ${(title || host || "untitled").slice(0, 120)}`,
    content: `${header}\n\n${text}`,
    tags,
  };
}
