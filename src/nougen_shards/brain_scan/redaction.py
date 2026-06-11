import re

SECRET_PATTERNS = [
    # Specific Providers (MUST be before generic to match specific tags)
    (re.compile(r'sk-ant-[a-zA-Z0-9_-]{20,}'), "<REDACTED_ANTHROPIC_KEY>"),
    (re.compile(r'sk-or-v1-[a-zA-Z0-9_-]{20,}'), "<REDACTED_OPENROUTER_KEY>"),
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), "<REDACTED_OPENAI_KEY>"),
    (re.compile(r'hf_[a-zA-Z0-9_-]{20,}'), "<REDACTED_HF_KEY>"),
    
    # Database URLs
    (re.compile(r'(postgres|mysql|sqlite|mongodb)://[^:]+:[^@]+@[^/]+/[^\s"\']+'), "<REDACTED_DB_URL>"),
    
    # JWTs
    (re.compile(r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'), "<REDACTED_JWT>"),
    
    # General API Keys / Tokens
    (re.compile(r'(?i)(?:api_key|apikey|secret|token|password|auth|credential|access_key|key)[\s:=]+[\'"]?([A-Za-z0-9_-]{16,})[\'"]?'), "<REDACTED_SECRET>")
]

def redact_content(content: str) -> str:
    """Scans and redacts known secret patterns from content."""
    if not content:
        return content
        
    redacted = content
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
