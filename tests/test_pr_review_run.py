"""`ngs pr review` called pr_review.run_review, which did not exist (AttributeError)."""
import json

import pytest

from nougen_shards import pr_review

F = pr_review.Finding


def _stub(monkeypatch, existing=None, error=None):
    posted = []
    def fake_list(repo, pr):
        if error:
            raise RuntimeError(error)
        return existing or []
    monkeypatch.setattr(pr_review, "list_review_comments", fake_list)
    monkeypatch.setattr(pr_review, "_post_comment", lambda *a: posted.append(a))
    monkeypatch.setattr(pr_review, "_patch_comment", lambda *a: posted.append(("patch", *a)))
    return posted


def test_run_review_exists():
    assert callable(pr_review.run_review)


def test_no_findings_reports_existing(monkeypatch):
    _stub(monkeypatch, existing=[{"id": 1, "path": "a", "line": 1, "body": "x", "fingerprint": None}])
    res = pr_review.run_review("o/r", 5, "obj")
    assert res["status"] == "no_findings"
    assert res["comments_count"] == 0 and res["existing_comments"] == 1


def test_gh_failure_is_error_status(monkeypatch):
    _stub(monkeypatch, error="gh CLI not found on PATH")
    res = pr_review.run_review("o/r", 5, "obj")
    assert res["status"] == "error" and "gh CLI" in res["error"]
    assert res["comments_count"] == 0


def test_dry_run_counts_without_posting(monkeypatch):
    f_old, f_new = F("a.py", 1, "old"), F("b.py", 2, "new")
    existing = [{"id": 9, "path": "a.py", "line": 1, "body": "", "fingerprint": f_old.fp}]
    posted = _stub(monkeypatch, existing=existing)
    res = pr_review.run_review("o/r", 5, "obj", dry_run=True, findings=[f_old, f_new])
    assert res["status"] == "dry_run" and res["comments_count"] == 1 and res["skipped"] == 1
    assert posted == []


def test_posts_new_findings_once(monkeypatch):
    posted = _stub(monkeypatch)
    res = pr_review.run_review("o/r", 5, "obj", findings=[F("a.py", 3, "bug")], commit_id="abc")
    assert res["status"] == "posted" and res["comments_count"] == 1
    assert len(posted) == 1


def test_missing_head_sha_lookup_failure(monkeypatch):
    _stub(monkeypatch)
    def boom(args, input_payload=None):
        raise RuntimeError("gh api failed")
    monkeypatch.setattr(pr_review, "_gh_json", boom)
    res = pr_review.run_review("o/r", 5, "obj", findings=[F("a.py", 3, "bug")])
    assert res["status"] == "error"


def test_cli_pr_review_prints_status(monkeypatch, capsys):
    from nougen_shards import cli
    _stub(monkeypatch)
    monkeypatch.setattr("sys.argv", ["ngs", "pr", "review", "--repo", "o/r", "--pr", "5",
                                     "--objective", "x", "--json"])
    try:
        cli.main()
    except SystemExit:
        pass
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "no_findings"
