"""The saved vector matrix is mapped, not copied into the heap, and its hash
is computed without a second full copy."""
import hashlib
import os

import numpy as np
import pytest

from nougen_shards import core


def test_chunked_hash_equals_whole_matrix_hash(monkeypatch):
    rng = np.random.default_rng(3)
    matrix = rng.random((1000, 16), dtype=np.float32)
    want = hashlib.sha256(matrix.tobytes()).hexdigest()
    for chunk in (1, 7, 1000, 4096):
        monkeypatch.setattr(core, "_MATRIX_HASH_CHUNK_ROWS", chunk)
        assert core._matrix_sha256(matrix) == want
    assert core._matrix_sha256(np.zeros((0, 16), dtype=np.float32)) == hashlib.sha256(b"").hexdigest()


def test_chunked_hash_of_a_mapped_matrix(tmp_path):
    matrix = np.arange(600, dtype=np.float32).reshape(100, 6)
    path = tmp_path / "m.npy"
    np.save(path, matrix)
    mapped = np.load(path, mmap_mode="r")
    assert isinstance(mapped, np.memmap)
    assert core._matrix_sha256(mapped) == hashlib.sha256(matrix.tobytes()).hexdigest()
    np.testing.assert_array_equal(mapped @ np.ones(6, dtype=np.float32), matrix @ np.ones(6, dtype=np.float32))


@pytest.mark.parametrize("raw,posix,nt", [
    ("", True, False), ("0", False, False), ("off", False, False), ("1", True, True),
])
def test_mmap_switch(monkeypatch, raw, posix, nt):
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR_MMAP", raw)
    monkeypatch.setattr(core.os, "name", "posix")
    assert core._vector_sidecar_mmap() is posix
    monkeypatch.setattr(core.os, "name", "nt")
    assert core._vector_sidecar_mmap() is nt


def _blocks(base_rows=6, tail_rows=3, dim=4):
    base = np.arange(base_rows * dim, dtype=np.float32).reshape(base_rows, dim)
    tail = 100 + np.arange(tail_rows * dim, dtype=np.float32).reshape(tail_rows, dim)
    return base, tail, core._RowBlocks.appended(base, tail)


def test_row_blocks_behave_like_the_joined_matrix():
    base, tail, rb = _blocks()
    whole = np.vstack([base, tail])
    q = np.array([1, 2, 3, 4], dtype=np.float32)
    assert rb.shape == whole.shape and len(rb) == 9
    np.testing.assert_array_equal(rb @ q, whole @ q)
    np.testing.assert_array_equal(np.asarray(rb), whole)
    assert rb[-1, 0] == whole[-1, 0] and rb[2, 1] == whole[2, 1]
    assert core._matrix_sha256(rb) == hashlib.sha256(whole.tobytes()).hexdigest()


def test_append_never_copies_the_base():
    base, tail, rb = _blocks()
    more = np.full((2, 4), 7, dtype=np.float32)
    grown = core._RowBlocks.appended(rb, more)
    assert grown.blocks[0] is base and len(grown.blocks) == 2
    np.testing.assert_array_equal(np.asarray(grown), np.vstack([base, tail, more]))


def test_dropping_tail_rows_keeps_the_base_block():
    base, tail, rb = _blocks()
    kept = rb.take([0, 1, 2, 3, 4, 5, 6, 8])  # drop tail row 1
    assert isinstance(kept, core._RowBlocks) and kept.blocks[0] is base
    np.testing.assert_array_equal(np.asarray(kept), np.vstack([base, tail[[0, 2]]]))
    everything = core._RowBlocks((base,)).take(list(range(6)))
    assert everything.blocks == (base,)


def test_dropping_a_base_row_returns_the_right_rows():
    base, tail, rb = _blocks()
    kept = rb[[0, 2, 3, 4, 5, 6, 7, 8]]
    np.testing.assert_array_equal(np.asarray(kept), np.vstack([base[[0, 2, 3, 4, 5]], tail]))


def test_save_maps_the_file_and_an_append_keeps_it_mapped(tmp_path, monkeypatch):
    """End to end on a real DB: build, save, append a shard, recall order."""
    import sqlite3
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR_MMAP", "1")
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR_DIR", str(tmp_path / "vc"))
    db = tmp_path / "nougen_shards_1.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT, utility_score REAL, "
                 "domain_key TEXT, event_type TEXT, embedding BLOB)")

    clock = [1_800_000_000]

    def touch():
        # The cache's staleness key is the file's whole-second mtime and size;
        # a write inside the same second would look like no write at all.
        clock[0] += 10
        os.utime(db, (clock[0], clock[0]))

    def add(sid, first):
        vec = np.zeros(8, dtype=np.float32)
        vec[0] = first
        conn.execute("INSERT INTO shards VALUES (?, '2026-01-01T00:00:00Z', 1.0, 'global', 'KNOWLEDGE', ?)",
                     (sid, vec.tobytes()))
        conn.commit()
        touch()

    for sid in (1, 2, 3):
        add(sid, float(sid))
    monkeypatch.setattr(core, "get_db_path", lambda i: db)
    monkeypatch.setattr(core, "_VECTOR_CACHE", {})
    first = core._vector_cache_entry(1, conn)
    assert isinstance(first["matrix"], np.memmap)  # a fresh build is saved, then served from the file
    add(4, 4.0)
    grown = core._vector_cache_entry(1, conn)
    assert grown["ids"] == [1, 2, 3, 4]
    assert isinstance(grown["matrix"], core._RowBlocks) and isinstance(grown["matrix"].blocks[0], np.memmap)
    q = np.zeros(8, dtype=np.float32)
    q[0] = 1
    np.testing.assert_array_equal(np.array(grown["matrix"] @ q), [1, 2, 3, 4])
    conn.execute("DELETE FROM shards WHERE id = 4")
    conn.commit()
    touch()
    pruned = core._vector_cache_entry(1, conn)
    assert pruned["ids"] == [1, 2, 3] and pruned["matrix"].shape == (3, 8)
    assert isinstance(_first_block(pruned["matrix"]), np.memmap)  # the delete did not copy the base
    conn.close()


def _first_block(matrix):
    return core._matrix_blocks(matrix)[0]
