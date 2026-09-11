"""Phase 2 of the SHANG TSUNG PR-Agent absorption: incremental review windows
and deduped review comments.

The git-window tests use a real temp git repo (hermetic, no network). The
comment-dedup tests fake `gh` via monkeypatched subprocess.run so no network
or GitHub token is required to run them.
"""
import json
import subprocess
from pathlib import Path

import pytest

from nougen_shards import pr_lease, pr_review


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return out.stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "test@example.com")
    _git(r, "config", "user.name", "Test")
    (r / "a.txt").write_text("one\n")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-q", "-m", "first")
    return r


def _make_lease(repo_name="owner/repo", objective="test objective", last_reviewed_sha=None):
    return pr_lease.Lease(
        objective=objective, objective_key=pr_lease._slug(objective),
        repo=repo_name, branch="feat/test", last_reviewed_sha=last_reviewed_sha,
        chained_objectives=[objective],
    )


# --- incremental review window ---------------------------------------------

def test_first_review_covers_everything_reachable(repo):
    (repo / "b.txt").write_text("two\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "second")

    lease = _make_lease(last_reviewed_sha=None)
    window = pr_review.incremental_review_window(str(repo), lease)

    assert window.commit_count == 2
    assert not window.is_empty
    assert window.since_sha is None
    assert window.until_sha == pr_review.head_sha(str(repo))


def test_second_review_only_sees_the_new_delta(repo):
    first_sha = pr_review.head_sha(str(repo))
    (repo / "b.txt").write_text("two\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "second")

    lease = _make_lease(last_reviewed_sha=first_sha)
    window = pr_review.incremental_review_window(str(repo), lease)

    assert window.commit_count == 1
    assert "b.txt" in window.diff
    assert "a.txt" not in window.diff  # already-reviewed content stays out


def test_nothing_new_since_checkpoint_is_empty(repo):
    head = pr_review.head_sha(str(repo))
    lease = _make_lease(last_reviewed_sha=head)
    window = pr_review.incremental_review_window(str(repo), lease)

    assert window.is_empty
    assert window.diff == ""
    assert window.new_commits == []


def test_mark_reviewed_advances_checkpoint_independent_of_record_push(tmp_path):
    store = pr_lease.LeaseStore(path=tmp_path / "state.json")
    store.attach_objective("owner/repo", "test objective")

    store.mark_reviewed("owner/repo", "test objective", "deadbeef")
    lease = store.get("owner/repo", "test objective")
    assert lease.last_reviewed_sha == "deadbeef"
    assert lease.commit_count == 0  # record_push's counter is untouched

    store.record_push("owner/repo", "test objective", "cafef00d")
    lease = store.get("owner/repo", "test objective")
    assert lease.commit_count == 1
    assert lease.last_reviewed_sha == "cafef00d"  # record_push still sets its own


def test_mark_reviewed_without_a_lease_raises():
    store = pr_lease.LeaseStore(path=Path("does-not-matter.json"))
    store._data = {}
    with pytest.raises(KeyError):
        store.mark_reviewed("owner/repo", "no such objective", "sha")


# --- fingerprinting ----------------------------------------------------------

def test_fingerprint_stable_across_whitespace_and_case():
    a = pr_review.fingerprint("f.py", 10, "Unused import  os")
    b = pr_review.fingerprint("f.py", 10, "unused import os")
    assert a == b


def test_fingerprint_distinguishes_location_and_text():
    base = pr_review.fingerprint("f.py", 10, "unused import os")
    assert pr_review.fingerprint("f.py", 11, "unused import os") != base
    assert pr_review.fingerprint("g.py", 10, "unused import os") != base
    assert pr_review.fingerprint("f.py", 10, "something else") != base


def test_marker_roundtrip():
    fp = pr_review.fingerprint("f.py", 1, "x")
    body = pr_review.embed_marker("finding text", fp)
    assert pr_review.extract_marker(body) == fp
    assert pr_review.extract_marker("no marker here") is None


# --- comment dedup (gh faked) -----------------------------------------------

class _FakeGh:
    """Records calls; serves canned `gh api ... comments` list responses and
    accepts POST/PATCH without hitting the network."""

    def __init__(self, existing_comments):
        self.existing = existing_comments
        self.calls = []

    def __call__(self, args, capture_output, text, timeout, input=None):
        self.calls.append((args, input))
        if "--paginate" in args:  # list existing comments
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(self.existing), stderr="")
        if "--method" in args or "--input" in args:  # PATCH update or POST new
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")


def test_sync_skips_identical_fingerprint(monkeypatch):
    fp = pr_review.fingerprint("f.py", 10, "unused import os")
    existing = [{"id": 1, "path": "f.py", "line": 10, "body": pr_review.embed_marker("unused import os", fp)}]
    fake = _FakeGh(existing)
    monkeypatch.setattr(pr_review.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(pr_review.subprocess, "run", fake)

    result = pr_review.sync_review_comments(
        "owner/repo", 5, "abc123", [pr_review.Finding("f.py", 10, "unused import os")],
    )
    assert result == {"posted": 0, "updated": 0, "skipped": 1, "total": 1}


def test_sync_updates_same_location_different_text(monkeypatch):
    old_fp = pr_review.fingerprint("f.py", 10, "old message")
    existing = [{"id": 42, "path": "f.py", "line": 10, "body": pr_review.embed_marker("old message", old_fp)}]
    fake = _FakeGh(existing)
    monkeypatch.setattr(pr_review.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(pr_review.subprocess, "run", fake)

    result = pr_review.sync_review_comments(
        "owner/repo", 5, "abc123", [pr_review.Finding("f.py", 10, "new refined message")],
    )
    assert result == {"posted": 0, "updated": 1, "skipped": 0, "total": 1}
    patch_calls = [c for c in fake.calls if "--method" in c[0]]
    assert len(patch_calls) == 1
    assert "repos/owner/repo/pulls/comments/42" in patch_calls[0][0]


def test_sync_posts_new_finding(monkeypatch):
    fake = _FakeGh(existing_comments=[])
    monkeypatch.setattr(pr_review.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(pr_review.subprocess, "run", fake)

    result = pr_review.sync_review_comments(
        "owner/repo", 5, "abc123", [pr_review.Finding("f.py", 10, "brand new finding")],
    )
    assert result == {"posted": 1, "updated": 0, "skipped": 0, "total": 1}
    post_calls = [c for c in fake.calls if "--input" in c[0] and "repos/owner/repo/pulls/5/comments" in c[0]]
    assert len(post_calls) == 1


def test_sync_requires_gh(monkeypatch):
    monkeypatch.setattr(pr_review.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="gh CLI not found"):
        pr_review.sync_review_comments("owner/repo", 5, "abc123", [pr_review.Finding("f.py", 1, "x")])
