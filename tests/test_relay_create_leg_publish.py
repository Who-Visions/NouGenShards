"""relay_create_leg: real lane byline, .md + .json pair, and publish to the registry clone.

Before this, every leg was stamped ``phoebus/antigravity`` whatever box wrote it, only
the .md was written (relay tools read the .json), and it landed in ``~/.nougen/relay``,
which is not a git clone, so no other lane ever saw it.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("gradio")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as node  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """A registry clone with a bare origin, wired in through NOUGEN_RELAY_REGISTRY."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    clone = tmp_path / "nougenrelay"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "config", "user.email", "test@example.invalid")
    _git(clone, "config", "user.name", "test")
    (clone / ".handoffs").mkdir()
    (clone / ".handoffs" / ".keep").write_text("")
    _git(clone, "add", ".")
    _git(clone, "commit", "-q", "-m", "init")
    _git(clone, "push", "-q", "-u", "origin", "main")
    monkeypatch.setenv("NOUGEN_RELAY_REGISTRY", str(clone))
    monkeypatch.setenv("NOUGEN_MACHINE", "testbox")
    monkeypatch.delenv("NOUGEN_AGENT", raising=False)
    return clone, origin


def test_leg_uses_this_lane_not_a_hardcoded_one(registry):
    out = node.relay_create_leg.fn("goal one", body="b", agent="claude-cli")
    assert out["leg_id"].endswith("__testbox__claude-cli")
    assert "phoebus" not in out["leg_id"]
    md = Path(out["file"]).read_text(encoding="utf-8")
    assert "testbox / claude-cli" in md


def test_leg_writes_a_valid_json_sidecar(registry):
    out = node.relay_create_leg.fn("goal two", agent="claude-cli")
    meta = json.loads(Path(out["meta_file"]).read_text(encoding="utf-8"))
    assert meta["id"] == out["leg_id"]
    assert (meta["machine"], meta["agent"], meta["status"]) == ("testbox", "claude-cli", "open")
    assert meta["goal"] == "goal two"
    assert meta["relay"] == []


def test_leg_is_committed_and_pushed_to_the_registry(registry):
    clone, origin = registry
    out = node.relay_create_leg.fn("goal three", agent="claude-cli")
    assert out["published"] is True, out
    assert Path(out["file"]).parent == clone / ".handoffs"
    pushed = _git(origin, "ls-tree", "--name-only", "main", ".handoffs/")
    assert f".handoffs/{out['leg_id']}.md" in pushed
    assert f".handoffs/{out['leg_id']}.json" in pushed
    assert _git(clone, "status", "--porcelain") == ""


def test_publish_false_keeps_the_leg_off_the_registry(registry):
    clone, _ = registry
    out = node.relay_create_leg.fn("draft", agent="claude-cli", publish=False)
    assert out["published"] is False
    assert clone not in Path(out["file"]).parents


def test_no_registry_clone_reports_unpublished(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_RELAY_REGISTRY", str(tmp_path / "missing"))
    monkeypatch.setenv("NOUGEN_MACHINE", "testbox")
    monkeypatch.setattr(node, "_relay_handoffs_dir", lambda: tmp_path / "board" / ".handoffs")
    out = node.relay_create_leg.fn("local only", agent="claude-cli")
    assert out["published"] is False
    assert "NOUGEN_RELAY_REGISTRY" in out["error"]
    assert Path(out["file"]).exists() and Path(out["meta_file"]).exists()


def test_claim_and_ack_default_to_this_lane(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_MACHINE", "testbox")
    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    monkeypatch.setattr(node, "_relay_handoffs_dir", lambda: tmp_path / ".handoffs")
    leg = "20261119T000000Z__other__agent"
    assert node.relay_claim_leg.fn(leg)["claim"]["claimed_by"] == "testbox/claude-cli"
    assert node.relay_ack_leg.fn(leg, "artifact", "pass")["proof"]["closed_by"] == "testbox"
