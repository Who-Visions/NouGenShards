"""
Verification tests for the Dual-System Memory Architecture.
"""

import tempfile
import pytest
from pathlib import Path
import nougen_shards.core as core
import nougen_shards.dream as dream_mod


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Fixture to set up a temporary environment for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(core, "GLOBAL_DIR", temp_path)
        
        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(core, "get_db_path", mock_get_db_path)
        
        # Force all databases to route to index 1 for consistent test transactions
        monkeypatch.setattr(core, "get_routing_index", lambda fhash: 1)
        monkeypatch.setattr(core, "get_write_index", lambda fhash: 1)
        
        core.init_db(1)
        yield temp_path


def test_schema_upgrade():
    """Verify that init_db initializes the database with consolidated column and semantic_knowledge table."""
    conn = core.get_connection(1)
    try:
        # Check shards table has consolidated column
        cursor = conn.execute("PRAGMA table_info(shards)")
        cols = [row["name"] for row in cursor]
        assert "consolidated" in cols
        
        # Check semantic_knowledge table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_knowledge'")
        assert cursor.fetchone() is not None
        
        # Check semantic_knowledge table columns
        cursor = conn.execute("PRAGMA table_info(semantic_knowledge)")
        sem_cols = {row["name"]: row["type"] for row in cursor}
        assert "subject" in sem_cols
        assert "predicate" in sem_cols
        assert "confidence_score" in sem_cols
    finally:
        conn.close()


def test_fallback_rule_parser():
    """Verify that the fallback Regex-based rule parser extracts invariants correctly."""
    content = (
        "rule - SQLite: timeout must be set to 10.0 seconds to prevent WAL locks\n"
        "Rule: Next.js dev server must run on port 3000\n"
        "Some general comment that is not a rule\n"
        "GitHub: Always pull remote updates before push"
    )
    invariants = dream_mod.fallback_rule_parser(content)
    
    assert len(invariants) == 3
    assert invariants[0]["subject"] == "SQLite"
    assert invariants[0]["predicate"] == "timeout must be set to 10.0 seconds to prevent WAL locks"
    assert invariants[1]["subject"] == "Next.js dev server"
    assert invariants[1]["predicate"] == "must run on port 3000"
    assert invariants[2]["subject"] == "GitHub"
    assert invariants[2]["predicate"] == "Always pull remote updates before push"


def test_consolidation_pipeline(monkeypatch):
    """Verify that consolidation processes unconsolidated high-utility shards and upserts rules."""
    # Mock LLM extraction to return a predictable invariant
    def mock_extract(content):
        return [{"subject": "Memory", "predicate": "Requires offline REM consolidation"}]
    monkeypatch.setattr(dream_mod, "extract_semantic_invariants_via_llm", mock_extract)
    
    # 1. Capture a high-utility shard (utility_score >= 1.0 by default)
    core.capture(
        event_type="TEST",
        title="Episodic Log 1",
        content="This is an interaction about Memory which is unconsolidated."
    )
    
    # Verify shard is not consolidated initially
    conn = core.get_connection(1)
    try:
        row = conn.execute("SELECT id, consolidated, utility_score FROM shards LIMIT 1").fetchone()
        assert row is not None
        assert row["consolidated"] == 0
        assert row["utility_score"] >= 1.0
    finally:
        conn.close()
        
    # 2. Run consolidation
    res = dream_mod.consolidate_episodic_data(limit=10)
    assert res["shards_scanned"] == 1
    assert res["shards_consolidated"] == 1
    assert res["new_invariants_extracted"] == 1
    assert res["rules"][0]["subject"] == "Memory"
    
    # Verify shard is marked consolidated
    conn = core.get_connection(1)
    try:
        row = conn.execute("SELECT consolidated FROM shards LIMIT 1").fetchone()
        assert row["consolidated"] == 1
        
        # Verify rule exists in semantic_knowledge
        rule = conn.execute("SELECT subject, predicate, confidence_score FROM semantic_knowledge LIMIT 1").fetchone()
        assert rule is not None
        assert rule["subject"] == "Memory"
        assert rule["predicate"] == "Requires offline REM consolidation"
        assert rule["confidence_score"] == 1.0
    finally:
        conn.close()

    # 3. Duplicate upsert: run consolidation again on a new shard with the same extracted rule
    core.capture(
        event_type="TEST",
        title="Episodic Log 2",
        content="Duplicate rule check about Memory."
    )
    # Run consolidation again
    res2 = dream_mod.consolidate_episodic_data(limit=10)
    assert res2["shards_consolidated"] == 1
    
    # Verify confidence_score has increased on the rule
    conn = core.get_connection(1)
    try:
        rule = conn.execute("SELECT confidence_score FROM semantic_knowledge WHERE subject = 'Memory'").fetchone()
        assert rule is not None
        assert rule["confidence_score"] > 1.0  # Boosted on conflict
    finally:
        conn.close()


def test_dual_system_retrieval(monkeypatch):
    """Verify retrieve_dual_system partitions semantic and episodic rules correctly."""
    # Write a rule directly to semantic_knowledge
    conn = core.get_connection(1)
    try:
        conn.execute("""
            INSERT INTO semantic_knowledge (subject, predicate, confidence_score, domain_key, updated_at)
            VALUES ('Docker', 'Containers must use read-only root filesystems', 1.5, 'global', '2026-06-16T12:00:00Z')
        """)
        conn.commit()
    finally:
        conn.close()
        
    # Capture matching episodic shard
    core.capture(
        event_type="TEST",
        title="Docker Shard",
        content="We built a Docker setup with read-only filesystems today."
    )
    
    # Run dual system retrieve (querying for "Docker" matches the shard and rule)
    results = core.retrieve_dual_system("Docker")
    
    assert len(results["semantic_rules"]) == 1
    assert results["semantic_rules"][0]["subject"] == "Docker"
    assert results["semantic_rules"][0]["predicate"] == "Containers must use read-only root filesystems"
    
    assert len(results["episodic_shards"]) == 1
    assert "Docker" in results["episodic_shards"][0]["title"]
    
    # Compile recall packet
    packet = core.compile_recall_packet_dual(results)
    assert "=== NOUGENSHARDS DUAL-SYSTEM RECALL PACKET ===" in packet
    assert "-- SYSTEM 2: SEMANTIC INVARIANTS (GLOBAL RULES) --" in packet
    assert "[Docker] Containers must use read-only root filesystems" in packet
    assert "-- SYSTEM 1: EPISODIC STORAGE (RECENT CONTEXT) --" in packet
    assert "Title: Docker Shard" in packet
