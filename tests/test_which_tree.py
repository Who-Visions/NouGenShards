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


def test_health_mode_requires_an_explicit_user_agent():
    """The default Python-urllib UA is refused with 403 by the edge.

    Measured 2026-09-08: urllib's default User-Agent got HTTP 403 from a node's
    /health while curl got 200 from the same URL in the same second. A peer had
    reported that 403 hours earlier and it could not be reproduced -- because
    the reproduction attempt used curl. The endpoint was never down; it answers
    some clients and not others, and a health check that only works from one
    HTTP client is not a health check.
    """
    sys.path.insert(0, str(TOOL.parent))
    try:
        import which_tree
    finally:
        sys.path.pop(0)
    captured = {}

    class FakeResponse:
        def read(self):
            return b'{"redaction_patterns": 1, "redaction_fingerprint": "x"}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    import urllib.request
    real = urllib.request.urlopen

    def spy(req, timeout=None):
        captured["ua"] = req.get_header("User-agent")
        return FakeResponse()

    urllib.request.urlopen = spy
    try:
        which_tree.ask_health("https://example.invalid")
    finally:
        urllib.request.urlopen = real

    assert captured["ua"], "no User-Agent was set"
    assert "urllib" not in captured["ua"].lower()


def test_absent_health_fields_are_a_definite_answer(monkeypatch, capsys):
    """A node publishing neither field is running pre-self-report code.

    That is a conclusion, not a gap -- reporting it as "unknown" would discard
    a definite answer and let an out-of-date node read as merely unmeasured.
    """
    sys.path.insert(0, str(TOOL.parent))
    try:
        import which_tree
    finally:
        sys.path.pop(0)

    monkeypatch.setattr(which_tree, "ask_health", lambda url, timeout=30.0: {"status": "ignited"})
    monkeypatch.setattr(sys, "argv",
                        ["which_tree", "--module", "m", "--marker", "x",
                         "--health", "https://example.invalid"])
    assert which_tree.main() == 1
    assert "ABSENT" in capsys.readouterr().out


def test_process_path_survives_the_health_branch_existing(monkeypatch, capsys):
    """Regression: #281 shadowed the module-level count() and broke every real match.

    Adding --health introduced `count = body.get(...)` inside main(), which
    makes `count` a LOCAL name for the entire function — so the process path
    below it died with UnboundLocalError on every --proc that actually matched
    something. It shipped because the new path was tested and the old one was
    only exercised against a NO-match case, which returns before reaching the
    shadowed name.

    Found by whoart running the tool for real on 2026-09-08. This test walks
    the full main() with a matching process and a resolvable module, so the
    two paths can never diverge silently again.
    """
    sys.path.insert(0, str(TOOL.parent))
    try:
        import which_tree
    finally:
        sys.path.pop(0)

    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(which_tree, "pids", lambda pattern: [(1234, "python fake.py")])
    monkeypatch.setattr(which_tree, "cwd_of", lambda pid: str(root))
    monkeypatch.setattr(which_tree, "pythonpath_of", lambda pid: str(root / "src"))
    monkeypatch.setattr(sys, "argv", [
        "which_tree", "--module", "nougen_shards.brain_scan.redaction",
        "--marker", r"re\.compile", "--proc", "fake.py",
    ])

    rc = which_tree.main()
    out = capsys.readouterr().out
    assert "WINS" in out, out
    assert "marker=" in out
    assert rc == 0


def test_health_branch_does_not_bind_a_name_used_elsewhere():
    """Guards the specific mistake rather than only its symptom.

    A local named `count` in main() is always a bug here, because the process
    path calls the module-level count(). Asserting on the source is crude, but
    it fails loudly at the moment someone reintroduces the shadow rather than
    only when a live process happens to match.
    """
    source = TOOL.read_text(encoding="utf-8")
    body = source.split("def main(")[1]
    assert "\n        count = " not in body, "main() rebinds count(); use another name"
