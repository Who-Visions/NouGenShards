import math
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

# --- Entropy-based fallback for BARE (unlabeled) high-entropy secrets --------
# The labeled SECRET_PATTERNS above only fire when a value follows a keyword
# (token/secret/key/...). A standalone credential dropped into a log with no
# label (e.g. a 40-char API key on its own) slips past all of them. This pass
# catches long, high-entropy, mixed-charset tokens while deliberately sparing
# ordinary long words (all-lowercase) and lowercase content hashes (hex md5/
# sha, which are letters+digits only) to keep false positives low.
_ENTROPY_MIN_LEN = 32          # long enough to skip normal identifiers/words
_ENTROPY_THRESHOLD = 4.0       # bits/char; random base64 ~6, hex ~4, prose <3.5
_HIGH_ENTROPY_CANDIDATE = re.compile(r'[A-Za-z0-9+/=_\-]{%d,}' % _ENTROPY_MIN_LEN)


def _shannon_entropy(s: str) -> float:
    counts: dict = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _looks_like_secret(token: str) -> bool:
    has_lower = any(c.islower() for c in token)
    has_upper = any(c.isupper() for c in token)
    has_digit = any(c.isdigit() for c in token)
    has_special = any(c in '+/=' for c in token)
    # Must mix letters and digits (rules out prose and pure numbers).
    if not (has_digit and (has_lower or has_upper)):
        return False
    # Require charset diversity: three letter/digit classes, or base64 padding/
    # symbol chars alongside digits. This spares all-lowercase words and
    # lowercase hex content hashes (only 2 classes, no special chars).
    classes = has_lower + has_upper + has_digit
    if not (classes >= 3 or (has_special and has_digit)):
        return False
    return _shannon_entropy(token) >= _ENTROPY_THRESHOLD


def _redact_high_entropy(content: str) -> str:
    def _repl(m: "re.Match") -> str:
        tok = m.group(0)
        return "<REDACTED_SECRET>" if _looks_like_secret(tok) else tok
    return _HIGH_ENTROPY_CANDIDATE.sub(_repl, content)


def redact_content(content: str) -> str:
    """Scans and redacts known secret patterns from content."""
    if not content:
        return content

    redacted = content
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    # Fallback pass LAST so labeled/provider-specific patterns take precedence
    # and their <REDACTED_*> placeholders are left untouched (no digits/length).
    redacted = _redact_high_entropy(redacted)
    return redacted
