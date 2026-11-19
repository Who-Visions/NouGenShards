"""Regression tests for the lane-health sensor (HARDENING §4, atlas 201/511).

HARDENING §4 claimed ``core.lane_health()`` existed; it did not. The P0
Native Memory Engine lane implements it as an additive, read-only sensor:
it reports per-lane health so recall can distinguish "no match" from
"degraded lane", and it must never change recall results or the recall path.

Linux note: the sensor opens each DB read-only (``mode=ro`` URI) so it never
creates ``-wal``/``-shm`` files or takes a write lock, and it uses
``PRAGMA quick_check`` (not the full ``integrity_check``) so a health probe
stays cheap on a multi-GB grid.
"""
# pylint: disable=protected-access
import os
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def vault(monkeypatch):
    """Temporary vault so the real grid is never touched."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(
            shards, "get_db_path",
            lambda index: temp_path / f"test_shards_{index}.db")
        monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
        from nougen_shards import embed_providers
        monkeypatch.setattr(
            embed_providers, "provider_status",
            lambda: {"provider": "stub", "model": "stub", "ollama_reachable": True})
        shards._INITIALIZED_DBS.clear()
        shards.init_db(1)
        yield temp_path


def _capture(title, content, embedding=None):
    result = shards.capture("test", title, content, embedding=embedding)
    assert result["captured"] is True, result
    return result


def test_empty_vault_is_healthy_with_no_coverage():
    """An empty grid has nothing degraded; coverage is undefined, not zero."""
    health = shards.lane_health()
    assert health["healthy"] is True
    assert health["degraded_lanes"] == []
    assert health["total_shards"] == 0
    assert health["embedding_coverage_pct"] is None
    assert health["semantic_degraded"] is False
    assert health["fts"]["present_all"] is True
    assert health["databases"]["db1"]["exists"] is True
    assert health["databases"]["db1"]["readable"] is True
    assert health["databases"]["db2"]["exists"] is False


def test_full_embedding_coverage_is_healthy():
    """Shards stored with vectors: coverage 100%, semantic lane healthy."""
    vec = [0.1] * 8
    for i in range(3):
        _capture(f"health test shard {i} alpha", f"body text here number {i}", embedding=vec)
    health = shards.lane_health()
    assert health["total_shards"] == 3
    assert health["embedded_shards"] == 3
    assert health["embedding_coverage_pct"] == 100.0
    assert health["semantic_degraded"] is False
    assert health["healthy"] is True
    assert health["fts"]["rows"] == 3


def test_zero_coverage_flags_semantic_lane_degraded():
    """Embed-at-capture off + no vectors: coverage 0% < 50% threshold."""
    for i in range(2):
        _capture(f"no vector shard {i} beta", f"plain body text number {i}")
    health = shards.lane_health()
    assert health["total_shards"] == 2
    assert health["embedded_shards"] == 0
    assert health["embedding_coverage_pct"] == 0.0
    assert health["semantic_degraded"] is True
    assert "embedding" in health["degraded_lanes"]
    assert health["healthy"] is False


def test_min_coverage_threshold_is_env_tunable():
    """NOUGEN_MIN_COVERAGE_PCT moves the degraded verdict (Rule 0.2)."""
    _capture("one vector shard gamma", "vector body one", embedding=[0.1] * 8)
    _capture("one bare shard gamma", "bare body two")
    assert shards.lane_health()["embedding_coverage_pct"] == 50.0
    assert shards.lane_health()["semantic_degraded"] is False
    os.environ["NOUGEN_MIN_COVERAGE_PCT"] = "90"
    try:
        assert shards.lane_health()["semantic_degraded"] is True
    finally:
        del os.environ["NOUGEN_MIN_COVERAGE_PCT"]


def test_corrupt_db_is_degraded_not_fatal(vault):
    """A corrupt DB reports degraded; the sensor still answers for the rest."""
    _capture("good shard delta", "body", embedding=[0.1] * 8)
    db2 = vault / "test_shards_2.db"
    db2.write_bytes(b"not a sqlite database at all" * 100)
    health = shards.lane_health()
    assert health["healthy"] is False
    assert "db2" in health["degraded_lanes"]
    assert health["databases"]["db2"]["readable"] is False
    assert health["databases"]["db1"]["readable"] is True
    assert health["total_shards"] == 1


def test_lane_health_never_raises_on_missing_vault(monkeypatch):
    """Even a vault dir that cannot be read returns a degraded dict."""
    monkeypatch.setattr(shards, "get_db_path", lambda index: (_ for _ in ()).throw(
        OSError("permission denied")))
    health = shards.lane_health()
    assert health["healthy"] is False
    assert len(health["degraded_lanes"]) == 9


def test_lane_health_does_not_change_recall():
    """Sensor first, recall after: identical results with/without the probe."""
    _capture("relay leg routing epsilon", "relay legs route work",
             embedding=[0.1] * 8)
    _capture("unrelated cooking zeta", "recipes and spices",
             embedding=[0.2] * 8)
    before = shards.retrieve("relay leg routing", limit=2)
    shards.lane_health()
    after = shards.retrieve("relay leg routing", limit=2)
    assert [r["title"] for r in before] == [r["title"] for r in after]
    assert before[0]["title"] == "relay leg routing epsilon"


def test_lane_health_reports_durability_contract():
    """journal_mode / synchronous are read back from a live connection."""
    health = shards.lane_health()
    assert health["journal_mode"] == "WAL"
    assert health["synchronous"] == "FULL"
    assert health["databases"]["db1"]["journal_mode"] == "wal"
    # PRAGMA synchronous reads back as an integer: FULL == 2.
    assert health["databases"]["db1"]["synchronous"] == 2


def test_vector_cache_absent_is_not_degraded():
    """No sidecar yet (lazy by design) is 'not built', never degraded."""
    _capture("sidecar shard eta", "body", embedding=[0.1] * 8)
    health = shards.lane_health()
    assert health["vector_cache"]["present"] is False
    assert health["vector_cache"]["files"] == 0
    assert "vector_cache" not in health["degraded_lanes"]


def test_lane_health_exported_from_package():
    """``from nougen_shards import lane_health`` works (public API)."""
    from nougen_shards import lane_health  # pylint: disable=import-outside-toplevel

    assert callable(lane_health)
    assert lane_health()["vault_dir"]
