"""Safe, machine-readable failures for media ingestion."""

from urllib.parse import urlsplit, urlunsplit


def public_source(source: str) -> str:
    """Strip URL credentials, query parameters and fragments from diagnostics."""
    parts = urlsplit(source)
    if parts.scheme not in ("http", "https"):
        return "local-media"
    host = parts.hostname or ""
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


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
    if any(marker in message for marker in ("login", "sign in", "authentication", "cookies")):
        return "AUTH_REQUIRED"
    if any(marker in message for marker in ("429", "rate limit", "too many requests")):
        return "RATE_LIMITED"
    if any(marker in message for marker in ("404", "not found", "unavailable")):
        return "MEDIA_UNAVAILABLE"
    if any(marker in message for marker in ("403", "forbidden", "blocked")):
        return "ACCESS_DENIED"
    return "DOWNLOAD_FAILED"
