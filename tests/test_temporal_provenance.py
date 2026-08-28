"""
Tests for full temporal provenance vectors and era window queries across NouGenShards.
"""
import ast
import json
import logging
import os
import pytest
from typing import Optional

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    tokens = shards.bind_active_vault(tmp_path, "owner")
    monkeypatch.setattr(shards, "GLOBAL_DIR", tmp_path)
    shards.init_db(1)
    yield tmp_path
    shards.reset_active_vault(tokens)


def _load_window_search():
    """Extract _window_search from app.py without requiring gradio."""
    src = open("app.py", encoding="utf-8").read()
    tree = ast.parse(src)
    logger = logging.getLogger("test_window")
    ns = {"core": shards, "os": os, "logging": logging, "logger": logger,
          "Optional": Optional, "json": json}
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_window_search")
    mod = ast.Module(body=[fn], type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod), "app.py", "exec"), ns)
    return ns["_window_search"]


def _load_window_page():
    """Extract _window_page from app.py without requiring gradio."""
    src = open("app.py", encoding="utf-8").read()
    tree = ast.parse(src)
    logger = logging.getLogger("test_window")
    ns = {"core": shards, "os": os, "logging": logging, "logger": logger,
          "Optional": Optional, "json": json}
    fns = [n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name in (
               "_window_page_max", "_window_clauses", "_cursor_decode", "_window_page")]
    mod = ast.Module(body=fns, type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod), "app.py", "exec"), ns)
    return ns["_window_page"]


def _find_shard(title: str):
    for i in range(1, shards.MAX_DB_COUNT + 1):
        if not shards.get_db_path(i).exists():
            continue
        conn = shards.get_connection(i)
        row = conn.execute("SELECT * FROM shards WHERE title = ?", (title,)).fetchone()
        conn.close()
        if row:
            return shards.hydrate(dict(row))
    return None


def test_temporal_provenance_vectors_storage_and_hydration():
    """Verify all 7 distinct temporal vector fields are stored and hydrated."""
    ok = shards.capture(
        "KNOWLEDGE",
        "Historic RFC 791",
        "Internet Protocol DARPA Internet Program Protocol Specification September 1981.",
        tags=["network", "rfc"],
        event_time_original="1981-09-01T00:00:00Z",
        source_created_at="1981-09-01T00:00:00Z",
        source_modified_at="1981-09-05T12:00:00Z",
        captured_at="2026-08-28T03:00:00Z",
        ai_first_touched_at="2026-08-28T03:01:00Z",
        ai_last_touched_at="2026-08-28T03:05:00Z",
        migrated_at="2026-08-28T03:10:00Z",
        amended_at=["2026-08-28T03:15:00Z"],
    )
    assert ok is True

    # Retrieve and check hydrated fields
    item = _find_shard("Historic RFC 791")
    assert item is not None
    assert item["original_timestamp"] == "1981-09-01T00:00:00Z"
    assert item["event_time_original"] == "1981-09-01T00:00:00Z"
    
    meta = json.loads(item["temporal_meta"]) if isinstance(item["temporal_meta"], str) else item["temporal_meta"]
    assert meta["event_time_original"] == "1981-09-01T00:00:00Z"
    assert meta["source_created_at"] == "1981-09-01T00:00:00Z"
    assert meta["source_modified_at"] == "1981-09-05T12:00:00Z"
    assert meta["captured_at"] == "2026-08-28T03:00:00Z"
    assert meta["ai_first_touched_at"] == "2026-08-28T03:01:00Z"
    assert meta["ai_last_touched_at"] == "2026-08-28T03:05:00Z"
    assert meta["migrated_at"] == "2026-08-28T03:10:00Z"
    assert meta["amended_at"] == ["2026-08-28T03:15:00Z"]


def test_backward_compatibility_original_timestamp_mapping():
    """Verify original_timestamp seamlessly maps to event_time_original and vice versa."""
    ok = shards.capture(
        "KNOWLEDGE",
        "Legacy Migration Shard",
        "Content captured using legacy original_timestamp parameter.",
        original_timestamp="2024-05-15T10:30:00Z"
    )
    assert ok is True

    item = _find_shard("Legacy Migration Shard")
    assert item is not None
    assert item["original_timestamp"] == "2024-05-15T10:30:00Z"
    assert item["event_time_original"] == "2024-05-15T10:30:00Z"

    meta = json.loads(item["temporal_meta"]) if isinstance(item["temporal_meta"], str) else item["temporal_meta"]
    assert meta["event_time_original"] == "2024-05-15T10:30:00Z"


def test_window_search_retrieves_historical_shards_by_event_time_original():
    """Verify era window search retrieves historical shards based on event_time_original."""
    # Capture historical shard with recent capture time (simulating migration)
    shards.capture(
        "KNOWLEDGE",
        "1995 Netscape Milestone",
        "Netscape Navigator 1.0 release notes.",
        event_time_original="1994-12-15T00:00:00Z"
    )
    # Capture modern shard
    shards.capture(
        "KNOWLEDGE",
        "2026 Architecture Update",
        "Modern architecture notes.",
        event_time_original="2026-08-20T00:00:00Z"
    )

    _window_search = _load_window_search()

    # Search window covering 1994
    results_1994 = _window_search(query="Netscape", since="1994-01-01", until="1994-12-31")
    assert len(results_1994) == 1
    assert results_1994[0]["title"] == "1995 Netscape Milestone"

    # Search window covering 2026
    results_2026 = _window_search(query="Architecture", since="2026-08-01", until="2026-08-31")
    assert len(results_2026) == 1
    assert results_2026[0]["title"] == "2026 Architecture Update"

    # Search 1994 window should NOT return 2026 shard
    results_none = _window_search(query="Architecture", since="1994-01-01", until="1994-12-31")
    assert len(results_none) == 0


def test_window_page_keyset_pagination_with_temporal_meta():
    """Verify keyset pagination correctly uses effective_timestamp."""
    for i in range(5):
        shards.capture(
            "KNOWLEDGE",
            f"Event {i}",
            f"Content for event {i}",
            event_time_original=f"2020-0{i+1}-01T00:00:00Z"
        )

    _window_page = _load_window_page()
    page1 = _window_page(since="2020-01-01", until="2020-12-31", limit=2)
    assert page1["returned"] == 2
    assert page1["rows"][0]["title"] == "Event 4"
    assert page1["rows"][1]["title"] == "Event 3"
    assert page1["next_cursor"] is not None

    page2 = _window_page(since="2020-01-01", until="2020-12-31", limit=2, cursor=page1["next_cursor"])
    assert page2["returned"] == 2
    assert page2["rows"][0]["title"] == "Event 2"
    assert page2["rows"][1]["title"] == "Event 1"
