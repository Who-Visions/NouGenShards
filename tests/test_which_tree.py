"""Tests for the running-process resolver.

The tool exists because every node verified a redaction fix correctly, in a
clean worktree, and none of them was running it. These tests pin the two
behaviours that make it worth running at all: shadows are reported, and an
empty match set is a failure rather than a silent pass.
"""

import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "which_tree.py"


def _run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, check=False)


def test_no_matching_process_is_a_failure_not_a_pass():
    """'Nothing matched' must never read like 'everything is fine'.

    A deploy gate that exits 0 when it measured nothing is worse than no gate:
    it produces a green line in a log for an unverified service.
    """
    r = _run("--module", "nougen_shards.brain_scan.redaction",
             "--marker", r"re\.compile", "--proc", "a-process-that-cannot-exist-xyzzy")
    assert r.returncode == 1
    assert "NO PROCESS" in r.stderr


def test_resolve_orders_winner_first_and_reports_shadows(tmp_path):
    """The shadow list is the point, not decoration.

    phoebus had nine copies of one module and blade six; the count of the
    winner alone would have hidden how many others were a PYTHONPATH edit away
    from winning instead.
    """
    sys.path.insert(0, str(TOOL.parent))
    try:
        import which_tree
    finally:
        sys.path.pop(0)

    first, second = tmp_path / "a", tmp_path / "b"
    for root, n in ((first, 3), (second, 1)):
        pkg = root / "src" / "pkg" / "sub"
        pkg.mkdir(parents=True)
        (pkg / "mod.py").write_text("re.compile(1)\n" * n, encoding="utf-8")

    hits = which_tree.resolve("pkg.sub.mod", [str(first), str(second)])
    assert len(hits) == 2
    assert hits[0].startswith(str(first)), "first root on the path must win"
    assert which_tree.count(hits[0], r"re\.compile") == 3
    assert which_tree.count(hits[1], r"re\.compile") == 1


def test_count_returns_minus_one_for_an_unreadable_file():
    sys.path.insert(0, str(TOOL.parent))
    try:
        import which_tree
    finally:
        sys.path.pop(0)
    assert which_tree.count("/no/such/file/anywhere", "x") == -1
