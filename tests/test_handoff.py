import json
import tempfile
import pytest
from pathlib import Path
from nougen_shards import handoff

@pytest.fixture(autouse=True)
def setup_handoff_env(monkeypatch):
    """Fixture to redirect handoffs to a temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(handoff, "HANDOFF_DIR", temp_path)
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
