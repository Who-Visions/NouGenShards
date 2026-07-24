"""Regression: retrieve() ranking must be deterministic.

A prior implementation added `random.uniform(0, 0.02)` jitter to every shard's
tripartite utility score, so identical queries returned different orderings and
scores run-to-run. These tests pin deterministic behavior.
"""
import tempfile
from datetime import timedelta
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


def test_ranking_samples_the_clock_once_per_pass(monkeypatch):
    """Root-cause guard for the id-order flake (2026-07-24).

    test_retrieve_ranking_is_deterministic above was a real failure, not a bad
    assertion -- it failed on roughly 1 run in 13 on pristine source. Cause:
    every ranking lane inlined `datetime.now()` PER CANDIDATE ROW, so a shard's
    recency decay depended on where in the scan loop it landed. Over the 30-day
    half-life the microseconds between two rows shift a score by ~1e-12, which
    is bigger than the gap between shards captured seconds apart, so
    near-identical candidates swapped places between two calls on an unchanged
    vault.

    Asserting the ordering repeatedly would only re-create a probabilistic
    test. This asserts the invariant instead: one retrieval = one clock
    reading, shared by every candidate. Restore per-row sampling and the count
    jumps to one call per row per lane.
    """
    _seed()

    base = shards._now_utc()
    calls = {"n": 0}

    def _ticking_clock():
        # Each sample is a DAY apart. Harmless if the clock is read once per
        # pass; catastrophic for ranking if it is read per candidate.
        calls["n"] += 1
        return base + timedelta(days=calls["n"])

    monkeypatch.setattr(shards, "_now_utc", _ticking_clock)

    first = shards.retrieve("automation", limit=5)
    assert calls["n"] == 1, (
        f"retrieve() sampled the clock {calls['n']} times in one pass; "
        "candidates are being aged against different instants")

    # And the consequence: a uniformly advancing clock decays every candidate by
    # the same factor, so the ORDER must not move even as absolute scores fall.
    for _ in range(4):
        again = shards.retrieve("automation", limit=5)
        assert [(r["_db_index"], r["id"]) for r in again] == \
               [(r["_db_index"], r["id"]) for r in first]


def test_equal_scores_break_ties_on_a_stable_shard_identity():
    """Stable sort alone only preserves *scan* order; ties must be broken on
    something durable, or the same two shards rank differently once the grid
    scan order changes (a shard's home DB moves when its target is full)."""
    tied = [
        {"_db_index": 7, "id": 3, "final_score": 0.5},
        {"_db_index": 2, "id": 9, "final_score": 0.5},
        {"_db_index": 2, "id": 1, "final_score": 0.5},
        {"_db_index": 4, "id": 1, "final_score": 0.9},
    ]
    ranked = sorted(tied, key=shards._rank_key)
    assert [(r["_db_index"], r["id"]) for r in ranked] == [(4, 1), (2, 1), (2, 9), (7, 3)]
    # Same total order regardless of the order the scan produced them in.
    assert sorted(reversed(tied), key=shards._rank_key) == ranked


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
