"""Tests for the NouGenShards advanced memory substrate."""
# pylint: disable=duplicate-code, protected-access
import tempfile
import pytest
from pathlib import Path
import nougen_shards.core as shards

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Fixture to set up a temporary environment for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        
        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(shards, "get_db_path", mock_get_db_path)
        
        shards.init_db(1)
        yield temp_path

def test_init_db(setup_test_env):
    """Test database initialization with trigram FTS5."""
    db_path = setup_test_env / "test_shards_1.db"
    assert db_path.exists()
    
    conn = shards.get_connection(1)
    # Check for FTS5 table
    res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shards_fts'").fetchone()
    assert res is not None
    conn.close()

def test_capture_and_retrieve_bayesian(setup_test_env):
    """Test capturing and retrieving with weighted relevance scoring."""
    # Add a high-utility shard
    shards.capture("KNOWLEDGE", "Important Tool", "This tool works perfectly for automation.")
    
    # Force a result by using the exact term
    res = shards.retrieve("automation")
    assert len(res) >= 1
    
    shard_id = res[0]["id"]
    shards.mark_shard(shard_id, worked=True) # Increase usefulness prior
    
    # Add a new shard with same keyword but neutral utility
    shards.capture("KNOWLEDGE", "New Tool", "This is another tool for automation.")
    
    results = shards.retrieve("automation")
    assert len(results) >= 2
    # The first one should be ranked higher due to higher utility prior
    assert results[0]["title"] == "Important Tool"
    assert "final_score" in results[0]

def test_trigram_n_gram_recall(setup_test_env):
    """Test trigram tokenizer for fuzzy/substring recall."""
    shards.capture("TECH", "Substrate", "The underlying infrastructure is a substrate.")
    
    # Search for a substring 'substrate' or longer part
    results = shards.retrieve("substrate")
    assert len(results) >= 1
    assert "Substrate" in results[0]["title"]

