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
    # Cloudflare API tokens (cfat_...). Previously only caught when a label
    # like "API Token" happened to precede them; a bare token passed through.
    (re.compile(r'cfat_[A-Za-z0-9]{20,}'), "<REDACTED_CLOUDFLARE_TOKEN>"),
    (re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}'), "<REDACTED_SLACK_TOKEN>"),
    # Notion integration tokens (ntn_..., and the older secret_... form). Added
    # 2026-08-29 after a LIVE ntn_ token came back verbatim in a grid search
    # result: it matched no provider pattern here, and the generic labelled-
    # secret rule missed it because it sat in source code as a bare assignment
    # with no credential-shaped label in front of it.
    (re.compile(r'ntn_[A-Za-z0-9]{20,}'), "<REDACTED_NOTION_TOKEN>"),
    (re.compile(r'secret_[A-Za-z0-9]{40,}'), "<REDACTED_NOTION_TOKEN>"),
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
    # Up to three short words may sit between the label and the value. Without
    # this, "Access Key ID <32-hex>" and "fleet key outpost <44-char key>" both
    # passed through unredacted — the exact shapes that leaked into dream
    # digests on 2026-08-15 and 2026-08-19.
    # Runs BEFORE the generic label rule below, deliberately. That rule matches
    # a bare label anywhere, so on NGS_NODE_TOKEN=<value> it consumed "TOKEN"
    # as well and emitted "NGS_NODE_<REDACTED_SECRET>" -- destroying half the
    # key's NAME. Names are the part that is safe to keep and the part that
    # makes a redacted line diagnosable, so the name-preserving rule wins.
    # A credential label that is part of a longer identifier rather than a
    # standalone word: NGS_NODE_TOKEN=, CLOUDFLARE_API_TOKEN=, SOME_SECRET_KEY=.
    # The rule above requires the label to be followed by [\s:=], so an
    # underscore-joined name like SOME_SECRET_KEY defeated it -- and those are
    # exactly the names this fleet's own keys carry.
    (re.compile(r'(?i)([A-Za-z0-9]*(?:SECRET|TOKEN|PASSWORD|PASSWD|APIKEY|API_KEY|PRIVATE_KEY|ACCESS_KEY|CREDENTIAL)[A-Za-z0-9_]*\s*[=:]\s*)[\'"]?[A-Za-z0-9_\-+/=.~]{8,}'), r"\1<REDACTED_SECRET>"),
    (re.compile(r'(?i)(?:api[_-]?key|secret|token|password|passwd|pwd|auth|credential|access[_-]?key|client[_-]?secret|private[_-]?key|bearer|session[_-]?token|\bpat\b|\bkey\b)[\s:=]+(?:[A-Za-z]{1,12}[\s:=]+){0,3}[\'"]?([A-Za-z0-9_\-+/=.~]{16,})[\'"]?'), "<REDACTED_SECRET>"),

    # --- added 2026-09-07 from the cross-node shape audit --------------
    # Three nodes each ran a private pattern set and each missed roughly half
    # of what the others tested for. This module was already the strongest of
    # them (20 of 27 merged shapes, zero false positives) -- these seven close
    # the rest rather than starting a fourth set. Fixture:
    # tests/test_credential_patterns.py.
    # A PEM header with NO body after it. The two block rules above both
    # require key material to follow, so a lone header line survived -- and a
    # truncated log line, a diff hunk, or a file listing is exactly where one
    # appears. Found by blade's independent 20-case corpus (case 8), which is
    # the first fixture scored here that phoebus did not write.
    (re.compile(r'-----BEGIN[ A-Z0-9]*PRIVATE KEY-----'), "<REDACTED_PRIVATE_KEY>"),
    # Marker-only, zero-entropy shapes. There is no random material in these,
    # so every rule written to match "the secret" misses them structurally --
    # blade predicted the class after the bare BEGIN header defeated both PEM
    # rules, and fixture v2 immediately found two more here. A PEM END block
    # means a key was in this text; an Azure connection-string prefix means
    # an AccountKey was.
    (re.compile(r'-----END[ A-Z0-9]*PRIVATE KEY-----'), "<REDACTED_PRIVATE_KEY>"),
    (re.compile(r'DefaultEndpointsProtocol\s*=\s*[a-z]+;[^\s]*'), "<REDACTED_AZURE_CONNECTION>"),
    (re.compile(r'sk_live_[A-Za-z0-9]{16,}'), "<REDACTED_STRIPE_KEY>"),
    (re.compile(r'sk_test_[A-Za-z0-9]{16,}'), "<REDACTED_STRIPE_KEY>"),
    (re.compile(r'glpat-[A-Za-z0-9_\-]{20}'), "<REDACTED_GITLAB_TOKEN>"),
    (re.compile(r'npm_[A-Za-z0-9]{36}'), "<REDACTED_NPM_TOKEN>"),
    # Cloudflare's scoped v1.0- tokens; cfat_ above covers only the older form.
    (re.compile(r'v1\.0-[A-Za-z0-9]{20,}-[A-Za-z0-9_\-]{20,}'), "<REDACTED_CLOUDFLARE_TOKEN>"),
    # Azure connection strings. Keeps the AccountKey= label so the line stays
    # diagnosable, and destroys only the value.
    (re.compile(r'(?i)(AccountKey\s*=\s*)[A-Za-z0-9+/=]{20,}'), r"\1<REDACTED_AZURE_KEY>"),
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
