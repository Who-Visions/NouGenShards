"""
Verification script for NouGenShards HistoryEngine.
"""
from nougen_shards import capture, retrieve, mark_shard, HistoryEngine
import json
import time
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

def test_history():
    print("--- 🚀 Testing HistoryEngine ---")
    
    # 1. Capture a shard
    print("Capturing shard...")
    capture(
        event_type="RESEARCH",
        title="History Test Shard",
        content="This is a unit of experience for history tracking verification.",
        tags=["test", "history"]
    )
    
    # 2. Retrieve shards
    print("Retrieving shards...")
    results = retrieve("history tracking", limit=1)
    if not results:
        print("❌ No results found!")
        return
    
    shard_id = results[0]["id"]
    print(f"Retrieved shard ID: {shard_id}")
    
    # 3. Mark shard (Utility Change)
    print("Marking shard as worked...")
    mark_shard(shard_id, worked=True)
    
    # 4. Initialize Engine and query stats
    print("Querying HistoryEngine...")
    engine = HistoryEngine()
    
    growth = engine.get_growth_rate("24h")
    print(f"Growth Rate (24h): {growth}")
    
    stats = engine.get_utility_stats("24h")
    print(f"Utility Stats: {json.dumps(stats, indent=2)}")
    
    top = engine.get_top_shards("24h")
    print(f"Top Shards: {len(top)}")
    for s in top:
        print(f" - {s['title']} (Utility: {s['utility_score']}, Activity: {s.get('activity_in_window', 0)})")
        
    print("\n--- 📦 JSON Export ---")
    print(engine.export_stats_json("24h"))

if __name__ == "__main__":
    test_history()
