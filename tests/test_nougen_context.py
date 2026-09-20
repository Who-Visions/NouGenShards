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


def test_search_events_filters_query():
    """search_events should only return events matching the query."""
    nougen_context.init_context_db(clean_slate=True)
    nougen_context.log_event("alpha_type", "needle context payload")
    nougen_context.log_event("beta_type", "irrelevant payload")

    results = nougen_context.search_events("needle", limit=10)

    assert len(results) == 1
    assert results[0]["event_type"] == "alpha_type"
    assert results[0]["description"] == "needle context payload"


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


def test_html_content_extractor():
    """Test zero-dependency HTML parser."""
    html = """
    <html>
      <head><title>Test Page Title</title></head>
      <body>
        <h1>Main Heading</h1>
        <p>This is a paragraph with <a href="https://example.com">a link</a>.</p>
        <script>console.log('ignore');</script>
        <h2>Sub Heading</h2>
        <ul><li>Item 1</li><li>Item 2</li></ul>
      </body>
    </html>
    """
    parser = nougen_context._HTMLContentExtractor()
    parser.feed(html)
    assert parser.title == "Test Page Title"
    assert len(parser.headings) == 2
    assert "H1: Main Heading" in parser.headings[0]
    assert "https://example.com" in parser.links
    md = parser.get_markdown()
    assert "# Main Heading" in md
    assert "Item 1" in md
    assert "ignore" not in md


def test_analyze_file_python(tmp_path):
    """Test sandboxed AST analysis of Python code."""
    nougen_context.init_context_db(clean_slate=True)
    code_file = tmp_path / "sample.py"
    code_file.write_text(
        "import os, sys\n"
        "class Pilot:\n"
        "    pass\n"
        "def fly(dest):\n"
        "    return dest\n",
        encoding="utf-8"
    )
    res = nougen_context.analyze_file(str(code_file), query="dest")
    assert res["name"] == "sample.py"
    assert "Pilot" in res["ast"]["classes"]
    assert "fly" in res["ast"]["functions"]
    assert "os" in res["ast"]["imports"]
    assert len(res["query_matches"]) > 0


def test_checkpoint_and_restore_session():
    """Test session snapshot and restore capabilities."""
    nougen_context.init_context_db(clean_slate=True)
    nougen_context.log_event("TEST_EVENT", "First important finding")
    nougen_context.log_event("TEST_EVENT", "Second important finding")

    # Save checkpoint
    saved = nougen_context.checkpoint_session("v1-alpha")
    assert saved["status"] == "checkpoint_saved"
    assert saved["events_count"] == 2

    # Check list
    cps = nougen_context.list_checkpoints()
    assert len(cps) == 1
    assert cps[0]["label"] == "v1-alpha"

    # Add a third event
    nougen_context.log_event("TEST_EVENT", "Third finding that will be wiped on restore")
    events = nougen_context.search_events("finding", limit=10)
    assert len(events) == 3

    # Restore checkpoint
    restored = nougen_context.restore_session("v1-alpha")
    assert restored["status"] == "checkpoint_restored"
    assert restored["events_restored"] == 2

    # Verify only 2 events remain
    events_after = nougen_context.search_events("finding", limit=10)
    assert len(events_after) == 2


def test_batch_execute_sandboxed():
    """Test batch execution in sandbox."""
    commands = [
        {"label": "py_step", "code": "print('result_alpha')", "language": "python"},
        {"label": "py_step2", "code": "print('result_beta')", "language": "python"}
    ]
    res = nougen_sandbox.batch_execute_sandboxed(commands, queries=["alpha", "beta"])
    assert res["total_commands"] == 2
    assert len(res["steps"]) == 2
    assert res["steps"][0]["status"] == "ok"
    assert "result_alpha" in res["query_matches"]["alpha"][0]
    assert "result_beta" in res["query_matches"]["beta"][0]


def test_query_ollama_and_synthesize(monkeypatch):
    """Test native Ollama acceleration and sandbox synthesis with mocked HTTP response."""
    nougen_context.init_context_db(clean_slate=True)
    nougen_context.store_sandbox("test_handle", "raw telemetry data about space treaty")

    class MockResponse:
        def __init__(self, data):
            self.data = data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    import json
    def mock_urlopen(req, timeout=35):
        payload = json.dumps({"response": "Executive synthesis: space treaty valid", "eval_count": 42}).encode("utf-8")
        return MockResponse(payload)

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    res = nougen_context.query_ollama("Summarize", context_handle="test_handle")
    assert res["status"] == "success"
    assert "space treaty valid" in res["response"]
    assert res["tokens_eval"] == 42

    # Test synthesize_sandbox
    synth = nougen_context.synthesize_sandbox("test_handle")
    assert synth["status"] == "synthesized"
    assert "space treaty valid" in synth["summary"]


def test_fetch_blocks_file_scheme_and_private_hosts(monkeypatch):
    from nougen_shards import nougen_context as nc
    monkeypatch.delenv("NOUGEN_CONTEXT_ALLOW_PRIVATE_HOSTS", raising=False)
    for url in ("file:///C:/Windows/win.ini", "ftp://example.com/x", "http://127.0.0.1:4444/health",
                "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/", "http://[::1]/"):
        res = nc.fetch_and_index_web(url)
        assert "error" in res and res["error"].startswith("blocked"), url


def test_redirect_to_internal_host_is_refused(monkeypatch):
    import urllib.error
    import pytest
    from nougen_shards import nougen_context as nc
    monkeypatch.delenv("NOUGEN_CONTEXT_ALLOW_PRIVATE_HOSTS", raising=False)
    handler = nc._CheckedRedirect()
    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1:4444/health")
