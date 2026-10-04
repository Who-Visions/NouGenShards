"""Label fleet claims that carry no checkable evidence.

2026-10-04 (leg 20261004T190617Z): of four fleet broadcasts blade re-verified, three were wrong
at implied certainty ("PR landed" while open, "19 equations operationalized" with no artifact,
"no config entry" when it was at line ~90). A reader cannot weigh a claim it cannot check.

``label_claim(text)`` prefixes ``[UNVERIFIED]`` when a message asserts a completed state
(merged, landed, passed, fixed, ...) but cites nothing a reader could check: a PR/issue
number or URL, a commit sha, a ``path:line`` reference, a relay leg id or shard id.
It does not judge truth; it only makes the absence of evidence visible.
"""
from __future__ import annotations

import re

LABEL = "[UNVERIFIED: no evidence ref]"

_CLAIM = re.compile(
    r"\b(merged|landed|shipped|deployed|complete[d]?|passed|green|fixed|resolved|verified|"
    r"operationali[sz]ed|implemented|done|closed|reconciled)\b",
    re.IGNORECASE,
)

_EVIDENCE = re.compile(
    r"(https?://\S+"                                   # any URL
    r"|\b[\w.-]+/[\w.-]+#\d+\b"                        # owner/repo#123
    r"|\b(?:PR|pull|issue)\s*#?\d+\b"                  # PR #123 / PR 123
    r"|(?<![\w/])#\d{2,}\b"                            # #705
    r"|\b[0-9a-f]{7,40}\b"                             # commit sha
    r"|\b[\w./\\-]+\.\w{1,5}:\d+\b"                    # path/file.py:42
    r"|\b\d{8}T\d{6}Z__[\w-]+"                         # relay leg id
    r"|\bshard[ _:#]*\d{3,}\b)",                       # shard 30744
    re.IGNORECASE,
)


def has_claim(text: str) -> bool:
    return bool(_CLAIM.search(text or ""))


def has_evidence(text: str) -> bool:
    return bool(_EVIDENCE.search(text or ""))


def label_claim(text: str) -> str:
    """Prefix LABEL when ``text`` asserts a completed state without any checkable reference."""
    if not text or LABEL in text:
        return text
    if has_claim(text) and not has_evidence(text):
        return f"{LABEL} {text}"
    return text
