"""A delete must prune the vector cache in place, not force a full reload.

blade 2026-09-23: the e2e canary writes then deletes one shard per cycle. The
delete shrank the embedded-row count, which forced a full matrix reload of
that grid DB, so every next recall paid the cold rebuild (~38s across 9 DBs
vs ~2s warm) and the canary missed the 20s federation deadline 15% of the day.
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import nougen_shards.core as core  # noqa: E402

DIM = 4


def _vec(seed: int) -> bytes:
    return np.full(DIM, float(seed), dtype=np.float32).tobytes()


@pytest.fixture
def db(monkeypatch, tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT,
        utility_score REAL, domain_key TEXT, event_type TEXT, embedding BLOB)""")
    for sid in range(1, 6):
        conn.execute("INSERT INTO shards VALUES (?, 't', 1.0, 'd', 'system', ?)",
                     (sid, _vec(sid)))
    sig = {"n": 0}
    monkeypatch.setattr(core, "_VECTOR_CACHE", {})
    monkeypatch.setattr(core, "_VECTOR_DB_LOCKS", {})
    monkeypatch.setattr(core, "get_db_path", lambda i=None: tmp_path / "grid.db")
    monkeypatch.setattr(core, "_db_write_signature", lambda i: ("sig", sig["n"]))
    yield conn, sig
    conn.close()


def test_delete_prunes_without_reloading_blobs(db):
    conn, sig = db
    first = core._vector_cache_entry(1, conn)
    assert first["ids"] == [1, 2, 3, 4, 5]

    conn.execute("DELETE FROM shards WHERE id = 3")
    sig["n"] += 1
    blob_reads = []
    conn.set_trace_callback(
        lambda sql: blob_reads.append(sql) if "embedding" in sql and "SELECT id," in sql else None)
    got = core._vector_cache_entry(1, conn)
    conn.set_trace_callback(None)

    assert got["ids"] == [1, 2, 4, 5]
    assert got["matrix"].shape == (4, DIM)
    assert got["matrix"][2, 0] == 4.0  # rows stay aligned with ids
    assert got["n_embedded"] == 4
    # Only the append-path read (id > max_id) runs; no full blob reload.
    assert blob_reads and all("id > 5" in sql for sql in blob_reads), blob_reads


def test_delete_plus_new_write_appends_after_prune(db):
    conn, sig = db
    core._vector_cache_entry(1, conn)
    conn.execute("DELETE FROM shards WHERE id = 2")
    conn.execute("INSERT INTO shards VALUES (6, 't', 1.0, 'd', 'system', ?)", (_vec(6),))
    sig["n"] += 1
    got = core._vector_cache_entry(1, conn)
    assert got["ids"] == [1, 3, 4, 5, 6]
    assert got["matrix"].shape == (5, DIM)
    assert got["matrix"][-1, 0] == 6.0
    assert got["max_id"] == 6
