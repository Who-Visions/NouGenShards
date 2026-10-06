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

import os
import re
import subprocess
from functools import lru_cache
from typing import Callable, Optional

LABEL = "[UNVERIFIED: no evidence ref]"

_CLAIM = re.compile(
    r"\b(merged|landed|shipped|deployed|complete[d]?|passed|green|fixed|resolved|verified|"
    r"operationali[sz]ed|implemented|done|closed|reconciled|checkpointed)\b",
    re.IGNORECASE,
)

# A claim word is not an assertion when negated shortly before it ("not done", "nothing has landed").
_NEGATORS = re.compile(r"\b(?:not|no|nothing|never|yet|without|until|isn't|wasn't|hasn't|haven't|won't)\b|n't\b",
                       re.IGNORECASE)

_EVIDENCE = re.compile(
    r"(https?://\S+"                                   # any URL
    r"|\b[\w.-]+/[\w.-]+#\d+\b"                        # owner/repo#123
    r"|\b(?:PR|pull|issue)\s*#?\d+\b"                  # PR #123 / PR 123
    r"|(?<![\w/])#\d{2,}\b"                            # #705
    r"|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"  # commit sha: needs a digit AND an a-f letter
    r"|\b[\w./\\-]+\.\w{1,5}:\d+\b"                    # path/file.py:42
    r"|\b\d{8}T\d{6}Z__[\w-]+"                         # relay leg id
    r"|\bshard[ _:#]*\d{3,}\b)",                       # shard 30744
    re.IGNORECASE,
)


def has_claim(text: str) -> bool:
    """True when ``text`` asserts a completed state; negated mentions ("not done") do not count."""
    text = text or ""
    for m in _CLAIM.finditer(text):
        if not _NEGATORS.search(" ".join(text[:m.start()].split()[-4:])):
            return True
    return False


def has_evidence(text: str) -> bool:
    return bool(_EVIDENCE.search(text or ""))


def label_claim(text: str) -> str:
    """Prefix LABEL when ``text`` asserts a completed state without any checkable reference."""
    if not text or LABEL in text:
        return text
    if has_claim(text) and not has_evidence(text):
        return f"{LABEL} {text}"
    return text


# --- Referenced-but-false claims -------------------------------------------------------------
# Experiment 2026-10-04 (leg 20261004T192122Z): only 4 of 32 completion claims lacked a ref, but
# most false claims DID cite one ("#711 landed" while #711 was open). For merge-type claims that
# cite a PR, compare against the PR's live state.

MISMATCH = "[CLAIM MISMATCH]"
PR_CHECK_ENV = "NOUGEN_CLAIM_PR_CHECK"   # "1" enables the live gh lookup on the wire (off by default: network)
DEFAULT_REPO_ENV = "NOUGEN_CLAIM_DEFAULT_REPO"  # owner/repo for bare "#N" refs, e.g. Who-Visions/NouGenShards

_MERGE_CLAIM = re.compile(r"\b(merged|landed|shipped)\b", re.IGNORECASE)
_PR_REF = re.compile(r"(?:\b([\w.-]+/[\w.-]+)#(\d+)\b|github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)|(?<![\w/])(?:PR\s*)?#(\d{2,})\b)",
                     re.IGNORECASE)


@lru_cache(maxsize=256)
def gh_pr_state(repo: str, number: int) -> Optional[str]:
    """MERGED / OPEN / CLOSED via the gh CLI, or None if unavailable."""
    try:
        out = subprocess.run(["gh", "pr", "view", str(number), "--repo", repo, "--json", "state", "-q", ".state"],
                             capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    state = out.stdout.strip().upper()
    return state or None


def pr_refs(text: str, default_repo: Optional[str] = None):
    for m in _PR_REF.finditer(text or ""):
        repo = m.group(1) or m.group(3) or default_repo
        num = m.group(2) or m.group(4) or m.group(5)
        if repo and num:
            yield repo, int(num)


def check_merge_claims(text: str, lookup: Callable[[str, int], Optional[str]] = gh_pr_state,
                       default_repo: Optional[str] = None) -> str:
    """Append a mismatch note when a merge-type claim cites a PR whose live state is not MERGED."""
    if not text or MISMATCH in text or not _MERGE_CLAIM.search(text):
        return text
    default_repo = default_repo or os.environ.get(DEFAULT_REPO_ENV)
    notes = []
    for repo, num in dict.fromkeys(pr_refs(text, default_repo)):
        state = lookup(repo, num)
        if state and state != "MERGED":
            notes.append(f"{repo}#{num} is {state}")
    return f"{text}\n{MISMATCH} " + "; ".join(notes) if notes else text
