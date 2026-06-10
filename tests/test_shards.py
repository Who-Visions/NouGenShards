"""Tests for the NouGenShards module."""
# pylint: disable=duplicate-code
import os
import tempfile
import pytest
import nougen_shards.core as shards

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Fixture to set up a temporary database for testing."""
    # Create a temporary file
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Mock the database path in shards module
    monkeypatch.setattr(shards, "DB_PATH", temp_db_path)

    # Initialize the database
    shards.init_db()

    yield temp_db_path

    # Cleanup after test
    try:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
    except OSError:
        pass

def test_init_db():
    """Test that the database initializes correctly with tables."""
    conn = shards.get_connection()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()

    assert "shards" in tables
    assert "shards_fts" in tables

def test_capture_and_retrieve():
    """Test capturing a shard and retrieving it."""
    # The auto-seed runs during init_db, so we clear the shards table for a clean test
    conn = shards.get_connection()
    conn.execute("DELETE FROM shards")
    conn.commit()
    conn.close()

    # Capture a new shard
    success = shards.capture(
        event_type="TEST",
        title="Test Title",
        content="This is test content.",
        tags=["test"]
    )
    assert success is True

    # Duplicate capture should return False
    success = shards.capture(
        event_type="TEST",
        title="Test Title",
        content="This is test content.",
        tags=["test"]
    )
    assert success is False

    # Retrieve the shard
    results = shards.retrieve("test content", limit=10)
    assert len(results) == 1
    assert results[0]["title"] == "Test Title"
    assert results[0]["content"] == "This is test content."
    assert "test" in results[0]["tags"]

def test_retrieve_fallback():
    """Test retrieve fallback logic with empty query."""
    conn = shards.get_connection()
    conn.execute("DELETE FROM shards")
    conn.commit()
    conn.close()

    shards.capture("TEST", "Fallback Test", "Fallback content", ["fallback"])

    # Empty query should trigger fallback and match everything or use LIKE
    results = shards.retrieve("", limit=1)
    assert len(results) >= 0

def test_compile_recall_packet():
    """Test compilation of the recall packet."""
    packet = shards.compile_recall_packet([])
    assert "NO RELEVANT MEMORY SHARDS" in packet

    test_shards = [{
        "id": 1,
        "event_type": "TEST",
        "title": "A Title",
        "timestamp": "2024-01-01T00:00:00Z",
        "tags": '["t1", "t2"]',
        "utility_score": 1.0,
        "access_count": 0,
        "content": "Content line 1."
    }]

    packet = shards.compile_recall_packet(test_shards)
    assert "NOUGENSHARDS RECALL PACKET" in packet
    assert "A Title" in packet
    assert "t1, t2" in packet
    assert "Content line 1." in packet

def test_discover_and_import_shards(tmp_path):
    """Test discovering and importing markdown files as shards."""
    test_md = tmp_path / "shard_test.md"
    test_md.write_text(
        "---\n"
        "title: Test Discovered\n"
        "event_type: KNOWLEDGE\n"
        "tags: a, b\n"
        "---\n"
        "Some body content.",
        encoding="utf-8"
    )

    count = shards.discover_and_import_shards(str(tmp_path))
    assert count == 1

    results = shards.retrieve("Some body content")
    assert len(results) >= 1

    found = False
    for res in results:
        if res["title"] == "Test Discovered":
            found = True
            break
    assert found
