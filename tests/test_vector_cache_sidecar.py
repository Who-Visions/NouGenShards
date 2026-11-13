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
    # Only the append query (id > max_id) and the bounded spot-check (id IN ...) run.
    assert all("id > ?" in sql or "id > 5" in sql or "id IN (" in sql for sql in reads), reads


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


def _sidecar(tmp):
    npy = next((tmp / "vec").glob("*.npy"))
    return npy, npy.with_suffix(".json")


def test_flipped_matrix_bytes_fail_the_checksum_and_rebuild(db, monkeypatch):
    conn, sig, tmp = db
    core._vector_cache_entry(1, conn)
    npy, _ = _sidecar(tmp)
    m = np.load(npy)
    m[0, 0] = 99.0
    np.save(npy, m)
    assert core._load_vector_sidecar(1, str(tmp / "grid.db"), conn) is None
    _restart(monkeypatch)
    assert core._vector_cache_entry(1, conn)["matrix"][0, 0] == 1.0


def test_row_backfilled_below_max_id_forces_a_rebuild(db, monkeypatch):
    conn, sig, tmp = db
    conn.execute("UPDATE shards SET embedding = NULL WHERE id = 3")
    core._vector_cache_entry(1, conn)
    conn.execute("UPDATE shards SET embedding = ? WHERE id = 3", (_vec(30),))
    sig["n"] += 1
    assert core._load_vector_sidecar(1, str(tmp / "grid.db"), conn) is None
    _restart(monkeypatch)
    got = core._vector_cache_entry(1, conn)
    assert got["ids"] == [1, 2, 3, 4, 5] and got["matrix"][2, 0] == 30.0


def test_a_held_save_lock_skips_the_save(db, monkeypatch):
    conn, sig, tmp = db
    (tmp / "vec").mkdir()
    entry = core._vector_cache_entry  # build without saving first
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR", "0")
    built = entry(1, conn)
    monkeypatch.delenv("NOUGEN_VECTOR_SIDECAR")
    npy, _ = core._vector_sidecar_paths(1, built["path"])
    lock = Path(npy + ".lock")
    lock.write_text("4242", encoding="utf-8")
    core._save_vector_sidecar(1, built)
    assert not Path(npy).exists() and lock.exists()  # the other writer's lock is untouched


def test_a_stale_lock_from_a_crash_is_taken_over(db, monkeypatch):
    conn, sig, tmp = db
    (tmp / "vec").mkdir()
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR", "0")
    built = core._vector_cache_entry(1, conn)
    monkeypatch.delenv("NOUGEN_VECTOR_SIDECAR")
    npy, _ = core._vector_sidecar_paths(1, built["path"])
    lock = Path(npy + ".lock")
    lock.write_text("4242", encoding="utf-8")
    old = __import__("time").time() - 3600
    __import__("os").utime(lock, (old, old))
    core._save_vector_sidecar(1, built)
    assert Path(npy).exists() and not lock.exists()


def _concurrent_save(args):
    import os
    src, vec_dir, grid = args
    os.environ["NOUGEN_VECTOR_SIDECAR_DIR"] = vec_dir
    sys.path.insert(0, src)
    import nougen_shards.core as c
    n = 2000
    rng = np.random.default_rng(os.getpid())
    entry = {"path": grid, "dim": 8, "n_embedded": n, "max_id": n, "ids": list(range(1, n + 1)),
             "ts": ["t"] * n, "util": np.ones(n, dtype=np.float32), "dom": [""] * n,
             "etype": [""] * n, "matrix": rng.random((n, 8), dtype=np.float32), "legacy": []}
    for _ in range(5):
        c._save_vector_sidecar(1, entry)
    return True


def test_two_processes_saving_at_once_leave_a_valid_pair(tmp_path, monkeypatch):
    import multiprocessing as mp
    src = str(Path(__file__).resolve().parents[1] / "src")
    grid = str(tmp_path / "grid.db")
    with mp.get_context("spawn").Pool(2) as pool:
        assert all(pool.map(_concurrent_save, [(src, str(tmp_path / "vec"), grid)] * 2))
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR_DIR", str(tmp_path / "vec"))
    got = core._load_vector_sidecar(1, grid)
    assert got is not None and got["matrix"].shape == (2000, 8)  # checksum matched its own metadata
    leftovers = [p.name for p in (tmp_path / "vec").iterdir() if p.suffix not in (".npy", ".json")]
    assert leftovers == []


def test_small_appends_do_not_resave_every_time(db, monkeypatch):
    conn, sig, _ = db
    saves = []
    real = core._save_vector_sidecar
    monkeypatch.setattr(core, "_save_vector_sidecar", lambda i, e: (saves.append(len(e["ids"])), real(i, e)))
    monkeypatch.setattr(core, "_VECTOR_SIDECAR_RESAVE_ROWS", 3)
    core._vector_cache_entry(1, conn)                     # full build: saved
    for sid in (6, 7):                                    # 2 appends: below the threshold
        conn.execute("INSERT INTO shards VALUES (?, 't', 1.0, 'd', 'system', ?)", (sid, _vec(sid)))
        sig["n"] += 1
        core._vector_cache_entry(1, conn)
    assert saves == [5]
    conn.execute("INSERT INTO shards VALUES (8, 't', 1.0, 'd', 'system', ?)", (_vec(8),))
    sig["n"] += 1
    core._vector_cache_entry(1, conn)                     # 3rd append reaches it
    assert saves == [5, 8]


def test_save_happens_outside_the_db_lock(db, monkeypatch):
    conn, sig, _ = db
    held = []
    real = core._save_vector_sidecar

    def spy(i, e):
        lk = core._vector_cache_lock(i)
        got = lk.acquire(blocking=False)
        held.append(not got)
        if got:
            lk.release()
        real(i, e)
    monkeypatch.setattr(core, "_save_vector_sidecar", spy)
    core._vector_cache_entry(1, conn)
    assert held == [False]


def test_emptied_db_removes_its_copy(db, monkeypatch):
    conn, sig, tmp = db
    core._vector_cache_entry(1, conn)
    assert list((tmp / "vec").glob("*.npy"))
    conn.execute("DELETE FROM shards")
    sig["n"] += 1
    _restart(monkeypatch)
    core._vector_cache_entry(1, conn)
    assert not list((tmp / "vec").glob("*.npy")) and not list((tmp / "vec").glob("*.json"))


def test_in_place_reembed_is_caught_and_rebuilt(db, monkeypatch):
    conn, sig, tmp = db
    core._vector_cache_entry(1, conn)
    conn.execute("UPDATE shards SET embedding = ?", (_vec(77),))   # provider change, same ids
    sig["n"] += 1
    assert core._load_vector_sidecar(1, str(tmp / "grid.db"), conn) is None
    _restart(monkeypatch)
    assert core._vector_cache_entry(1, conn)["matrix"][0, 0] == 77.0


def test_default_location_is_beside_the_vault(monkeypatch, tmp_path):
    monkeypatch.delenv("NOUGEN_VECTOR_SIDECAR_DIR", raising=False)
    a = core._vector_sidecar_paths(1, str(tmp_path / "tenantA" / "nougen_shards_1.db"))[0]
    b = core._vector_sidecar_paths(1, str(tmp_path / "tenantB" / "nougen_shards_1.db"))[0]
    assert Path(a).parent == tmp_path / "tenantA" / ".vector-cache"
    assert Path(b).parent == tmp_path / "tenantB" / ".vector-cache"
