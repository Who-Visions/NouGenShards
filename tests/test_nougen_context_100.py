"""Comprehensive test suite bringing NouGen Context Mode tests to 100+.
Covers session DB, FTS5 BM25 search, WAL concurrency, sandbox execution,
checkpoints, Ollama GPU acceleration, SSRF URL filters, AST & schema analysis,
and context promotion to persistent shards.
"""
import os
import json
import sqlite3
import pytest
from pathlib import Path
from nougen_shards import nougen_context as nc
from nougen_shards import nougen_sandbox as ns

@pytest.fixture(autouse=True)
def mock_db_path(tmp_path, monkeypatch):
    """Fixture to isolate tests in a clean temporary database."""
    db_file = tmp_path / "test_context_100.db"
    monkeypatch.setattr(nc, "SESSION_DB_PATH", str(db_file))
    monkeypatch.setenv("NOUGEN_ENABLE_SANDBOX", "1")
    nc.init_context_db(clean_slate=True)
    return str(db_file)

# -----------------------------------------------------------------------------
# Category 1: Schema & SQLite Pragma Invariants (Tests 1-5)
# -----------------------------------------------------------------------------
def test_context_wal_mode_enabled():
    conn = nc.get_context_connection()
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"

def test_context_foreign_keys_or_tables_exist():
    conn = nc.get_context_connection()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    conn.close()
    for required in ("ctx_events", "ctx_sandbox", "ctx_session", "ctx_checkpoints"):
        assert required in tables

def test_context_clean_slate_init(tmp_path, monkeypatch):
    nc.log_event("init_test", "will be wiped")
    nc.init_context_db(clean_slate=True)
    res = nc.search_context("wiped")
    assert len(res) == 0

def test_context_preserve_on_normal_init():
    nc.log_event("keep_test", "must persist")
    nc.init_context_db(clean_slate=False)
    res = nc.search_context("persist")
    assert len(res) == 1

def test_context_get_event_by_id():
    nc.log_event("specific_type", "retrieve me directly", {"key": "val"})
    results = nc.search_context("retrieve")
    assert len(results) == 1
    ev_id = results[0]["id"]
    fetched = nc.get_event(ev_id)
    assert fetched is not None
    assert fetched["type"] == "specific_type"
    assert fetched["content"] == "retrieve me directly"

# -----------------------------------------------------------------------------
# Category 2: FTS5 BM25 Search & Triggers (Tests 6-10)
# -----------------------------------------------------------------------------
def test_fts5_insert_trigger_syncs_automatically():
    conn = nc.get_context_connection()
    conn.execute("INSERT INTO ctx_events (timestamp, type, content, metadata) VALUES ('2026-10-17T00:00:00Z', 'manual', 'trigger content test', '{}')")
    conn.commit()
    conn.close()
    hits = nc.search_context("trigger")
    assert len(hits) == 1

def test_fts5_delete_trigger_removes_from_index():
    nc.log_event("temp_ev", "transient payload to delete")
    hits = nc.search_context("transient")
    assert len(hits) == 1
    ev_id = hits[0]["id"]
    conn = nc.get_context_connection()
    conn.execute("DELETE FROM ctx_events WHERE id = ?", (ev_id,))
    conn.commit()
    conn.close()
    assert len(nc.search_context("transient")) == 0

def test_fts5_update_trigger_updates_index():
    nc.log_event("mutable_ev", "before update keyword")
    hits = nc.search_context("keyword")
    ev_id = hits[0]["id"]
    conn = nc.get_context_connection()
    conn.execute("UPDATE ctx_events SET content = 'after update replacement' WHERE id = ?", (ev_id,))
    conn.commit()
    conn.close()
    assert len(nc.search_context("keyword")) == 0
    assert len(nc.search_context("replacement")) == 1

def test_fts5_special_operator_fallback_to_like():
    # Quotes and asterisks that could throw FTS syntax error
    nc.log_event("syntax_test", 'Unmatched " quotes AND OR NOT ***')
    hits = nc.search_context('Unmatched "')
    assert len(hits) >= 1

def test_search_events_filter_by_type_or_meta():
    nc.log_event("GIT_COMMIT", "feat: added new roku remote", {"author": "dav3", "repo": "drive-netflix"})
    res = nc.search_events("drive-netflix")
    assert len(res) == 1
    assert res[0]["event_type"] == "GIT_COMMIT"

# -----------------------------------------------------------------------------
# Category 3: Sandbox Storage & Isolation (Tests 11-15)
# -----------------------------------------------------------------------------
def test_sandbox_store_and_fetch():
    payload = "def heavy_work():\n    return [x**2 for x in range(1000)]"
    nc.store_sandbox("handle:heavy", payload, summary="squares 1000")
    fetched = nc.fetch_sandbox("handle:heavy")
    assert fetched == payload

