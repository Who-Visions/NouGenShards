"""
Tests for handoff live-status reconciliation (Feature 1).

Proves:
  - A handoff with 100% tasks done + clean git tree → "stale-complete"
    even when stored status is "open".
  - reconcile_handoffs(write=False) does NOT mutate files.
  - compute_live_status respects human-set states (acknowledged/in_progress/blocked/complete).
  - compact task summary "N/N tasks completed" is recognised as done.
"""

import json
from unittest.mock import patch

import pytest

# Import the public surface under test
from nougen_shards.handoff import compute_live_status, reconcile_handoffs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def clean_git():
    """Simulate a clean git tree."""
    return {"branch": "main", "changes": [], "commits": []}


@pytest.fixture()
def dirty_git():
    """Simulate uncommitted changes."""
    return {"branch": "main", "changes": ["M src/foo.py"], "commits": []}


def _full_tasks(n_done: int, n_pending: int) -> dict:
    return {
        "completed": [f"task {i}" for i in range(n_done)],
        "in_progress": [],
        "pending": [f"pending {i}" for i in range(n_pending)],
    }


def _compact_tasks(n_done: int, total: int) -> dict:
    return {
        "summary": f"Semantic Anchor: {n_done}/{total} tasks completed.",
        "raw_count": total,
    }


def _handoff(status: str, tasks: dict) -> dict:
    return {
        "handoff_id": "test_id",
        "status": status,
        "goal": "test goal",
        "tasks": tasks,
        "git": {"branch": "main", "changes": [], "commits": []},
        "agent": "claude",
    }


# ---------------------------------------------------------------------------
# Feature 1a: compute_live_status
# ---------------------------------------------------------------------------

class TestComputeLiveStatus:

    def test_all_done_clean_tree_is_stale_complete(self, clean_git):
        """Core case: 8/8 tasks done + clean tree → stale-complete."""
        data = _handoff("open", _full_tasks(8, 0))
        assert compute_live_status(data, clean_git) == "stale-complete"

    def test_partial_tasks_stays_open(self, clean_git):
        data = _handoff("open", _full_tasks(6, 2))
        assert compute_live_status(data, clean_git) == "open"

    def test_all_done_but_dirty_tree_stays_open(self, dirty_git):
        data = _handoff("open", _full_tasks(4, 0))
        assert compute_live_status(data, dirty_git) == "open"

    def test_human_acknowledged_is_respected(self, clean_git):
        data = _handoff("acknowledged", _full_tasks(8, 0))
        assert compute_live_status(data, clean_git) == "acknowledged"

    def test_human_in_progress_is_respected(self, clean_git):
        data = _handoff("in_progress", _full_tasks(8, 0))
        assert compute_live_status(data, clean_git) == "in_progress"

    def test_human_blocked_is_respected(self, clean_git):
        data = _handoff("blocked", _full_tasks(8, 0))
        assert compute_live_status(data, clean_git) == "blocked"

    def test_human_complete_is_respected(self, clean_git):
        data = _handoff("complete", _full_tasks(8, 0))
        assert compute_live_status(data, clean_git) == "complete"

    def test_compact_summary_all_done_clean_is_stale_complete(self, clean_git):
        """Compact 'N/N tasks completed' summary treated as done."""
        data = _handoff("open", _compact_tasks(8, 8))
        assert compute_live_status(data, clean_git) == "stale-complete"

    def test_compact_summary_partial_stays_open(self, clean_git):
        data = _handoff("open", _compact_tasks(5, 8))
        assert compute_live_status(data, clean_git) == "open"

    def test_empty_tasks_stays_open(self, clean_git):
        data = _handoff("open", {"completed": [], "in_progress": [], "pending": []})
        assert compute_live_status(data, clean_git) == "open"

    def test_uses_embedded_git_when_no_override(self):
        """If git_info arg is None, falls back to data['git']."""
        data = _handoff("open", _full_tasks(3, 0))
        data["git"] = {"branch": "main", "changes": [], "commits": []}
        assert compute_live_status(data, None) == "stale-complete"


# ---------------------------------------------------------------------------
# Feature 1b: reconcile_handoffs(write=False) must not mutate files
# ---------------------------------------------------------------------------

class TestReconcileHandoffsNoMutation:

    def test_no_mutation_when_write_false(self, tmp_path):
        """reconcile_handoffs(write=False) must not write to disk."""
        # Build a minimal handoff JSON in a temp dir
        hdir = tmp_path / ".handoffs"
        hdir.mkdir()
        hfile = hdir / "handoff_20250614_120000_main.json"
        data = _handoff("open", _full_tasks(3, 0))
        hfile.write_text(json.dumps(data), encoding="utf-8")

        original_content = hfile.read_text(encoding="utf-8")

        # Patch HANDOFF_DIR so the function finds our temp file
        with patch("nougen_shards.handoff.HANDOFF_DIR", hdir), \
             patch("nougen_shards.handoff.get_git_status",
                   return_value={"branch": "main", "changes": [], "commits": []}):
            counts = reconcile_handoffs(write=False)

        # File must be byte-for-byte unchanged
        assert hfile.read_text(encoding="utf-8") == original_content, \
            "reconcile_handoffs(write=False) must NOT mutate files"

        # Counts sanity
        assert counts["total"] >= 1
        assert counts["stale_complete"] >= 1
        assert counts["actionable"] == 0  # stale-complete is not actionable

    def test_write_true_updates_file(self, tmp_path):
        """reconcile_handoffs(write=True) DOES persist resolved status."""
        hdir = tmp_path / ".handoffs"
        hdir.mkdir()
        hfile = hdir / "handoff_20250614_130000_main.json"
        data = _handoff("open", _full_tasks(2, 0))
        hfile.write_text(json.dumps(data), encoding="utf-8")

        with patch("nougen_shards.handoff.HANDOFF_DIR", hdir), \
             patch("nougen_shards.handoff.HANDOFF_DB_NAME", ":memory:"), \
             patch("nougen_shards.handoff._sync_handoff_to_db", return_value=True), \
             patch("nougen_shards.handoff.get_git_status",
                   return_value={"branch": "main", "changes": [], "commits": []}):
            counts = reconcile_handoffs(write=True)

        updated = json.loads(hfile.read_text(encoding="utf-8"))
        assert updated["status"] == "stale-complete"
        assert counts["stale_complete"] >= 1
