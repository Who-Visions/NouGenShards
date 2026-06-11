"""Tests for nougen_context.py and nougen_sandbox.py."""
# pylint: disable=protected-access
import os
import pytest
from nougen_shards import nougen_context
from nougen_shards import nougen_sandbox

@pytest.fixture(autouse=True)
def mock_db_path(tmp_path, monkeypatch):
    """Fixture to use a temporary database path for testing."""
    db_file = tmp_path / "test_session.db"
    monkeypatch.setattr(nougen_context, "SESSION_DB_PATH", str(db_file))
    # Sandbox execution is opt-in by default; enable it for these capability tests.
    monkeypatch.setenv("NOUGEN_ENABLE_SANDBOX", "1")
    return str(db_file)


def test_sandbox_disabled_by_default(monkeypatch):
    """By default the sandbox refuses to run arbitrary code (security gate)."""
    monkeypatch.delenv("NOUGEN_ENABLE_SANDBOX", raising=False)
    result = nougen_sandbox.execute_sandboxed("print('should not run')", language="python")
    assert "disabled by default" in result


def test_sandbox_trusted_bypasses_gate(monkeypatch):
    """Trusted internal callers may run even when the gate is off."""
    monkeypatch.delenv("NOUGEN_ENABLE_SANDBOX", raising=False)
    result = nougen_sandbox.execute_sandboxed(
        "print('trusted ok')", language="python", trusted=True)
    assert result == "trusted ok"

def test_init_context_db():
    """Test database initialization."""
    nougen_context.init_context_db(clean_slate=True)
    assert os.path.exists(nougen_context.SESSION_DB_PATH)

    conn = nougen_context.get_context_connection()
    cursor = conn.cursor()
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    assert "ctx_events" in tables
    assert "ctx_sandbox" in tables
    assert "ctx_session" in tables
    conn.close()

def test_log_and_search_event():
    """Test logging an event and searching for it using FTS5."""
    nougen_context.init_context_db(clean_slate=True)
    nougen_context.log_event("test_type", "Unique content for search", {"meta": "data"})

    results = nougen_context.search_context("Unique")
    assert len(results) == 1
    assert results[0]["content"] == "Unique content for search"
    assert results[0]["type"] == "test_type"

def test_sandbox_store_fetch():
    """Test sandbox storage and retrieval."""
    nougen_context.init_context_db(clean_slate=True)
    test_data = "large raw output data"
    nougen_context.store_sandbox("handle_1", test_data, "small summary")

    fetched_data = nougen_context.fetch_sandbox("handle_1")
    assert fetched_data == test_data

    # Test OR REPLACE
    new_data = "new updated data"
    nougen_context.store_sandbox("handle_1", new_data)
    assert nougen_context.fetch_sandbox("handle_1") == new_data

def test_execute_sandboxed_python():
    """Test Python execution in sandbox."""
    code = "print('hello from python')"
    result = nougen_sandbox.execute_sandboxed(code, language="python")
    assert result == "hello from python"

def test_execute_sandboxed_unsupported():
    """Test error handling for unsupported language."""
    result = nougen_sandbox.execute_sandboxed("code", language="brainfuck")
    assert "Error: Unsupported language" in result

def test_execute_sandboxed_timeout():
    """Test timeout in sandbox."""
    # This might be tricky to test reliably but let's try a sleep
    code = "import time; time.sleep(2)"
    result = nougen_sandbox.execute_sandboxed(code, language="python", timeout=1)
    assert "Error: Execution timed out" in result

def test_execute_sandboxed_javascript():
    """Test JavaScript execution if node/bun is available."""
    if nougen_sandbox._is_tool_available("node") or nougen_sandbox._is_tool_available("bun"):
        code = "console.log('hello from js')"
        result = nougen_sandbox.execute_sandboxed(code, language="javascript")
        assert result == "hello from js"
    else:
        pytest.skip("Neither Node.js nor Bun available for testing JS sandbox.")