def test_vector_similarity_substrate(setup_test_env):
    """Test that embedding storage and cosine similarity integration works."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.9, 0.1, 0.0]
    v3 = [0.0, 1.0, 0.0]
    
    shards.capture("VEC", "Vector A", "Content A", embedding=v1)
    shards.capture("VEC", "Vector B", "Content B", embedding=v2)
    shards.capture("VEC", "Vector C", "Content C", embedding=v3)
    
    # Search with embedding close to A and B
    results = shards.retrieve("Content", query_embedding=[1.0, 0.1, 0.0])
    assert len(results) >= 2
    titles = [r["title"] for r in results]
    assert "Vector A" in titles
    assert "Vector B" in titles

def test_multi_db_deterministic_routing(setup_test_env):
    """Test that shards are routed deterministically based on hash."""
    content1 = "Unique experience Alpha"
    content2 = "Unique experience Beta"
    
    shards.capture("ROUTE", "Alpha", content1)
    shards.capture("ROUTE", "Beta", content2)
    
    res1 = shards.retrieve("Alpha")[0]
    res2 = shards.retrieve("Beta")[0]
    
    assert "_db_index" in res1
    assert "_db_index" in res2

def test_mark_shard_outcome_loop(setup_test_env):
    """Test the utility score update (the usefulness prior)."""
    shards.capture("TEST", "Status", "Success scenario")
    res = shards.retrieve("scenario")[0]
    initial_prior = res["utility_score"]
    
    shards.mark_shard(res["id"], worked=True)
    
    res_updated = shards.retrieve("scenario")[0]
    assert res_updated["utility_score"] > initial_prior

def test_fts_triggers_sync_on_update_and_delete(setup_test_env):
    """Edited/deleted shards must not linger in the FTS index.

    Regression for the missing AFTER UPDATE / AFTER DELETE triggers: with only
    the insert trigger, an edited or removed shard left a stale row in
    shards_fts that kept matching searches. We assert directly against the FTS
    index so the test detects retraction, not just join masking.
    """
    def fts_count(conn, term):
        # Query the FTS index exactly the way production builds its MATCH expr.
        return conn.execute(
            "SELECT count(*) FROM shards_fts WHERE shards_fts MATCH ?",
            (shards._build_fts_match_query(term),),
        ).fetchone()[0]

    shards.capture("KNOWLEDGE", "Trigger Probe", "contains zubzubzub marker token")
    res = shards.retrieve("zubzubzub")
    assert len(res) == 1
    sid = res[0]["id"]
    db = res[0]["_db_index"]  # capture hash-routes across the 9-db grid

    conn = shards.get_connection(db)
    try:
        assert fts_count(conn, "zubzubzub") == 1

        # UPDATE: the AFTER UPDATE trigger must retract the old token and index the new.
        conn.execute(
            "UPDATE shards SET content = ? WHERE id = ?",
            ("now contains wexwexwex marker instead", sid),
        )
        conn.commit()
        assert fts_count(conn, "zubzubzub") == 0
        assert fts_count(conn, "wexwexwex") == 1

        # DELETE: the AFTER DELETE trigger must retract the row entirely.
        conn.execute("DELETE FROM shards WHERE id = ?", (sid,))
        conn.commit()
        assert fts_count(conn, "wexwexwex") == 0
    finally:
        conn.close()

    assert shards.retrieve("wexwexwex") == []


def test_domain_isolation_capture_and_retrieve(setup_test_env):
    """Test that shards captured in different domains are isolated from retrieval."""
    shards.capture("TEST", "Python Code", "Writing python logic for NouGen.", domain_key="Watchtower/NouGen")
    shards.capture("TEST", "Flutter Code", "Writing dart code for Mobile.", domain_key="Mobile/Trader")

    # Retrieve from Watchtower/NouGen domain
    res_domain_a = shards.retrieve("code", domain_key="Watchtower/NouGen")
    assert len(res_domain_a) == 1
    assert res_domain_a[0]["title"] == "Python Code"

    # Retrieve from Mobile/Trader domain
    res_domain_b = shards.retrieve("code", domain_key="Mobile/Trader")
    assert len(res_domain_b) == 1
    assert res_domain_b[0]["title"] == "Flutter Code"


def test_domain_global_fallback(setup_test_env):
    """Test fallback to global domain if no domain-specific matches exist."""
    shards.capture("TEST", "Global Document", "This content lives globally.", domain_key="global")

    # Retrieve targeting an empty domain - should fall back to global
    res = shards.retrieve("globally", domain_key="NonExistentDomain")
    assert len(res) >= 1
    assert res[0]["title"] == "Global Document"


def test_vector_normalization(setup_test_env):
    """Test that embeddings are normalized at write time and retrieve works correctly."""
    import numpy as np
    import json
    unnormalized = [3.0, 4.0, 0.0]  # magnitude is 5.0
    shards.capture("VEC", "Vector Norm", "Content Norm", embedding=unnormalized)
    
    # Retrieve it
    res = shards.retrieve("Content Norm")[0]
    db_index = res["_db_index"]
    shard_id = res["id"]
    
    # Check stored embedding directly from database
    conn = shards.get_connection(db_index)
    try:
        row = conn.execute("SELECT embedding FROM shards WHERE id = ?", (shard_id,)).fetchone()
        raw_emb = row["embedding"]
        if raw_emb.startswith(b'['):
            emb_list = json.loads(raw_emb.decode())
        else:
            emb_list = np.frombuffer(raw_emb, dtype=np.float32).tolist()
        # The stored embedding should be [0.6, 0.8, 0.0]
        assert len(emb_list) == 3
        assert abs(emb_list[0] - 0.6) < 1e-6
        assert abs(emb_list[1] - 0.8) < 1e-6
        assert abs(emb_list[2] - 0.0) < 1e-6
        
        # Verify L2 norm is 1.0
        norm = np.linalg.norm(emb_list)
        assert abs(norm - 1.0) < 1e-6
    finally:
        conn.close()


def test_vector_retrieve_independent_of_fts(setup_test_env):
    """Test that _vector_retrieve retrieves matches strictly on embedding cosine similarity."""
    # Shard 1: semantic match for query embedding, no keyword overlap
    shards.capture("TEST", "Apple", "Red sweet fruit.", embedding=[1.0, 0.0, 0.0], domain_key="global")
    # Shard 2: no semantic match, no keyword overlap
    shards.capture("TEST", "Orange", "Citrus orange fruit.", embedding=[0.0, 1.0, 0.0], domain_key="global")
    
    # Query for something unrelated but pass embedding close to Apple
    res = shards._vector_retrieve(query_embedding=[0.9, 0.1, 0.0], limit=5, domain_key="global")
    assert len(res) >= 1
    assert res[0]["title"] == "Apple"


def test_reciprocal_rank_fusion(setup_test_env):
    """Test the reciprocal_rank_fusion helper."""
    list1 = [
        {"id": 1, "_db_index": 1, "title": "Doc A", "final_score": 0.9},
        {"id": 2, "_db_index": 1, "title": "Doc B", "final_score": 0.8},
    ]
    list2 = [
        {"id": 2, "_db_index": 1, "title": "Doc B", "final_score": 0.95},
        {"id": 3, "_db_index": 1, "title": "Doc C", "final_score": 0.7},
    ]
    
    merged = shards.reciprocal_rank_fusion([list1, list2], k=60)
    
    # Doc B is ranked 2nd in list1 (rank 2) and 1st in list2 (rank 1)
    # Score for B: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.016129 + 0.016393 = 0.032522
    # Doc A is ranked 1st in list1 (rank 1), not in list2. Score: 1/61 = 0.016393
    # Doc C is ranked 2nd in list2 (rank 2), not in list1. Score: 1/62 = 0.016129
    # So ranking should be B, A, C
    assert len(merged) == 3
    assert merged[0]["title"] == "Doc B"
    assert merged[1]["title"] == "Doc A"
    assert merged[2]["title"] == "Doc C"
    
    # Check that scores are set as final_score
    assert abs(merged[0]["final_score"] - (1.0/62 + 1.0/61)) < 1e-6


def test_retrieve_parallel_rrf_boost(setup_test_env):
    """Test that parallel retrieve boosts documents present in both lanes."""
    # Shard matching keyword only
    shards.capture("TEST", "Banana", "Yellow tropical fruit.", embedding=[0.0, 1.0, 0.0], domain_key="global")
    # Shard matching both keyword and embedding
    shards.capture("TEST", "Pineapple", "Tropical sweet fruit.", embedding=[1.0, 0.0, 0.0], domain_key="global")
    
    # Retrieve with query "Tropical" and query_embedding close to Pineapple
    results = shards.retrieve("Tropical", query_embedding=[0.95, 0.05, 0.0])
    
    # Pineapple should be ranked higher than Banana because Pineapple matches FTS and matches embedding,
    # whereas Banana only matches FTS/LIKE or has a lower semantic score.
    assert len(results) >= 2
    assert results[0]["title"] == "Pineapple"


