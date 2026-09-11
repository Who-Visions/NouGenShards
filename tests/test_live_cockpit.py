import pytest
import os
import json
from pathlib import Path
from nougen_shards.live_cockpit import LiveCockpit, LiveSession

def test_live_cockpit_discovery(tmp_path):
    # Setup mock session registry
    state_dir = tmp_path / ".nougen"
    state_dir.mkdir(parents=True)
    
    cc_file = state_dir / "cc_sessions.json"
    cc_file.write_text(json.dumps([
        {
            "id": "mock-claude-session-1",
            "name": "Feature Worker",
            "machine": "phoebus",
            "pipe": str(tmp_path / "mock.sock")
        }
    ]))

    cockpit = LiveCockpit(state_dir=state_dir)
    sessions = cockpit.discover_sessions()
    
    # Should discover mock-claude and http-mesh
    assert any(s.session_id == "mock-claude-session-1" for s in sessions)
    assert any("http-mesh" in s.session_id for s in sessions)

def test_live_cockpit_render(tmp_path):
    cockpit = LiveCockpit(state_dir=tmp_path)
    rendered = cockpit.render_cockpit()
    assert "/live" in rendered
    assert "SESSION ID" in rendered

def test_live_cockpit_send_and_broadcast(tmp_path):
    cockpit = LiveCockpit(state_dir=tmp_path)
    res = cockpit.broadcast("Test live mesh broadcast")
    assert res["broadcast"] is True
    assert "targets_count" in res
