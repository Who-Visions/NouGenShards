/**
 * Secret redaction. (TS mimic of brain_scan/redaction.py)
 *
 * Each pattern is kept byte-for-byte equivalent to the Python `re.compile` source.
 * Python's inline `(?i)` on the final general-secret regex is unsupported mid-pattern
 * in JS, so the `i` flag is applied to that whole RegExp; every other pattern stays
 * case-sensitive exactly as written. All patterns use the global flag so `.sub`/
 * `.replace` redacts every occurrence (mirroring Python's `pattern.sub`).
 */

export const SECRET_PATTERNS: [RegExp, string][] = [
  // Specific Providers (MUST be before generic to match specific tags)
  [/sk-ant-[a-zA-Z0-9_-]{20,}/g, "<REDACTED_ANTHROPIC_KEY>"],
  [/sk-or-v1-[a-zA-Z0-9_-]{20,}/g, "<REDACTED_OPENROUTER_KEY>"],
  // Covers sk-..., sk-proj-..., sk-svcacct-... (newer keys contain - and _)
  [/sk-[a-zA-Z0-9_-]{20,}/g, "<REDACTED_OPENAI_KEY>"],
  [/hf_[a-zA-Z0-9_-]{20,}/g, "<REDACTED_HF_KEY>"],
  [/gh[pousr]_[A-Za-z0-9]{20,}/g, "<REDACTED_GITHUB_TOKEN>"],
  [/github_pat_[A-Za-z0-9_]{20,}/g, "<REDACTED_GITHUB_TOKEN>"],
  [/AKIA[0-9A-Z]{16}/g, "<REDACTED_AWS_ACCESS_KEY>"],
  [/AIza[0-9A-Za-z_-]{30,}/g, "<REDACTED_GOOGLE_KEY>"],
  [/xox[baprs]-[A-Za-z0-9-]{10,}/g, "<REDACTED_SLACK_TOKEN>"],
  [/(?:^|[\s"'=:])(nougen_[a-z]+_token_[A-Za-z0-9]+)/g, "<REDACTED_NOUGEN_TOKEN>"],
  [
    /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/g,
    "<REDACTED_PRIVATE_KEY>",
  ],

  // Database URLs (credentials present; path/db name is optional)
  [/(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp):\/\/[^:\s/]+:[^@\s]+@[^\s"'/]+(?:\/[^\s"']*)?/g, "<REDACTED_DB_URL>"],

  // JWTs
  [/eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/g, "<REDACTED_JWT>"],

  // General API Keys / Tokens (Python inline (?i) -> JS `i` flag on whole pattern)
  [
    /(?:api_key|apikey|secret|token|password|auth|credential|access_key|key)[\s:=]+['"]?([A-Za-z0-9_\-./+=~]{16,})['"]?/gi,
    "<REDACTED_SECRET>",
  ],
];

/** Scans and redacts known secret patterns from content. */
export function redact_content(content: string): string {
  if (!content) {
    return content;
  }

  let redacted = content;
  for (const [pattern, replacement] of SECRET_PATTERNS) {
    redacted = redacted.replace(pattern, replacement);
  }
  return redacted;
}
