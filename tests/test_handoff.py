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
