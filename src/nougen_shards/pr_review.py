"""Incremental review + persistent deduped review comments.

Phase 2 of the SHANG TSUNG PR-Agent absorption (relay leg
20260908T025803Z__chatgpt-app__g-whoentertains; Phase 1 in pr_lease.py,
landed as PR #289). Two problems, one module:

1. INCREMENTAL REVIEW. A PR that gathers commits over days shouldn't be
   re-read from scratch every pass. `Lease.last_reviewed_sha` (added in
   Phase 1 but unused until now) is the checkpoint: `incremental_review_window`
   diffs only what landed since it, and `LeaseStore.mark_reviewed` advances
   it once that delta has actually been looked at.

2. DEDUPED COMMENTS. Re-running a reviewer against the same PR must not
   repost findings that are already there. Source of truth is GitHub's own
   review comments, not a local cache -- per the fleet's 2026-09-08 scoring
   doctrine (relay leg 20260908T030907Z), a claim a stranger can't verify
   with one `gh` call is worth nothing, and a local dedup store would be
   exactly that kind of claim on a second machine. Every comment this module
   posts carries an embedded `<!-- nougen-review-fp:<hash> -->` marker keyed
   on (file, line, normalized text); a second run reads that marker back off
   the live PR to decide skip / update / post.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from . import pr_lease

FINGERPRINT_MARKER = "nougen-review-fp"
_MARKER_RE = re.compile(rf"<!-- {FINGERPRINT_MARKER}:([0-9a-f]{{16}}) -->")


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _run_git(repo_path: str, args: list[str]) -> str:
    out = subprocess.run(
        ["git", "-C", repo_path, *args], capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def head_sha(repo_path: str) -> str:
    return _run_git(repo_path, ["rev-parse", "HEAD"]).strip()


def commits_since(repo_path: str, since_sha: Optional[str], until: str = "HEAD") -> list[str]:
    """New commit SHAs since `since_sha` (exclusive), oldest first.

    All commits reachable from `until` when `since_sha` is None (first
    review of this lease -- nothing has been checkpointed yet).
    """
    rev_range = f"{since_sha}..{until}" if since_sha else until
    out = _run_git(repo_path, ["rev-list", "--reverse", rev_range])
    return [line for line in out.splitlines() if line]


def diff_since(repo_path: str, since_sha: Optional[str], until: str = "HEAD") -> str:
    """Unified diff of everything new since `since_sha`.

    Empty string when `since_sha == until` -- nothing new, nothing to
    review, and callers should treat that as "skip", not "review a blank".
    """
    if since_sha == until:
        return ""
    args = ["diff", f"{since_sha}..{until}"] if since_sha else ["show", "--format=", until]
    return _run_git(repo_path, args)


@dataclass
class ReviewWindow:
    since_sha: Optional[str]
    until_sha: str
    new_commits: list[str]
    diff: str

    @property
    def commit_count(self) -> int:
        return len(self.new_commits)

    @property
    def is_empty(self) -> bool:
        return self.commit_count == 0


def incremental_review_window(repo_path: str, lease: pr_lease.Lease) -> ReviewWindow:
    """The delta a reviewer should actually look at: commits landed since
    the lease's checkpoint. `is_empty` means the PR hasn't moved since the
    last review pass -- callers should skip re-reviewing it entirely rather
    than re-diffing HEAD against itself."""
    until = head_sha(repo_path)
    new_commits = commits_since(repo_path, lease.last_reviewed_sha, until)
    diff_text = diff_since(repo_path, lease.last_reviewed_sha, until) if new_commits else ""
    return ReviewWindow(
        since_sha=lease.last_reviewed_sha, until_sha=until,
        new_commits=new_commits, diff=diff_text,
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def fingerprint(file: str, line: int, text: str) -> str:
    """Stable id for a finding, independent of when/who posts it. Two runs
    that produce the same complaint at the same spot get the same
    fingerprint even with unrelated whitespace/casing drift in the wording."""
    digest = hashlib.sha256(f"{file}:{line}:{_normalize(text)}".encode("utf-8")).hexdigest()
    return digest[:16]


@dataclass
class Finding:
    file: str
    line: int
    body: str

    @property
    def fp(self) -> str:
        return fingerprint(self.file, self.line, self.body)


def embed_marker(body: str, fp: str) -> str:
    return f"{body}\n\n<!-- {FINGERPRINT_MARKER}:{fp} -->"


def extract_marker(body: str) -> Optional[str]:
    m = _MARKER_RE.search(body or "")
    return m.group(1) if m else None


def _gh_json(args: list[str], input_payload: Optional[dict] = None) -> object:
    if not _gh_available():
        raise RuntimeError("gh CLI not found on PATH")
    kwargs = dict(capture_output=True, text=True, timeout=30)
    if input_payload is not None:
        kwargs["input"] = json.dumps(input_payload)
    out = subprocess.run(["gh", *args], **kwargs)
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {out.stderr.strip()}")
    text = out.stdout.strip()
    if not text:
        return []
    # --paginate can concatenate multiple top-level JSON arrays back to back;
    # decode them one at a time instead of assuming a single JSON document.
    decoder = json.JSONDecoder()
    results: list = []
    idx = 0
    while idx < len(text):
        chunk = text[idx:].lstrip()
        if not chunk:
            break
        obj, consumed = decoder.raw_decode(chunk)
        results.extend(obj if isinstance(obj, list) else [obj])
        idx += (len(text[idx:]) - len(chunk)) + consumed
    return results


def list_review_comments(repo: str, pr_number: int) -> list[dict]:
    """Existing review comments on a PR, each carrying its fingerprint (None
    if it wasn't posted by this module). This is the live GitHub state --
    the only thing dedup decisions are allowed to trust."""
    raw = _gh_json(["api", f"repos/{repo}/pulls/{pr_number}/comments", "--paginate"])
    return [
        {
            "id": c["id"], "path": c.get("path"),
            "line": c.get("line") or c.get("original_line"),
            "body": c.get("body", ""),
            "fingerprint": extract_marker(c.get("body", "")),
        }
        for c in raw
    ]


def _post_comment(repo: str, pr_number: int, commit_id: str, path: str, line: int, body: str) -> None:
    _gh_json(
        ["api", f"repos/{repo}/pulls/{pr_number}/comments", "--input", "-"],
        input_payload={"body": body, "commit_id": commit_id, "path": path, "line": line, "side": "RIGHT"},
    )


def _patch_comment(repo: str, comment_id: int, body: str) -> None:
    _gh_json(
        ["api", "--method", "PATCH", f"repos/{repo}/pulls/comments/{comment_id}", "--input", "-"],
        input_payload={"body": body},
    )


def sync_review_comments(
    repo: str, pr_number: int, commit_id: str, findings: list[Finding],
) -> dict:
    """Post each finding exactly once. A finding whose (file, line, text)
    fingerprint already has a live, unchanged comment is skipped; the same
    file/line with different text (a refined message for the same spot) is
    PATCHed in place; anything new is POSTed. Returns counts, not IDs -- the
    IDs are on GitHub, which is the point."""
    existing = list_review_comments(repo, pr_number)
    known_fps = {c["fingerprint"] for c in existing if c["fingerprint"]}
    by_loc: dict[tuple, list[dict]] = defaultdict(list)
    for c in existing:
        if c["fingerprint"]:
            by_loc[(c["path"], c["line"])].append(c)

    posted = updated = skipped = 0
    for finding in findings:
        fp = finding.fp
        if fp in known_fps:
            skipped += 1
            continue
        loc_matches = by_loc.get((finding.file, finding.line), [])
        if loc_matches:
            _patch_comment(repo, loc_matches[0]["id"], embed_marker(finding.body, fp))
            updated += 1
        else:
            _post_comment(repo, pr_number, commit_id, finding.file, finding.line, embed_marker(finding.body, fp))
            posted += 1
    return {"posted": posted, "updated": updated, "skipped": skipped, "total": len(findings)}
