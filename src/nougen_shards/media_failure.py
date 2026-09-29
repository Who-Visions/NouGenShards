"""Safe, machine-readable failures for media ingestion."""

from urllib.parse import urlsplit, urlunsplit


def public_source(source: str) -> str:
    """Strip URL credentials, query parameters and fragments from diagnostics."""
    try:
        parts = urlsplit(source)
        host = parts.hostname
        port = parts.port
    except (AttributeError, TypeError, ValueError):
        return "local-media"
    if parts.scheme.lower() not in ("http", "https") or not host:
        return "local-media"
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority = f"{authority}:{port}"
    return urlunsplit((parts.scheme.lower(), authority, parts.path, "", ""))


class MediaIngestFailure(Exception):
    def __init__(self, code: str, stage: str, source: str, attempts=None):
        self.code = code
        self.stage = stage
        self.source = public_source(source)
        self.attempts = list(attempts or [])
        super().__init__(f"{stage}: {code}")

    def to_dict(self):
        return {
            "code": self.code,
            "stage": self.stage,
            "source": self.source,
            "attempts": self.attempts,
        }


def classify_download_error(error: Exception) -> str:
    """Classify failures without returning downloader messages or credentials."""
    message = str(error).lower()
    bot_markers = ("captcha", "bot challenge", "challenge_required", "not a bot", "automated requests")
    if any(marker in message for marker in bot_markers):
        return "BOT_CHALLENGE"
    auth_markers = ("login", "sign in", "authentication", "cookies", "private account")
    if any(marker in message for marker in auth_markers):
        return "AUTH_REQUIRED"
    if any(marker in message for marker in ("429", "rate limit", "too many requests")):
        return "RATE_LIMITED"
    if any(marker in message for marker in ("403", "forbidden", "blocked")):
        return "ACCESS_DENIED"
    if any(marker in message for marker in ("404", "not found", "unavailable", "deleted")):
        return "MEDIA_NOT_FOUND"
    if any(marker in message for marker in ("unsupported url", "no suitable extractor", "unsupported site")):
        return "UNSUPPORTED"
    if any(marker in message for marker in ("invalid data", "corrupt", "could not find codec", "moov atom not found")):
        return "CORRUPT_MEDIA"
    network_markers = (
        "timed out", "timeout", "connection reset", "connection refused",
        "name or service not known", "temporary failure", "network is unreachable",
    )
    if any(marker in message for marker in network_markers):
        return "NETWORK"
    if any(marker in message for marker in ("ffmpeg", "postprocessing", "post-processing")):
        return "FFMPEG_FAILURE"
    return "DOWNLOADER_BUG"
