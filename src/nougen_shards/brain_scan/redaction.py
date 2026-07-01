import re

SECRET_PATTERNS = [
    # Specific Providers (MUST be before generic to match specific tags)
    (re.compile(r'sk-ant-[a-zA-Z0-9_-]{20,}'), "<REDACTED_ANTHROPIC_KEY>"),
    (re.compile(r'sk-or-v1-[a-zA-Z0-9_-]{20,}'), "<REDACTED_OPENROUTER_KEY>"),
    # OpenAI: classic sk-... plus project/service-account keys (sk-proj-, sk-svcacct-).
    # Allow _ and - so modern keys are redacted in full, not just up to the first dash.
    (re.compile(r'sk-(?:proj|svcacct|admin)-[a-zA-Z0-9_-]{20,}'), "<REDACTED_OPENAI_KEY>"),
    (re.compile(r'sk-[a-zA-Z0-9_-]{20,}'), "<REDACTED_OPENAI_KEY>"),
    (re.compile(r'hf_[a-zA-Z0-9_-]{20,}'), "<REDACTED_HF_KEY>"),
    (re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'), "<REDACTED_GITHUB_TOKEN>"),
    (re.compile(r'github_pat_[A-Za-z0-9_]{20,}'), "<REDACTED_GITHUB_TOKEN>"),
    # AWS: AKIA (long-term) and ASIA (STS temporary) access keys.
    (re.compile(r'(?:AKIA|ASIA)[0-9A-Z]{16}'), "<REDACTED_AWS_ACCESS_KEY>"),
    (re.compile(r'AIza[0-9A-Za-z_-]{30,}'), "<REDACTED_GOOGLE_KEY>"),
    (re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}'), "<REDACTED_SLACK_TOKEN>"),
    # NouGen token: match the token itself; do not consume a leading delimiter
    # (consuming it corrupted surrounding JSON and missed adjacent tokens).
    (re.compile(r'nougen_[a-z]+_token_[A-Za-z0-9]+'), "<REDACTED_NOUGEN_TOKEN>"),
    (re.compile(r'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----'), "<REDACTED_PRIVATE_KEY>"),
    # Truncated private key (no END marker, common in clipped logs): redact from
    # the header to end of content. Runs after the complete-key pattern above.
    (re.compile(r'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]+'), "<REDACTED_PRIVATE_KEY>"),

    # Database / broker URLs with embedded credentials. Path is optional so
    # bare host:port URLs (postgres://u:p@host:5432) are still redacted.
    (re.compile(r'(postgres|postgresql|mysql|mariadb|mongodb|redis|rediss|amqp|amqps)(?:\+[a-z0-9]+)?://[^:\s/"\']+:[^@\s/"\']+@[^\s/"\']+(?:/[^\s"\']*)?'), "<REDACTED_DB_URL>"),

    # JWTs
    (re.compile(r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]*'), "<REDACTED_JWT>"),

    # General API Keys / Tokens. Broadened value charset to cover base64/url-safe
    # secrets (+/=.~) so they are not truncated at the first special char, and
    # added common credential labels (bearer, client_secret, pwd, pat, ...).
    (re.compile(r'(?i)(?:api[_-]?key|secret|token|password|passwd|pwd|auth|credential|access[_-]?key|client[_-]?secret|private[_-]?key|bearer|session[_-]?token|\bpat\b|\bkey\b)[\s:=]+[\'"]?([A-Za-z0-9_\-+/=.~]{16,})[\'"]?'), "<REDACTED_SECRET>")
]


def redact_content(content: str) -> str:
    """Scans and redacts known secret patterns from content.

    Best-effort: this only redacts labeled/provider-specific secrets. Bare,
    unlabeled high-entropy tokens are NOT redacted — an entropy heuristic was
    tried and removed because it destroyed ordinary content (long CamelCase
    identifiers, base64 payloads) with too many false positives.
    """
    if not content:
        return content

    redacted = content
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
