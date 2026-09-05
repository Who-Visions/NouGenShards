"""The gate: decides whether a failed primary write is diverted into the dam.

Only *retryable infrastructure* failures are damned. A 401 will still be a 401
after replay, and a 400 will still be malformed -- queueing those manufactures
a backlog of events that can never drain, which is worse than failing loudly.
"""
from __future__ import annotations

import re
from typing import Optional

# Infrastructure said "not now". The write is still valid.
RETRYABLE_STATUS = frozenset({502, 503, 504})

# Rate limiting is retryable only after the local retry budget is spent,
# otherwise a burst becomes a dam full of events the primary would have
# accepted a second later.
RATE_LIMIT_STATUS = 429

# The request itself is wrong, or we are not allowed. Never damned.
NONRETRYABLE_STATUS = frozenset({400, 401, 403, 404, 409, 422})

_TRANSPORT_RETRYABLE = re.compile(
    r"timed?\s*out|timeout|connection\s+(reset|refused|aborted)|"
    r"temporary failure|broken pipe|remote end closed",
    re.I,
)


class Decision:
    """Why the gate ruled as it did. The reason is carried, not just the verdict."""

    __slots__ = ("divert", "reason", "terminal")

    def __init__(self, divert: bool, reason: str, terminal: bool = False):
        self.divert = divert
        self.reason = reason
        # terminal => do not retry the primary either; surface a hard failure.
        self.terminal = terminal

    def __repr__(self) -> str:
        return (f"Decision(divert={self.divert}, terminal={self.terminal}, "
                f"reason={self.reason!r})")


def classify(status: Optional[int] = None, error: Optional[BaseException] = None,
             *, retries_exhausted: bool = False) -> Decision:
    """Rule on one failed primary write.

    `retries_exhausted` refers to the caller's LOCAL retry budget against the
    primary. The dam is the last resort, not the first.
    """
    if status is not None:
        if 200 <= status < 300:
            return Decision(False, f"primary accepted ({status})")
        if status in NONRETRYABLE_STATUS:
            return Decision(False, f"non-retryable HTTP {status}", terminal=True)
        if status == RATE_LIMIT_STATUS:
            if retries_exhausted:
                return Decision(True, "429 after local retry budget exhausted")
            return Decision(False, "429 — retry locally before damming")
        if status in RETRYABLE_STATUS:
            return Decision(True, f"retryable HTTP {status}")
        if 500 <= status < 600:
            return Decision(True, f"server error HTTP {status}")
        return Decision(False, f"unclassified HTTP {status}", terminal=True)

    if error is not None:
        if _TRANSPORT_RETRYABLE.search(str(error)):
            if retries_exhausted:
                return Decision(True, f"transport failure: {type(error).__name__}")
            return Decision(False, "transport failure — retry locally first")
        return Decision(False, f"unclassified error: {type(error).__name__}",
                        terminal=True)

    return Decision(False, "no failure reported")
