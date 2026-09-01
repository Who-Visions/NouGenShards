"""Snapshot mode: the node serves read-only artifacts and never writes sqlite.

Architecture decision B (2026-08-31): row-wise replication corrupted the
Space grid on every storage backend (network mounts break sqlite locking).
In snapshot mode the grid resolves to the newest complete snapshot, opens
immutable, captures forward to the writer node, and history telemetry stays
off the mount.
"""
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards import core, history, snapshot_mode  # noqa: E402


@pytest.fixture()
def snapshot_root(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    try:
        base = Path(temp_dir)
        snap = base / "snapshots" / "20260831T000000Z"
        snap.mkdir(parents=True)
        # a miniature grid db1 with one shard
        conn = sqlite3.connect(snap / "nougen_shards_1.db")
        conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT, "
                     "title TEXT, content TEXT, utility_score REAL DEFAULT 1.0)")
        conn.execute("INSERT INTO shards (timestamp, title, content) VALUES "
                     "('2026-08-31T00:00:00Z', 'snapshot shard', 'frozen body')")
        conn.commit()
        conn.close()
        (base / "snapshots" / "LATEST.json").write_text(
            json.dumps({"stamp": "20260831T000000Z",
                        "path": "snapshots/20260831T000000Z"}),
            encoding="utf-8")
        monkeypatch.setenv("NOUGEN_SNAPSHOT_DIR", str(base))
        snapshot_mode._cache.update(at=0.0, dir=None, stamp=None)
        yield base
    finally:
        snapshot_mode._cache.update(at=0.0, dir=None, stamp=None)
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("NOUGEN_SNAPSHOT_DIR", raising=False)
    snapshot_mode._cache.update(at=0.0, dir=None, stamp=None)
    assert not snapshot_mode.enabled()
    assert snapshot_mode.snapshot_dir() is None


def test_resolves_latest_and_routes_paths(snapshot_root):
    assert snapshot_mode.enabled()
    assert snapshot_mode.stamp() == "20260831T000000Z"
    assert core.get_db_path(1).parent == snapshot_root / "snapshots" / "20260831T000000Z"


def test_connection_is_immutable_readonly(snapshot_root):
    conn = core.get_connection(1)
    row = conn.execute("SELECT title FROM shards").fetchone()
    assert row["title"] == "snapshot shard"
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO shards (title, content) VALUES ('x', 'y')")
    conn.close()


def test_init_db_is_noop(snapshot_root):
    before = core.get_db_path(1).stat().st_mtime_ns
    core._INITIALIZED_DBS.clear()
    core.init_db(1)  # must not raise, must not write
    assert core.get_db_path(1).stat().st_mtime_ns == before


def test_capture_forwards_instead_of_writing(snapshot_root, monkeypatch):
    seen = {}

    def fake_forward(payload):
        seen.update(payload)
        return {"captured": True, "reason": "forwarded"}
    monkeypatch.setattr(snapshot_mode, "forward_capture", fake_forward)
    result = core.capture("KNOWLEDGE", "forwarded title", "forwarded body")
    assert result.captured is True
    assert result.reason == "forwarded"
    assert seen["title"] == "forwarded title"
    # nothing was written locally
    conn = core.get_connection(1)
    n = conn.execute("SELECT COUNT(*) FROM shards WHERE title='forwarded title'"
                     ).fetchone()[0]
    conn.close()
    assert n == 0


def test_forward_without_url_reports_error(snapshot_root, monkeypatch):
    monkeypatch.delenv("NOUGEN_CAPTURE_FORWARD_URL", raising=False)
    out = snapshot_mode.forward_capture({"title": "t", "content": "c"})
    assert out["captured"] is False
    assert "nowhere to forward" in out["error"]


def test_history_path_stays_off_the_mount(snapshot_root):
    p = history.get_history_db_path()
    assert snapshot_root not in p.parents


def test_missing_latest_dir_keeps_previous(snapshot_root):
    good = snapshot_mode.snapshot_dir()
    assert good is not None
    (snapshot_root / "snapshots" / "LATEST.json").write_text(
        json.dumps({"stamp": "NOPE", "path": "snapshots/NOPE"}),
        encoding="utf-8")
    snapshot_mode._cache["at"] = 0.0  # force refresh
    assert snapshot_mode.snapshot_dir() == good
