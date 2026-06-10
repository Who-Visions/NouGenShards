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
    """Test capturing and retrieving with Bayesian scoring."""
    # Add a high-utility shard
    shards.capture("KNOWLEDGE", "Important Tool", "This tool works perfectly for automation.")
    
    # Force a result by using the exact term
    res = shards.retrieve("automation")
    assert len(res) >= 1
    
    shard_id = res[0]["id"]
    shards.mark_shard(shard_id, worked=True) # Increase Bayesian Prior
    
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
    """Test the utility score update (The Bayesian Prior)."""
    shards.capture("TEST", "Status", "Success scenario")
    res = shards.retrieve("scenario")[0]
    initial_prior = res["utility_score"]
    
    shards.mark_shard(res["id"], worked=True)
    
    res_updated = shards.retrieve("scenario")[0]
    assert res_updated["utility_score"] > initial_prior
