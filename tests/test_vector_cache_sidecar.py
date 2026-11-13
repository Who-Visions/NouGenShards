"""The vector matrix survives a restart on disk instead of being rebuilt.

whoart 2026-11-12: a cold rebuild of the ~950 MB grid took ~160 s and peaked at
~3.7 GB, so the node crossed its 6 GB memory watchdog, was restarted, and began
the same rebuild again. Every /search in between missed the 20 s recall deadline.
"""
import json
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
        conn.execute("INSERT INTO shards VALUES (?, 't', 1.0, 'd', 'system', ?)", (sid, _vec(sid)))
    sig = {"n": 0}
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR_DIR", str(tmp_path / "vec"))
    monkeypatch.delenv("NOUGEN_VECTOR_SIDECAR", raising=False)
    monkeypatch.setattr(core, "_VECTOR_CACHE", {})
    monkeypatch.setattr(core, "_VECTOR_DB_LOCKS", {})
    monkeypatch.setattr(core, "get_db_path", lambda i=None: tmp_path / "grid.db")
    monkeypatch.setattr(core, "_db_write_signature", lambda i: ("sig", sig["n"]))
    yield conn, sig, tmp_path
    conn.close()


def _restart(monkeypatch):
    monkeypatch.setattr(core, "_VECTOR_CACHE", {})


def test_restart_loads_from_disk_without_a_full_scan(db, monkeypatch):
    conn, sig, _ = db
    first = core._vector_cache_entry(1, conn)
    assert first["ids"] == [1, 2, 3, 4, 5]

    _restart(monkeypatch)
    reads = []
    conn.set_trace_callback(lambda sql: reads.append(sql) if "SELECT id," in sql and "embedding" in sql else None)
    got = core._vector_cache_entry(1, conn)
    conn.set_trace_callback(None)

    assert got["ids"] == [1, 2, 3, 4, 5]
    np.testing.assert_array_equal(got["matrix"], first["matrix"])
    # Only the append query (id > max_id) runs, and it returns nothing.
    assert all("id > ?" in sql or "id > 5" in sql for sql in reads), reads


def test_rows_written_while_down_are_appended(db, monkeypatch):
    conn, sig, _ = db
    core._vector_cache_entry(1, conn)
    _restart(monkeypatch)
    conn.execute("INSERT INTO shards VALUES (6, 't', 1.0, 'd', 'system', ?)", (_vec(6),))
    sig["n"] += 1
    got = core._vector_cache_entry(1, conn)
    assert got["ids"] == [1, 2, 3, 4, 5, 6]
    assert got["matrix"][5, 0] == 6.0


def test_rows_deleted_while_down_are_pruned(db, monkeypatch):
    conn, sig, _ = db
    core._vector_cache_entry(1, conn)
    _restart(monkeypatch)
    conn.execute("DELETE FROM shards WHERE id = 2")
    sig["n"] += 1
    got = core._vector_cache_entry(1, conn)
    assert got["ids"] == [1, 3, 4, 5]
    assert got["matrix"][1, 0] == 3.0


def test_corrupt_sidecar_falls_back_to_a_rebuild(db, monkeypatch):
    conn, sig, tmp = db
    core._vector_cache_entry(1, conn)
    for f in (tmp / "vec").glob("*.json"):
        f.write_text("{not json", encoding="utf-8")
    _restart(monkeypatch)
    got = core._vector_cache_entry(1, conn)
    assert got["ids"] == [1, 2, 3, 4, 5]


def test_sidecar_for_another_db_file_is_ignored(db, monkeypatch):
    conn, sig, tmp = db
    core._vector_cache_entry(1, conn)
    for f in (tmp / "vec").glob("*.json"):
        meta = json.loads(f.read_text(encoding="utf-8"))
        meta["path"] = "elsewhere.db"
        f.write_text(json.dumps(meta), encoding="utf-8")
    _restart(monkeypatch)
    assert core._load_vector_sidecar(1, str(tmp / "grid.db")) is None
    assert core._vector_cache_entry(1, conn)["ids"] == [1, 2, 3, 4, 5]


def test_sidecar_off_writes_nothing(db, monkeypatch):
    conn, sig, tmp = db
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR", "0")
    core._vector_cache_entry(1, conn)
    assert not (tmp / "vec").exists()


def test_scan_grows_past_a_low_capacity_guess():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE s (id INTEGER, timestamp TEXT, utility_score REAL, domain_key TEXT, event_type TEXT, embedding BLOB)")
    for sid in range(1, 11):
        conn.execute("INSERT INTO s VALUES (?, 't', NULL, NULL, NULL, ?)", (sid, _vec(sid)))
    rows = conn.execute("SELECT id, timestamp, utility_score, domain_key, event_type, embedding FROM s ORDER BY id")
    ids, ts, util, dom, etype, matrix, legacy, dim = core._scan_embedding_rows(rows, None, 2)
    assert ids == list(range(1, 11)) and matrix.shape == (10, DIM) and dim == DIM
    assert matrix[9, 0] == 10.0 and util[0] == 0.0 and legacy == []


def test_legacy_rows_survive_the_round_trip(db, monkeypatch):
    conn, sig, _ = db
    conn.execute("INSERT INTO shards VALUES (6, 't', 1.0, 'd', 'system', ?)", ("[1, 2, 3, 4]",))
    conn.execute("INSERT INTO shards VALUES (7, 't', 1.0, 'd', 'system', ?)", (b"\x00" * 8,))
    sig["n"] += 1
    first = core._vector_cache_entry(1, conn)
    assert [r[0] for r in first["legacy"]] == [6, 7]
    _restart(monkeypatch)
    got = core._vector_cache_entry(1, conn)
    assert got["legacy"] == first["legacy"]
    assert got["ids"] == [1, 2, 3, 4, 5]