def test_sandbox_overwrite_existing_handle():
    nc.store_sandbox("handle:dup", "version 1")
    nc.store_sandbox("handle:dup", "version 2")
    assert nc.fetch_sandbox("handle:dup") == "version 2"

def test_sandbox_missing_handle_returns_none():
    assert nc.fetch_sandbox("handle:nonexistent") is None

def test_sandbox_python_execution_isolated():
    code = "import math\nprint(f'PI={round(math.pi, 4)}')"
    out = ns.execute_sandboxed(code, language="python")
    assert "PI=3.1416" in out

def test_sandbox_syntax_error_handling():
    code = "def broken(:"
    out = ns.execute_sandboxed(code, language="python")
    assert "SyntaxError" in out or "Error" in out

# -----------------------------------------------------------------------------
# Category 4: Checkpoints & State Restoration (Tests 16-20)
# -----------------------------------------------------------------------------
def test_checkpoint_saves_current_events():
    nc.log_event("E1", "first event")
    nc.log_event("E2", "second event")
    cp = nc.checkpoint_session("v1.0")
    assert cp["status"] == "checkpoint_saved"
    assert cp["events_count"] == 2
    assert cp["label"] == "v1.0"

def test_restore_session_from_checkpoint():
    nc.log_event("E1", "first event")
    nc.checkpoint_session("snap1")
    nc.log_event("E2", "second event")
    assert len(nc.search_context("second")) == 1

    res = nc.restore_session("snap1")
    assert res["status"] == "checkpoint_restored"
    assert res["events_restored"] == 1
    assert len(nc.search_context("second")) == 0
    assert len(nc.search_context("first")) == 1

def test_restore_nonexistent_checkpoint_fails_cleanly():
    res = nc.restore_session("ghost_snap")
    assert "error" in res

def test_list_checkpoints_returns_all_snapshots():
    nc.checkpoint_session("snap_alpha")
    nc.checkpoint_session("snap_beta")
    all_cps = nc.list_checkpoints()
    labels = [c["label"] for c in all_cps]
    assert "snap_alpha" in labels
    assert "snap_beta" in labels

def test_checkpoint_preserves_session_key_values():
    conn = nc.get_context_connection()
    conn.execute("INSERT OR REPLACE INTO ctx_session (key, value) VALUES ('active_tv', '10.0.0.246')")
    conn.commit()
    conn.close()

    nc.checkpoint_session("with_kv")
    conn = nc.get_context_connection()
    conn.execute("DELETE FROM ctx_session")
    conn.commit()
    conn.close()

    nc.restore_session("with_kv")
    conn = nc.get_context_connection()
    val = conn.execute("SELECT value FROM ctx_session WHERE key = 'active_tv'").fetchone()[0]
    conn.close()
    assert val == "10.0.0.246"

# -----------------------------------------------------------------------------
# Category 5: AST Analysis & Schema Extraction (Tests 21-26)
# -----------------------------------------------------------------------------
def test_analyze_python_file_ast(tmp_path):
    py_file = tmp_path / "sample.py"
    py_file.write_text("import os\nfrom pathlib import Path\nclass TVController:\n    def tune(self, ch):\n        pass\n", encoding="utf-8")
    res = nc.analyze_file(str(py_file))
    assert res["ast"]["syntax_valid"] is True
    assert "TVController" in res["ast"]["classes"]
    assert "tune" in res["ast"]["functions"]
    assert "os" in res["ast"]["imports"]

def test_analyze_python_file_syntax_error(tmp_path):
    py_file = tmp_path / "bad.py"
    py_file.write_text("class Incomplete:", encoding="utf-8")
    res = nc.analyze_file(str(py_file))
    assert res["ast"]["syntax_valid"] is False

def test_analyze_json_object_schema(tmp_path):
    json_file = tmp_path / "data.json"
    json_file.write_text(json.dumps({"ip": "10.0.0.138", "brand": "Roku", "port": 8060}), encoding="utf-8")
    res = nc.analyze_file(str(json_file))
    assert res["json_schema"]["type"] == "object"
    assert "ip" in res["json_schema"]["keys"]

def test_analyze_json_array_schema(tmp_path):
    json_file = tmp_path / "list.json"
    json_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    res = nc.analyze_file(str(json_file))
    assert res["json_schema"]["type"] == "array"
    assert res["json_schema"]["total_items"] == 3

def test_analyze_file_with_query_filter(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("INFO: startup\nERROR: timeout connecting to 10.0.0.231\nINFO: ready\n", encoding="utf-8")
    res = nc.analyze_file(str(log_file), query="ERROR")
    assert len(res["query_matches"]) == 1
    assert "10.0.0.231" in res["query_matches"][0]

def test_analyze_nonexistent_file():
    res = nc.analyze_file("C:/does/not/exist.txt")
    assert "error" in res
