"""
Tests for NouGen Metameric Vector-Graph Substrate (Native Topological Memory).
"""
import tempfile
import pytest
from pathlib import Path
import numpy as np

import nougen_shards.core as core
from nougen_shards import graph
from nougen_shards import history
from nougen_shards import vector_graph


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Isolate the shard cluster + graph store in a temporary vault directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(core, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(core, "get_db_path", mock_get_db_path)

        # Silence background history worker in tests to avoid Windows file locks on temp dir
        monkeypatch.setattr(history, "log_event", lambda *args, **kwargs: None)

        core.init_db(1)
        vector_graph.init_vector_graph_db()
        yield temp_path
        import gc
        gc.collect()


def _mock_embed(text: str):
    """Deterministic synthetic 16-dim float32 embedding based on text hash."""
    import hashlib
    h = hashlib.sha256(text.encode("utf-8")).digest()
    arr = np.array([float(b) for b in h[:16]], dtype=np.float32)
    norm = np.linalg.norm(arr)
    return (arr / norm).tolist() if norm > 0 else arr.tolist()


def test_schema_initialization():
    """Verify that shard_entities and shard_relations tables are created with proper indices."""
    st = vector_graph.stats()
    assert st["entities"] == 0
    assert st["relations"] == 0
    assert st["edges"] == 0


def test_heuristic_triplet_extraction():
    """Verify heuristic extraction detects agent actions and engineering relations."""
    title = "Apollo: fixed JWT expiry check in auth.py"
    content = "The fix touches security middleware and resolves authentication timeout."
    triplets = vector_graph.extract_triplets_heuristic(title, content)

    assert len(triplets) > 0
    preds = [t[1] for t in triplets]
    assert any(p in ("fixes", "touches") for p in preds)


def test_triplet_ingestion_and_search():
    """Verify triplets can be ingested and found via cosine vector search."""
    core.capture("FIX", "Auth bug fix", "Apollo fixed the JWT expiry check in auth.py")
    shard = core.retrieve("Auth bug fix")[0]
    shard_hash = graph._hash_for(shard["id"], shard["_db_index"])

    ok = vector_graph.ingest_triplet(
        subject="Apollo",
        predicate="fixes",
        obj="JWT expiry",
        source_shard_hash=shard_hash,
        embed_fn=_mock_embed,
    )
    assert ok is True

    st = vector_graph.stats()
    assert st["entities"] == 2  # 'Apollo' and 'JWT expiry'
    assert st["relations"] == 1

    # Search entity
    apollo_vec = np.array(_mock_embed("Apollo"), dtype=np.float32)
    entities = vector_graph.search_entities(apollo_vec, limit=5, threshold=0.9)
    assert len(entities) >= 1
    assert entities[0]["name"] == "Apollo"

    # Search relation
    rel_vec = np.array(_mock_embed("Apollo fixes JWT expiry"), dtype=np.float32)
    relations = vector_graph.search_relations(rel_vec, limit=5, threshold=0.9)
    assert len(relations) >= 1
    assert relations[0]["subject"] == "Apollo"
    assert relations[0]["predicate"] == "fixes"


def test_subgraph_expansion():
    """Verify O(1) indexed expansion connects 1-hop and 2-hop entity relations."""
    core.capture("FIX", "Patch 1", "Apollo deployed Atibon")
    s1 = core.retrieve("Patch 1")[0]
    h1 = graph._hash_for(s1["id"], s1["_db_index"])

    core.capture("CONFIG", "Config 2", "Atibon encrypts secrets")
    s2 = core.retrieve("Config 2")[0]
    h2 = graph._hash_for(s2["id"], s2["_db_index"])

    # Ingest two chained triplets: Apollo -> Atibon -> secrets
    vector_graph.ingest_triplet("Apollo", "deploys", "Atibon", source_shard_hash=h1, embed_fn=_mock_embed)
    vector_graph.ingest_triplet("Atibon", "persists", "secrets", source_shard_hash=h2, embed_fn=_mock_embed)

    apollo_id = vector_graph._generate_entity_id("Apollo")
    expanded = vector_graph.expand_subgraph([apollo_id], max_hops=2, limit=10)

    assert len(expanded) >= 2
    subjects = {r["subject"] for r in expanded}
    assert "Apollo" in subjects
    assert "Atibon" in subjects


def test_retrieve_vector_graph_end_to_end(monkeypatch):
    """Verify end-to-end vector-graph retrieval pulls and enriches underlying shards."""
    monkeypatch.setattr(vector_graph, "_get_embedding_fn", lambda: _mock_embed)

    core.capture("INCIDENT", "Auth Failure", "Apollo resolved token timeout in auth gateway")
    shard = core.retrieve("Auth Failure")[0]
    shard_hash = graph._hash_for(shard["id"], shard["_db_index"])

    vector_graph.ingest_triplet("Apollo", "fixes", "token timeout", source_shard_hash=shard_hash, embed_fn=_mock_embed)

    query_vec = _mock_embed("Apollo token fix")
    results, subgraph = vector_graph.retrieve_vector_graph(
        query="Apollo token fix",
        query_vector=query_vec,
        limit=5,
        expand_hops=1,
    )

    assert len(results) >= 1
    assert results[0]["title"] == "Auth Failure"
    assert "vector_graph_score" in results[0]
    assert "graph_evidence" in results[0]
    assert subgraph.total_relations >= 1


def test_reciprocal_rank_fusion():
    """Verify RRF merges vector-graph and FTS5 result sets properly."""
    vg_results = [
        {"file_hash": "hash_A", "title": "Shard A", "vector_graph_score": 0.9},
        {"file_hash": "hash_B", "title": "Shard B", "vector_graph_score": 0.8},
    ]
    fts_results = [
        {"file_hash": "hash_B", "title": "Shard B", "bm25_score": 12.5},
        {"file_hash": "hash_C", "title": "Shard C", "bm25_score": 10.0},
    ]

    fused = vector_graph.fuse_with_fts(vg_results, fts_results, k=60, limit=5)
    assert len(fused) == 3
    # Shard B was in BOTH result sets, so its RRF score should be highest!
    assert fused[0]["file_hash"] == "hash_B"
    assert fused[0]["rrf_fused_score"] > fused[1]["rrf_fused_score"]
