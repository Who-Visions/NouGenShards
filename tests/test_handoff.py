import json
import sqlite3
import tempfile
import pytest
from pathlib import Path
from nougen_shards import handoff, nougen_context

@pytest.fixture(autouse=True)
def setup_handoff_env(monkeypatch):
    """Fixture to redirect handoffs to a temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(handoff, "HANDOFF_DIR", temp_path)
        monkeypatch.setattr(
            nougen_context,
            "SESSION_DB_PATH",
            str(temp_path / "context_session.db"),
        )
        yield temp_path

def test_handoff_creation(setup_handoff_env):
    temp_path = setup_handoff_env
    
    # 1. Create a handoff for "gemini" agent
    json_path = handoff.create_handoff(message="Testing handoff system", agent="gemini")
    assert json_path is not None
    assert json_path.exists()
    
    # Check that the file was created under the agent subdirectory
    subdir_name = handoff.AGENT_FOLDERS["gemini"]
    assert json_path.parent == temp_path / subdir_name
    
    # Check markdown sibling file
    md_path = json_path.with_suffix(".md")
    assert md_path.exists()
    
    # Verify content of JSON
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["agent"] == "gemini"
        assert data["message"] == "Testing handoff system"
        assert "git" in data
        assert "tasks" in data

    conn = sqlite3.connect(handoff.get_handoff_db_path())
    row = conn.execute(
        "SELECT agent, status, goal FROM handoff_records WHERE handoff_id = ?",
        (data["handoff_id"],),
    ).fetchone()
    conn.close()
    assert row == ("gemini", "open", data["goal"])

def test_handoff_creation_generic(setup_handoff_env):
    temp_path = setup_handoff_env
    
    # Create handoff with no agent, falls back to detect_current_agent
    json_path = handoff.create_handoff(message="Testing default fallback", agent="generic")
    assert json_path is not None
    assert json_path.exists()

def test_list_and_read_handoffs(setup_handoff_env):
    # Create multiple handoffs
    handoff.create_handoff(message="Handoff 1", agent="gemini")
    handoff.create_handoff(message="Handoff 2", agent="claude")
    
    # List handoffs
    files = handoff.get_handoff_files()
    assert len(files) == 2
    
    # Filter by agent
    gemini_files = handoff.get_handoff_files(agent="gemini")
    assert len(gemini_files) == 1
    
    # Run UI output functions to verify no exceptions
    handoff.list_handoffs()
    handoff.show_latest_handoff()


def test_handoff_goal_passthrough(setup_handoff_env):
    json_path = handoff.create_handoff(message="x", agent="claude", goal="Ship the launcher fix")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["goal"] == "Ship the launcher fix"
    assert data["status"] == "open"
    assert data["acknowledged_by"] is None
    assert data["handoff_id"]


def test_acknowledge_flow(setup_handoff_env, monkeypatch):
    monkeypatch.setenv("NOUGEN_AGENT", "claude")
    handoff.create_handoff(message="please pick up", agent="gemini", goal="G")

    acked = handoff.acknowledge_handoff()
    assert acked is not None
    data = json.loads(acked.read_text(encoding="utf-8"))
    assert data["status"] == "acknowledged"
    assert data["acknowledged_by"] == "claude"
    assert data["acknowledged_at"] is not None

    # Nothing open left to acknowledge
    assert handoff.acknowledge_handoff() is None


def test_start_orchestration_claims_handoff(setup_handoff_env, monkeypatch):
    monkeypatch.setenv("NOUGEN_AGENT", "codex")
    created = handoff.create_handoff(message="ready", agent="gemini", goal="G")

    started = handoff.start_orchestration(message="taking over")
    assert started == created
    data = json.loads(started.read_text(encoding="utf-8"))
    assert data["status"] == "in_progress"
    assert data["acknowledged_by"] == "codex"
    assert data["orchestration"]["started_by"] == "codex"
    assert data["orchestration"]["checkpoints"][0]["state"] == "started"


def test_checkpoint_and_complete_orchestration(setup_handoff_env, monkeypatch):
    monkeypatch.setenv("NOUGEN_AGENT", "codex")
    handoff.create_handoff(message="ready", agent="gemini", goal="G")
    started = handoff.start_orchestration(message="start")
    handoff.checkpoint_orchestration(message="halfway", handoff_id=None)

    data = json.loads(started.read_text(encoding="utf-8"))
    assert data["status"] == "in_progress"
    assert data["orchestration"]["checkpoints"][-1]["message"] == "halfway"

    completed = handoff.complete_orchestration(message="done")
    assert completed == started
    data = json.loads(started.read_text(encoding="utf-8"))
    assert data["status"] == "complete"
    assert data["completed_by"] == "codex"
    assert data["orchestration"]["checkpoints"][-1]["state"] == "complete"

    conn = sqlite3.connect(handoff.get_handoff_db_path())
    status = conn.execute(
        "SELECT status FROM handoff_records WHERE handoff_id = ?",
        (data["handoff_id"],),
    ).fetchone()[0]
    checkpoint_count = conn.execute(
        "SELECT COUNT(*) FROM handoff_checkpoints WHERE handoff_id = ?",
        (data["handoff_id"],),
    ).fetchone()[0]
    conn.close()
    assert status == "complete"
    assert checkpoint_count == 3


def test_handoff_transitions_are_mirrored_to_context_mode(setup_handoff_env, monkeypatch):
    monkeypatch.setenv("NOUGEN_AGENT", "codex")
    created = handoff.create_handoff(message="ready", agent="gemini", goal="Context mirror")
    handoff.start_orchestration(message="start")
    handoff.checkpoint_orchestration(message="halfway")
    handoff.complete_orchestration(message="done")

    data = json.loads(created.read_text(encoding="utf-8"))
    events = nougen_context.search_events(data["handoff_id"], limit=10)
    event_types = {event["event_type"] for event in events}

    assert "HANDOFF_CREATED" in event_types
    assert "HANDOFF_ORCHESTRATION_STARTED" in event_types
    assert "HANDOFF_ORCHESTRATION_CHECKPOINT" in event_types
    assert "HANDOFF_ORCHESTRATION_COMPLETED" in event_types

    completed = next(
        event for event in events
        if event["event_type"] == "HANDOFF_ORCHESTRATION_COMPLETED"
    )
    metadata = json.loads(completed["metadata"])
    assert metadata["handoff_id"] == data["handoff_id"]
    assert metadata["state"] == "complete"


def test_rebuild_handoff_db_from_json(setup_handoff_env):
    path = handoff.create_handoff(message="old file", agent="gemini", goal="G")
    db_path = handoff.get_handoff_db_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{db_path}{suffix}")
        if candidate.exists():
            candidate.unlink()

    assert not db_path.exists()
    assert handoff.rebuild_handoff_db() == 1
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM handoff_records").fetchone()[0]
    stored_path = conn.execute("SELECT path FROM handoff_records").fetchone()[0]
    conn.close()
    assert count == 1
    assert stored_path == str(path)


def test_agent_env_override(setup_handoff_env, monkeypatch):
    monkeypatch.setenv("NOUGEN_AGENT", "codex")
    assert handoff.detect_current_agent() == "codex"


def test_atomic_write_produces_valid_json(setup_handoff_env):
    p = handoff.create_handoff(message="integrity", agent="ollama")
    # Must be complete, parseable JSON — no truncation, no leftover temp files
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["handoff_id"]
    leftovers = list(p.parent.glob("*.tmp"))
    assert leftovers == []


def test_escaped_newlines_are_restored():
    # Agents escape newlines to survive cmd.exe; the note must still render as sections.
    # r"" keeps these as literal backslash-n, which is what the mangled input looks like.
    mangled = r"## Active Incidents\n- None\n\n## Recent Changes\n- patched"
    restored = handoff.normalize_handoff_message(mangled)
    assert "\\n" not in restored
    assert restored.count("\n") == 4


def test_clean_multiline_note_is_left_alone():
    clean = "## Active Incidents\n- None\n\n## Recent Changes\n- total $3,922.07"
    assert handoff.normalize_handoff_message(clean) == clean


def test_multiline_message_survives_create_handoff(setup_handoff_env):
    # Regression: cmd.exe truncated templated notes to their first heading, so a
    # ~2600-char handoff landed as 19 chars. Every section must survive the writer.
    note = (
        "## Active Incidents\n- None\n\n"
        "## Ongoing Investigations\n- none\n\n"
        "## Recent Changes\n- claim total $3,922.07\n\n"
        "## Known Issues and Workarounds\n- None\n\n"
        "## Upcoming Events\n- None\n"
    )
    p = handoff.create_handoff(message=note, agent="claude-cli")
    stored = json.loads(p.read_text(encoding="utf-8"))["message"]
    assert stored.count("## ") == 5
    assert "$3,922.07" in stored
