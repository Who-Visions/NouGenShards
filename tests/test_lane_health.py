"""HARDENING invariant 4: recall responses carry lane health.

A dead semantic index once returned "no relevant shards" while 27k shards sat
unembedded — a broken sensor reporting absence as fact. Empty recall must now
surface embedding coverage so callers don't assert absence from a degraded lane.
"""
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
        monkeypatch.setenv("NOUGEN_EMBED_MODEL", "")  # hermetic: no live embed
        shards.init_db(1)
        yield temp_path


def test_lane_health_reports_coverage():
    # No embed model reachable, so every capture lands keyword-only (0% embedded).
    for i in range(3):
        shards.capture("KNOWLEDGE", f"note {i}", f"unique body number {i} about pipelines")
    h = shards.lane_health()
    assert h["ok"] is True
    assert h["total_shards"] == 3
    assert h["embedding_coverage_pct"] == 0.0


def test_empty_recall_carries_lane_health():
    shards.capture("KNOWLEDGE", "seed", "some indexed content about retrieval")
    # Query that matches nothing -> empty packet, but it must not be a bare marker.
    packet = shards.compile_recall_packet([])
    assert "NO RELEVANT MEMORY" in packet
    assert "shards" in packet  # coverage annotation present
    # With 0% embedding coverage the notice must warn the lane is degraded.
    assert "DEGRADED SEMANTIC LANE" in packet


def test_populated_recall_unaffected():
    packet = shards.compile_recall_packet([
        {"id": 1, "_db_index": 1, "final_score": 0.9, "timestamp": None,
         "title": "t", "content": "hello vault"}])
    assert "hello vault" in packet
    assert "NO RELEVANT MEMORY" not in packet
