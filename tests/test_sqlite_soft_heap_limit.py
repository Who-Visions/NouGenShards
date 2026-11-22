"""The process-wide SQLite soft heap limit is applied once, and tests restore it."""
import sqlite3

import pytest

from nougen_shards import core


@pytest.fixture
def fresh_limit(monkeypatch, tmp_path):
    probe = sqlite3.connect(tmp_path / "probe.db")
    before = probe.execute("PRAGMA soft_heap_limit").fetchone()[0]
    monkeypatch.setattr(core, "_SQLITE_HEAP_LIMIT_SET", False)
    yield tmp_path
    # soft_heap_limit is process-wide: put back what the process had.
    probe.execute(f"PRAGMA soft_heap_limit={before}")
    probe.close()


def test_soft_heap_limit_applied_once(fresh_limit, monkeypatch):
    monkeypatch.setenv("NOUGEN_SQLITE_SOFT_HEAP_MB", "64")
    conn = sqlite3.connect(fresh_limit / "x.db")
    core._apply_sqlite_heap_limit(conn)
    assert conn.execute("PRAGMA soft_heap_limit").fetchone()[0] == 64 * 1024 * 1024
    assert core._SQLITE_HEAP_LIMIT_SET is True
    monkeypatch.setenv("NOUGEN_SQLITE_SOFT_HEAP_MB", "32")
    core._apply_sqlite_heap_limit(conn)  # second call is a no-op
    assert conn.execute("PRAGMA soft_heap_limit").fetchone()[0] == 64 * 1024 * 1024


def test_soft_heap_limit_zero_disables(fresh_limit, monkeypatch):
    monkeypatch.setenv("NOUGEN_SQLITE_SOFT_HEAP_MB", "0")
    conn = sqlite3.connect(fresh_limit / "y.db")
    core._apply_sqlite_heap_limit(conn)
    assert conn.execute("PRAGMA soft_heap_limit").fetchone()[0] == 0
