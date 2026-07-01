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
  // OpenAI: project/service-account keys plus classic; allow _ and - so modern
  // sk-proj-/sk-svcacct- keys redact in full, not just up to the first dash.
  [/sk-(?:proj|svcacct|admin)-[a-zA-Z0-9_-]{20,}/g, "<REDACTED_OPENAI_KEY>"],
  [/sk-[a-zA-Z0-9_-]{20,}/g, "<REDACTED_OPENAI_KEY>"],
  [/hf_[a-zA-Z0-9_-]{20,}/g, "<REDACTED_HF_KEY>"],
  [/gh[pousr]_[A-Za-z0-9]{20,}/g, "<REDACTED_GITHUB_TOKEN>"],
  [/github_pat_[A-Za-z0-9_]{20,}/g, "<REDACTED_GITHUB_TOKEN>"],
  // AWS: AKIA (long-term) and ASIA (STS temporary) keys.
  [/(?:AKIA|ASIA)[0-9A-Z]{16}/g, "<REDACTED_AWS_ACCESS_KEY>"],
  [/AIza[0-9A-Za-z_-]{30,}/g, "<REDACTED_GOOGLE_KEY>"],
  [/xox[baprs]-[A-Za-z0-9-]{10,}/g, "<REDACTED_SLACK_TOKEN>"],
  // Match the token itself; do not consume a leading delimiter (that corrupted
  // surrounding JSON and missed adjacent tokens).
  [/nougen_[a-z]+_token_[A-Za-z0-9]+/g, "<REDACTED_NOUGEN_TOKEN>"],
  [
    /-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----/g,
    "<REDACTED_PRIVATE_KEY>",
  ],
  // Truncated private key (no END marker, common in clipped logs). Runs after
  // the complete-key pattern above.
  [/-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]+/g, "<REDACTED_PRIVATE_KEY>"],

  // Database / broker URLs with embedded credentials. Optional +driver suffix
  // (SQLAlchemy form) and optional path so bare host:port URLs still redact.
  [
    /(postgres|postgresql|mysql|mariadb|mongodb|redis|rediss|amqp|amqps)(?:\+[a-z0-9]+)?:\/\/[^:\s/"']+:[^@\s/"']+@[^\s/"']+(?:\/[^\s"']*)?/g,
    "<REDACTED_DB_URL>",
  ],

  // JWTs (trailing segment may be empty for unsigned/alg=none tokens).
  [/eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]*/g, "<REDACTED_JWT>"],

  // General API Keys / Tokens. Broadened value charset for base64/url-safe
  // secrets (+/=.~) and added labels (bearer/client_secret/pwd/pat/...).
  [
    /(?:api[_-]?key|secret|token|password|passwd|pwd|auth|credential|access[_-]?key|client[_-]?secret|private[_-]?key|bearer|session[_-]?token|\bpat\b|\bkey\b)[\s:=]+['"]?([A-Za-z0-9_\-+/=.~]{16,})['"]?/gi,
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
