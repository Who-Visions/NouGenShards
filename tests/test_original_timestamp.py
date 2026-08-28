"""capture() must accept an original (pre-migration) timestamp.

Era re-stamp mission: migrated shards carried MIGRATION-time in the timestamp
column, so every date filter reported the grid floor as the migration month.
The fix is at the write path: capture(original_timestamp=...) stamps the shard
at its true era, so date-window queries find it where it actually happened.
Invalid values must never crash a write -- warn and fall back to now.
"""
import ast
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    tokens = shards.bind_active_vault(tmp_path, "owner")
    monkeypatch.setattr(shards, "GLOBAL_DIR", tmp_path)
    shards.init_db(1)
    yield tmp_path
    shards.reset_active_vault(tokens)


def _load_window_search():
    """Pull _window_search out of app.py without importing it (gradio at
    module scope is not a test dependency; same pattern as test_app_coverage)."""
    src = open("app.py", encoding="utf-8").read()
    tree = ast.parse(src)
    logger = logging.getLogger("test_window")
    ns = {"core": shards, "os": os, "logging": logging, "logger": logger,
          "Optional": Optional}
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_window_search")
    mod = ast.Module(body=[fn], type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod), "app.py", "exec"), ns)
    return ns["_window_search"]


def test_capture_with_original_timestamp_lands_in_its_era():
    assert shards.capture(
        "KNOWLEDGE", "era probe", "unique era probe body march 2025",
        tags=["era-test"], original_timestamp="2025-03-04T10:00:00Z")
    window = _load_window_search()
    rows = window(since="2025-03", until="2025-03", limit=10)
    assert any(r["title"] == "era probe" for r in rows), (
        "shard captured with original_timestamp must be found by a "
        "date-window query at its true era")


def _find_row(title):
    """capture() routes by content hash, so scan every mounted DB."""
    for i in range(1, shards.MAX_DB_COUNT + 1):
        if not shards.get_db_path(i).exists():
            continue
        conn = shards.get_connection(i)
        row = conn.execute(
            "SELECT timestamp FROM shards WHERE title = ?", (title,)).fetchone()
        conn.close()
        if row:
            return row
    return None


def test_invalid_original_timestamp_falls_back_to_now(caplog):
    with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
        assert shards.capture(
            "KNOWLEDGE", "bad ts probe", "unique bad timestamp probe body",
            original_timestamp="not-a-date")
    row = _find_row("bad ts probe")
    assert row is not None, "invalid original_timestamp must never lose a write"
    year_now = datetime.now(timezone.utc).year
    assert row["timestamp"].startswith(str(year_now))
    assert any("original_timestamp" in r.message for r in caplog.records)


def test_default_capture_still_stamps_now():
    assert shards.capture("KNOWLEDGE", "now probe", "unique now probe body")
    row = _find_row("now probe")
    assert row is not None
    year_now = datetime.now(timezone.utc).year
    assert row["timestamp"].startswith(str(year_now))
