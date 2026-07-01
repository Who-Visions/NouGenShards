"""Tests for the unified vector index (ann_index): ranking + fallback contract."""
import json
import numpy as np
import pytest

from nougen_shards import ann_index


def _write_index(vault, vectors, labels):
    """Persist a matrix + labels sidecar exactly as build() would."""
    mat_path, lbl_path = ann_index._paths(str(vault))
    np.save(mat_path, np.asarray(vectors, dtype=np.float32))
    with open(lbl_path, "w", encoding="utf-8") as fh:
        json.dump({"dim": len(vectors[0]), "count": len(vectors), "labels": labels}, fh)
    ann_index._CACHE.pop(str(vault), None)  # force reload


def test_query_returns_nearest_label_first(tmp_path):
    # three orthogonal-ish unit vectors -> a query near #2 must rank (2,20) first
    vecs = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    labels = [[1, 10], [2, 20], [3, 30]]
    _write_index(tmp_path, vecs, labels)

    res = ann_index.query([0.1, 0.95, 0.0], top_n=3, vault=str(tmp_path))
    assert res is not None
    assert res[0] == (2, 20)          # nearest first
    assert set(res) == {(1, 10), (2, 20), (3, 30)}


def test_missing_index_returns_none(tmp_path):
    # no matrix/labels on disk -> signal caller to fall back to linear scan
    ann_index._CACHE.pop(str(tmp_path), None)
    assert ann_index.query([0.1, 0.2, 0.3], top_n=5, vault=str(tmp_path)) is None


def test_dim_mismatch_returns_none(tmp_path):
    _write_index(tmp_path, [[1.0, 0.0, 0.0]], [[1, 10]])
    # query of wrong dimensionality must not crash; returns None -> fallback
    assert ann_index.query([1.0, 0.0], top_n=1, vault=str(tmp_path)) is None
