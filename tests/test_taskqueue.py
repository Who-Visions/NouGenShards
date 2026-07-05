import tempfile
from pathlib import Path

import pytest

from nougen_shards import handoff, nougen_context, taskqueue


@pytest.fixture(autouse=True)
def setup_queue_env(monkeypatch):
    """Redirect the handoff index (and thus the task queue) to a temp dir."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(handoff, "HANDOFF_DIR", temp_path)
        monkeypatch.setattr(
            nougen_context,
            "SESSION_DB_PATH",
            str(temp_path / "context_session.db"),
        )
        yield temp_path


def _add(owner="claude-cli", **kwargs):
    return taskqueue.add_task(
        title=kwargs.pop("title", "Test ticket"),
        instructions=kwargs.pop("instructions", "do the thing"),
        owner=owner,
        created_by="codex",
        definition_of_done=kwargs.pop("definition_of_done", "thing is done"),
        **kwargs,
    )


def test_full_lane_transition_with_receipt(setup_queue_env):
    task_id = _add()
    task = taskqueue.get_task(task_id)
    assert task["status"] == "todo"
    assert task["created_by"] == "codex"

    claimed = taskqueue.claim_task(task_id, agent="claude-cli")
    assert claimed is not None
    assert claimed["status"] == "working"
    assert claimed["claimed_by"] == "claude-cli"

    assert taskqueue.complete_task(
        task_id,
        receipt_done="did the thing",
        receipt_evidence="test output",
        agent="claude-cli",
    )
    final = taskqueue.get_task(task_id)
    assert final["status"] == "done"
    assert final["receipt_done"] == "did the thing"
    assert final["done_at"] is not None

    # Markdown ledger exists next to the handoff index
    md = setup_queue_env / "queue" / f"task_{task_id}.md"
    assert md.exists()
    text = md.read_text(encoding="utf-8")
    assert "Claimed" in text and "Receipt" in text


def test_claim_lock_single_winner(setup_queue_env):
    task_id = _add()
    first = taskqueue.claim_task(task_id, agent="claude-cli")
    second = taskqueue.claim_task(task_id, agent="gemini")
    assert first is not None
    assert second is None  # claim lock: only one agent wins
    task = taskqueue.get_task(task_id)
    assert task["claimed_by"] == "claude-cli"


def test_claim_next_respects_owner_lane(setup_queue_env):
    _add(owner="gemini", title="gemini-only ticket")
    open_lane = _add(owner=None, title="open ticket")

    # claude-cli must not claim gemini's ticket; it gets the unowned one
    claimed = taskqueue.claim_task(agent="claude-cli")
    assert claimed is not None
    assert claimed["task_id"] == open_lane

    # nothing else eligible for claude-cli
    assert taskqueue.claim_task(agent="claude-cli") is None


def test_needs_input_round_trip(setup_queue_env):
    task_id = _add()
    taskqueue.claim_task(task_id, agent="claude-cli")

    # blocking requires a question; the agent does not guess
    assert not taskqueue.block_task(task_id, "  ", agent="claude-cli")
    assert taskqueue.block_task(task_id, "Which vault: prod or clone?", agent="claude-cli")
    task = taskqueue.get_task(task_id)
    assert task["status"] == "needs_input"
    assert task["blocking_question"] == "Which vault: prod or clone?"

    # cannot complete a parked task
    assert not taskqueue.complete_task(task_id, receipt_done="nope", agent="claude-cli")

    # human answers on the ticket; task re-enters todo, claim released
    assert taskqueue.answer_task(task_id, "prod", agent="dave")
    task = taskqueue.get_task(task_id)
    assert task["status"] == "todo"
    assert task["answer"] == "prod"
    assert task["claimed_by"] is None

    # any agent in the lane resumes with the answer attached
    resumed = taskqueue.claim_task(task_id, agent="claude-cli")
    assert resumed["answer"] == "prod"


def test_receipt_is_mandatory(setup_queue_env):
    task_id = _add()
    taskqueue.claim_task(task_id, agent="claude-cli")
    assert not taskqueue.complete_task(task_id, receipt_done="", agent="claude-cli")
    assert taskqueue.get_task(task_id)["status"] == "working"


def test_cancel_only_from_open_states(setup_queue_env):
    task_id = _add()
    assert taskqueue.cancel_task(task_id, reason="superseded", agent="codex")
    assert taskqueue.get_task(task_id)["status"] == "cancelled"
    # terminal tasks stay terminal
    assert not taskqueue.cancel_task(task_id, agent="codex")


def test_smoke_test_passes(setup_queue_env):
    assert taskqueue.smoke_test(agent="claude-cli")
