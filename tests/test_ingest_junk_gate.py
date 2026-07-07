"""HARDENING invariant 7: the substrate is not a landfill.

Lockfiles, base64 blobs, and minified/SVG-JSON dumps were sharded as
"knowledge", polluting recall and wasting embeddings. capture() must reject
this low-signal blob class at write time while letting prose and real code
through.
"""
import base64
import os
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path",
                            lambda index: temp_path / f"test_shards_{index}.db")
        monkeypatch.setenv("NOUGEN_EMBED_MODEL", "")
        shards.init_db(1)
        yield temp_path


def _count():
    # Shards route across the DB grid by content hash, so sum every existing DB
    # rather than assuming index 1.
    total = 0
    for i in range(1, shards.MAX_DB_COUNT + 1):
        if not shards.get_db_path(i).exists():
            continue
        conn = shards.get_connection(i)
        try:
            total += conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
        finally:
            conn.close()
    return total


def test_base64_blob_is_rejected():
    blob = base64.b64encode(os.urandom(40000)).decode()  # ~53k unbroken chars
    assert shards.capture("KNOWLEDGE", "encoder.json vocab", blob) is False
    assert _count() == 0


def test_hex_blob_is_rejected():
    blob = os.urandom(30000).hex()  # 60k unbroken hex chars
    assert shards.capture("KNOWLEDGE", "weights dump", blob) is False
    assert _count() == 0


def test_ordinary_prose_passes():
    prose = ("The retrieval pipeline blends BM25 with semantic similarity and a "
             "usefulness prior. This note explains why the MMR stage matters for "
             "diversity, and how the recall packet is compiled for a small executor "
             "model. " * 6)
    assert shards.capture("KNOWLEDGE", "Recall design note", prose) is True
    assert _count() == 1


def test_normal_code_snippet_passes():
    code = (
        "def retrieve(query, limit=3):\n"
        "    results = _keyword_retrieve(query, limit)\n"
        "    vec = _vector_retrieve(embed(query), limit)\n"
        "    fused = reciprocal_rank_fusion([results, vec])\n"
        "    return mmr_diversify(fused, limit)\n"
    ) * 8
    assert shards.capture("CODE_SHARD", "retrieve()", code) is True
    assert _count() == 1
