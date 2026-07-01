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

// --- Entropy-based fallback for BARE (unlabeled) high-entropy secrets --------
// The labeled SECRET_PATTERNS only fire when a value follows a keyword. A
// standalone credential with no label (e.g. a 40-char API key on its own)
// slips past them all. This pass catches long, high-entropy, mixed-charset
// tokens while sparing ordinary long words (all-lowercase) and lowercase
// content hashes (hex, letters+digits only) to keep false positives low.
const ENTROPY_MIN_LEN = 32; // long enough to skip normal identifiers/words
const ENTROPY_THRESHOLD = 4.0; // bits/char; random base64 ~6, hex ~4, prose <3.5
const HIGH_ENTROPY_CANDIDATE = new RegExp(`[A-Za-z0-9+/=_-]{${ENTROPY_MIN_LEN},}`, "g");

function shannon_entropy(s: string): number {
  const counts: Record<string, number> = {};
  for (const ch of s) {
    counts[ch] = (counts[ch] ?? 0) + 1;
  }
  const n = s.length;
  let h = 0;
  for (const c of Object.values(counts)) {
    const p = c / n;
    h -= p * Math.log2(p);
  }
  return h;
}

function looks_like_secret(token: string): boolean {
  const has_lower = /[a-z]/.test(token);
  const has_upper = /[A-Z]/.test(token);
  const has_digit = /[0-9]/.test(token);
  const has_special = /[+/=]/.test(token);
  // Must mix letters and digits (rules out prose and pure numbers).
  if (!(has_digit && (has_lower || has_upper))) {
    return false;
  }
  // Require charset diversity: three letter/digit classes, or base64 symbol
  // chars alongside digits. Spares all-lowercase words and lowercase hex hashes.
  const classes = Number(has_lower) + Number(has_upper) + Number(has_digit);
  if (!(classes >= 3 || (has_special && has_digit))) {
    return false;
  }
  return shannon_entropy(token) >= ENTROPY_THRESHOLD;
}

function redact_high_entropy(content: string): string {
  return content.replace(HIGH_ENTROPY_CANDIDATE, (tok) =>
    looks_like_secret(tok) ? "<REDACTED_SECRET>" : tok,
  );
}

/** Scans and redacts known secret patterns from content. */
export function redact_content(content: string): string {
  if (!content) {
    return content;
  }

  let redacted = content;
  for (const [pattern, replacement] of SECRET_PATTERNS) {
    redacted = redacted.replace(pattern, replacement);
  }
  // Fallback pass LAST so labeled patterns take precedence and their
  // <REDACTED_*> placeholders are left untouched (no digits / too short).
  redacted = redact_high_entropy(redacted);
  return redacted;
}
