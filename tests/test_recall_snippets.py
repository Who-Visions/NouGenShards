"""recall_memory must inject snippets-plus-handles, not whole documents.

Held context is the fleet's dominant cost (98%+ cache re-read vs ~1.5%
output, measured 2026-08-31): every character recall returns is re-read by
the caller for the rest of its session. The contract: long bodies truncate
to NOUGEN_RECALL_SNIPPET_CHARS with a marker naming get_shard(shard_id,
db_index); get_shard returns the full body on demand.
"""
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as node_app  # noqa: E402
from nougen_shards import core  # noqa: E402


def _tool_body(tool):
    """The tool's underlying sync function, past FastMCP registration and the
    threadpool offload. Tools register as async wrappers so a blocking body
    cannot hold the event loop (app._offloaded); the body itself stays sync."""
    fn = getattr(tool, "fn", tool)
    return getattr(fn, "__wrapped__", fn)


@pytest.fixture()
def tmp_vault(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    try:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(core, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(core, "get_db_path", mock_get_db_path)
        monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
        core._INITIALIZED_DBS.clear()
        yield temp_path
    finally:
        core._INITIALIZED_DBS.clear()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_slim_shard_truncates_long_bodies(monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_SNIPPET_CHARS", raising=False)
    body = "word " * 500  # 2500 chars
    slim = node_app._slim_shard({"id": 42, "_db_index": 3, "content": body,
                                 "title": "t"})
    assert slim["content_truncated"] is True
    assert slim["content_full_chars"] == len(body)
    assert len(slim["content"]) < len(body)
    # the marker must carry the exact fetch handle
    assert "get_shard(shard_id=42, db_index=3)" in slim["content"]


def test_slim_shard_leaves_short_bodies_alone(monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_SNIPPET_CHARS", raising=False)
    slim = node_app._slim_shard({"id": 1, "_db_index": 1, "content": "short"})
    assert slim["content"] == "short"
    assert "content_truncated" not in slim


def test_snippet_budget_env_zero_disables(monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_SNIPPET_CHARS", "0")
    body = "x" * 5000
    slim = node_app._slim_shard({"id": 1, "_db_index": 1, "content": body})
    assert slim["content"] == body


def test_slim_shard_drops_bytes_fields(monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_SNIPPET_CHARS", raising=False)
    slim = node_app._slim_shard({"id": 1, "_db_index": 1, "content": "c",
                                 "embedding": b"\x00\x01"})
    assert "embedding" not in slim


def test_get_shard_returns_full_body(tmp_vault, monkeypatch):
    monkeypatch.setattr(core, "get_write_index", lambda fhash: 2)
    body = "full body " * 300
    assert core.capture("KNOWLEDGE", "snippet target", body)
    conn = core.get_connection(2)
    sid = conn.execute("SELECT id FROM shards WHERE title = ?",
                       ("snippet target",)).fetchone()[0]
    conn.close()
    fetched = _tool_body(node_app.get_shard)(sid, 2)
    assert fetched.get("content", "").startswith("full body")
    assert fetched["_db_index"] == 2


def test_get_shard_miss_reports_hint(tmp_vault):
    fetched = _tool_body(node_app.get_shard)(999999)
    assert fetched.get("found") is False
    assert "hint" in fetched
