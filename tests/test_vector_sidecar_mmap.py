"""The saved vector matrix is mapped, not copied into the heap, and its hash
is computed without a second full copy."""
import hashlib

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
