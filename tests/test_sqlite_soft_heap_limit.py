"""The process-wide SQLite soft heap limit is applied on first connection."""
import importlib

from nougen_shards import core


def test_soft_heap_limit_applied_once(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_SQLITE_SOFT_HEAP_MB", "64")
    monkeypatch.setattr(core, "_SQLITE_HEAP_LIMIT_SET", False)
    import sqlite3
    conn = sqlite3.connect(tmp_path / "x.db")
    core._apply_sqlite_heap_limit(conn)
    assert conn.execute("PRAGMA soft_heap_limit").fetchone()[0] == 64 * 1024 * 1024
    assert core._SQLITE_HEAP_LIMIT_SET is True


def test_soft_heap_limit_zero_disables(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_SQLITE_SOFT_HEAP_MB", "0")
    monkeypatch.setattr(core, "_SQLITE_HEAP_LIMIT_SET", False)
    import sqlite3
    conn = sqlite3.connect(tmp_path / "y.db")
    core._apply_sqlite_heap_limit(conn)
    assert conn.execute("PRAGMA soft_heap_limit").fetchone()[0] == 0
