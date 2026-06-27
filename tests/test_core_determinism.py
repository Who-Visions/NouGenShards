"""Regression: retrieve() ranking must be deterministic.

A prior implementation added `random.uniform(0, 0.02)` jitter to every shard's
tripartite utility score, so identical queries returned different orderings and
scores run-to-run. These tests pin deterministic behavior.
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
        shards.init_db(1)
        yield temp_path


def _seed():
    for i in range(6):
        shards.capture("KNOWLEDGE", f"Automation tool {i}",
                       f"This automation tool number {i} handles pipeline automation.")


def test_retrieve_ranking_is_deterministic():
    _seed()
    first = shards.retrieve("automation", limit=5)
    for _ in range(5):
        again = shards.retrieve("automation", limit=5)
        # Ordering must be identical run-to-run (the random jitter reordered ties).
        assert [r["id"] for r in again] == [r["id"] for r in first], "id order drifted"
        # Scores may differ only by sub-microsecond temporal decay (now() advances
        # ~1e-8 between calls). The removed random epsilon was up to 0.02, so a 1e-4
        # tolerance tolerates legitimate decay drift while still catching jitter.
        for a, b in zip(again, first):
            assert abs(a["utility_score_tripartite"] - b["utility_score_tripartite"]) < 1e-4


def test_density_score_flows_into_retrieve():
    # density_score is now SELECTed, so a shard's stored density actually reaches
    # the tripartite score instead of silently defaulting to 1.0.
    shards.capture("KNOWLEDGE", "Density probe", "unique density probe content here",
                   density_score=0.5)
    res = shards.retrieve("density probe", limit=3)
    assert res, "expected a hit"
    # The column round-trips (present on the row, not dropped by the query).
    row = shards.get_shard_by_id(res[0]["id"], res[0]["_db_index"])
    assert row is not None and "density_score" in row
