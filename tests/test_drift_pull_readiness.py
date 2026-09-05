"""Pull-readiness is judged against the branch's OWN upstream, not the
canonical ref.

Regression for a defect that fired twice on 2026-09-03, on two different
nodes, from one wrong comparison. A clone sitting on a feature branch has a
HEAD that is not an ancestor of origin/main -- that is what a branch IS -- and
the check reported it as PULL-BLOCKED with "a polling watcher here has already
stopped learning". On blade that escalated a destructive-change ruling to the
owner for a watcher that was in fact perfectly current; the clone it proposed
discarding held that day's uncommitted work. On phoebus it fired against the
live checkout minutes later.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import drift_check  # noqa: E402


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def origin_and_clone(tmp_path):
    """A bare 'origin' with main, plus a clone that can branch off it."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    _git(seed, "config", "user.email", "t@example.invalid")
    _git(seed, "config", "user.name", "t")
    (seed / "tools").mkdir()
    (seed / "tools" / "nougenmsg_node.py").write_text("canonical\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "seed")
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(origin)],
                   check=True, capture_output=True)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)],
                   check=True, capture_output=True)
    _git(clone, "config", "user.email", "t@example.invalid")
    _git(clone, "config", "user.name", "t")
    return origin, clone


def _states(clone):
    return [row[0] for row in drift_check.pull_health(Path(clone))]


def test_feature_branch_with_own_upstream_is_not_pull_blocked(origin_and_clone):
    """The exact shape that produced both false incidents."""
    origin, clone = origin_and_clone
    _git(clone, "checkout", "-q", "-b", "feature")
    (clone / "tools" / "extra.py").write_text("work in progress\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "feature work")
    _git(clone, "push", "-q", "-u", "origin", "feature")

    # Main moves on, so HEAD is genuinely not an ancestor of origin/main.
    _git(clone, "checkout", "-q", "main")
    (clone / "tools" / "on_main.py").write_text("later\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "main moves")
    _git(clone, "push", "-q", "origin", "main")
    _git(clone, "checkout", "-q", "feature")
    _git(clone, "fetch", "-q", "origin")

    ancestor = subprocess.run(
        ["git", "-C", str(clone), "merge-base", "--is-ancestor", "HEAD", "origin/main"],
        capture_output=True)
    assert ancestor.returncode != 0, "precondition: HEAD is not an ancestor of main"

    assert "PULL-BLOCKED" not in _states(clone)
    assert "NO-UPSTREAM" not in _states(clone)


def test_genuinely_diverged_branch_is_still_pull_blocked(origin_and_clone):
    """The real failure the check exists to catch must still be caught."""
    origin, clone = origin_and_clone
    _git(clone, "checkout", "-q", "-b", "feature")
    (clone / "a.py").write_text("a\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "a")
    _git(clone, "push", "-q", "-u", "origin", "feature")
    mine = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()

    # Upstream is rewritten under us onto a sibling commit, so HEAD is no
    # longer an ancestor of its OWN upstream and no fast-forward is possible.
    # That is a true block and must still be reported.
    _git(clone, "reset", "-q", "--hard", "HEAD~1")
    (clone / "b.py").write_text("b\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "b")
    _git(clone, "push", "-q", "--force", "origin", "feature")
    _git(clone, "reset", "-q", "--hard", mine)
    _git(clone, "fetch", "-q", "origin")

    ancestor = subprocess.run(
        ["git", "-C", str(clone), "merge-base", "--is-ancestor", "HEAD",
         "origin/feature"], capture_output=True)
    assert ancestor.returncode != 0, "precondition: HEAD diverged from its upstream"

    assert "PULL-BLOCKED" in _states(clone)


def test_branch_without_upstream_is_unknown_not_blocked(origin_and_clone):
    origin, clone = origin_and_clone
    _git(clone, "checkout", "-q", "-b", "local-only")
    (clone / "c.py").write_text("c\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "c")

    states = _states(clone)
    assert "NO-UPSTREAM" in states
    assert "PULL-BLOCKED" not in states


def test_modified_tracked_file_still_reports_pull_risk(origin_and_clone):
    origin, clone = origin_and_clone
    (clone / "tools" / "nougenmsg_node.py").write_text("locally changed\n")
    assert "PULL-RISK" in _states(clone)
