"""Behavioural tests for the NouGenShards HistoryEngine.

This file used to be a print-only verification script whose "no results found"
branch was a bare `return`, so a total retrieval failure exited GREEN. Every
path below now asserts on concrete, seeded values and there is deliberately no
early-return: an empty result is a failure, not a skip.
"""
import json
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards
import nougen_shards.history as history
from nougen_shards import capture, retrieve, mark_shard, HistoryEngine

# Rule 0.2: the window is a parameter of the engine, not a magic string.
PERIOD = "24h"
# mark_shard(worked=True) credits exactly +1.0 to a shard's utility prior.
WORKED_UTILITY_DELTA = 1.0

SEEDED_SHARDS = (
    {
        "event_type": "RESEARCH",
        "title": "History Test Shard",
        "content": "This is a unit of experience for history tracking verification.",
        "tags": ["test", "history"],
    },
    {
        "event_type": "RESEARCH",
        "title": "Decoy Shard",
        "content": "Unrelated payload about photographic lighting rigs.",
        "tags": ["test", "decoy"],
    },
)
TARGET_TITLE = SEEDED_SHARDS[0]["title"]
DECOY_TITLE = SEEDED_SHARDS[1]["title"]
RETRIEVAL_QUERY = "history tracking"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Isolate both the shard grid and the history substrate in a temp dir."""
    # ignore_cleanup_errors: the attribution writer can still hold history.db
    # open on Windows when the test body ends; a teardown unlink race must not
    # be reported as a test failure.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(shards, "get_db_path", mock_get_db_path)

        shards.init_db(1)
        yield temp_path


def seed_shard(spec):
    """Capture one fixture shard; the capture must succeed."""
    assert capture(**spec) is True, f"capture failed for {spec['title']}"


def seed_shards():
    """Capture the fixture shards; every capture must succeed."""
    for spec in SEEDED_SHARDS:
        seed_shard(spec)
    return len(SEEDED_SHARDS)


def locate_target_shard():
    """Retrieve the seeded target shard. No early-return: empty is a failure."""
    results = retrieve(RETRIEVAL_QUERY, limit=len(SEEDED_SHARDS))
    assert results, f"retrieval returned nothing for {RETRIEVAL_QUERY!r}"
    matches = [r for r in results if r["title"] == TARGET_TITLE]
    assert matches, (
        f"{TARGET_TITLE!r} missing from retrieval; got {[r['title'] for r in results]}"
    )
    target = matches[0]
    assert isinstance(target["id"], int)
    assert "history tracking" in target["content"]
    return target


def test_log_event_survives_a_read_before_the_first_write():
    """A READ before the first write must not disable event logging.

    Regression guard for the existence-gated lazy init in history.log_event: any
    read materializes an empty history.db, so `if not path.exists()` skipped the
    init forever after and every subsequent write died on `no such table:
    shard_events`. Initialization is now gated on the schema, so read-first is
    indistinguishable from write-first.
    """
    engine = HistoryEngine()

    # READ FIRST. This is the poison step: it creates history.db on disk.
    assert engine.get_growth_rate(PERIOD) == {
        "period": PERIOD, "new_shards": 0, "total_shards": 0
    }
    assert history.get_history_db_path().exists(), "the read did not create history.db"

    # Now write directly through the logging entry point and prove it landed.
    history.log_event(4242, 1, "CREATED", new_score=1.0)

    conn = history.get_history_connection()
    try:
        rows = conn.execute(
            "SELECT shard_id, db_index, event_type FROM shard_events"
        ).fetchall()
    finally:
        conn.close()
    assert [tuple(r) for r in rows] == [(4242, 1, "CREATED")], (
        "log_event silently dropped the write after a read created the DB file"
    )
    assert engine.get_growth_rate(PERIOD)["total_shards"] == 1


def test_growth_rate_counts_only_shards_created_in_the_window():
    """CREATED events must be counted, and the counter must move per capture.

    The engine is deliberately read BEFORE the first capture: the substrate must
    be usable in either order (see
    test_log_event_survives_a_read_before_the_first_write).
    """
    engine = HistoryEngine()
    assert engine.get_growth_rate(PERIOD)["total_shards"] == 0

    seed_shard(SEEDED_SHARDS[0])
    first = engine.get_growth_rate(PERIOD)
    assert first["period"] == PERIOD
    assert first["new_shards"] == 1
    assert first["total_shards"] == 1

    seed_shard(SEEDED_SHARDS[1])
    second = engine.get_growth_rate(PERIOD)
    assert second["period"] == PERIOD
    assert second["new_shards"] == len(SEEDED_SHARDS)
    assert second["total_shards"] == len(SEEDED_SHARDS)
    assert second["new_shards"] > first["new_shards"]


def test_utility_stats_reflect_a_marked_shard():
    """A single worked mark must show up as exactly one unit of utility growth."""
    seed_shards()
    engine = HistoryEngine()

    assert engine.get_utility_stats(PERIOD) == 0.0

    target = locate_target_shard()
    assert mark_shard(target["id"], worked=True, db_index=target["_db_index"]) is True

    assert engine.get_utility_stats(PERIOD) == pytest.approx(WORKED_UTILITY_DELTA)
    assert engine.get_utility_delta(PERIOD) == pytest.approx(WORKED_UTILITY_DELTA)


def test_top_shards_returns_the_marked_shard_with_its_title():
    """Top shards must be the marked shard, enriched with real core metadata."""
    seed_shards()
    engine = HistoryEngine()

    assert engine.get_top_shards(PERIOD) == []

    target = locate_target_shard()
    mark_shard(target["id"], worked=True, db_index=target["_db_index"])

    top = engine.get_top_shards(PERIOD)
    assert len(top) == 1, f"expected exactly the marked shard, got {top}"
    entry = top[0]
    assert entry["shard_id"] == target["id"]
    assert entry["db_index"] == target["_db_index"]
    assert entry["title"] == TARGET_TITLE
    assert entry["title"] != "Unknown Shard", "shard lookup fell back to a placeholder"
    assert entry["growth"] == pytest.approx(WORKED_UTILITY_DELTA)
    # The stored prior moved by exactly the amount the event recorded.
    assert entry["utility_score"] == pytest.approx(
        target["utility_score"] + WORKED_UTILITY_DELTA
    )
    # The unmarked decoy must not appear.
    assert all(e["title"] != DECOY_TITLE for e in top)


def test_export_stats_json_packs_every_metric():
    """The JSON packet must carry the same live numbers, not zeros."""
    expected_created = seed_shards()
    engine = HistoryEngine()

    target = locate_target_shard()
    mark_shard(target["id"], worked=True, db_index=target["_db_index"])

    packet = json.loads(engine.export_stats_json(PERIOD))

    assert packet["period"] == PERIOD
    assert packet["growth"] == engine.get_growth_rate(PERIOD)
    assert packet["growth"]["new_shards"] == expected_created
    assert packet["utility_delta"] == pytest.approx(WORKED_UTILITY_DELTA)
    assert len(packet["top_shards"]) == 1
    assert packet["top_shards"][0]["title"] == TARGET_TITLE
    assert packet["top_shards"][0]["shard_id"] == target["id"]


def test_period_delta_windows_are_ordered_and_defaulted():
    """Window mapping must be strictly increasing, with an unknown key defaulted."""
    periods = ["24h", "week", "month", "quarter", "year"]
    deltas = [HistoryEngine.get_period_delta(p) for p in periods]
    assert all(a < b for a, b in zip(deltas, deltas[1:])), deltas
    assert HistoryEngine.get_period_delta("not-a-period") == HistoryEngine.get_period_delta("week")


def test_timeline_renders_bars_for_the_bucket_holding_the_captures():
    """The ASCII timeline must observe the captures, not print an empty skeleton."""
    engine = HistoryEngine()
    bar = "█"

    seed_shards()

    populated = engine.get_timeline(PERIOD)
    assert PERIOD in populated
    assert bar in populated, "timeline did not register the captured shards"

    rows = [line for line in populated.splitlines() if bar in line]
    # All captures land in the current bucket, so exactly one column is drawn,
    # normalized to full height (5 rows).
    assert len(rows) == 5, populated
    assert all(row.count(bar) == 1 for row in rows), populated
