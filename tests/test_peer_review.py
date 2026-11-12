"""tools/peer_review.py: the refusals that keep a review honest, all offline."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "peer_review", Path(__file__).resolve().parents[1] / "tools" / "peer_review.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)


def _state(**kw):
    s = {"state": "OPEN", "author": {"login": "WhoVisions"},
         "statusCheckRollup": [{"name": "tests", "conclusion": "SUCCESS"},
                               {"name": "scorecard", "conclusion": "SKIPPED"}]}
    s.update(kw)
    return s


def test_green_pr_from_another_author_can_be_approved():
    pr.check_review_allowed(_state(), "approve", "go test ok, hashes match")


def test_empty_body_is_refused():
    with pytest.raises(SystemExit, match="evidence"):
        pr.check_review_allowed(_state(), "approve", "  ")


def test_failing_check_blocks_approval_but_not_request_changes():
    s = _state(statusCheckRollup=[{"name": "tests", "conclusion": "FAILURE"}])
    with pytest.raises(SystemExit, match="tests=FAILURE"):
        pr.check_review_allowed(s, "approve", "x")
    pr.check_review_allowed(s, "request-changes", "tests fail")


def test_pending_check_blocks_approval():
    s = _state(statusCheckRollup=[{"name": "ci", "status": "IN_PROGRESS"}])
    with pytest.raises(SystemExit):
        pr.check_review_allowed(s, "approve", "x")


def test_reviewer_cannot_review_its_own_pr():
    with pytest.raises(SystemExit, match="cannot review"):
        pr.check_review_allowed(_state(author={"login": pr.REVIEWER}), "approve", "x")


def test_closed_pr_is_refused():
    with pytest.raises(SystemExit, match="MERGED"):
        pr.check_review_allowed(_state(state="MERGED"), "comment", "x")


def test_tool_has_no_merge_path():
    src = Path(pr.__file__).read_text()
    assert '"merge"' not in src and "'merge'" not in src
