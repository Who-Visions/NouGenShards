"""DREAM trust identity: confidence saturates at 1.0, and shard records keep their database.

Relay 20261013T024409 / 20261013T024902: semantic confidence had no upper bound
(`confidence_score + 0.1`), and fetch_high_utility_shards dropped the database
index, so the same shard id on two databases could not be told apart.
"""
import sqlite3

import pytest

from nougen_shards import core, dream

TS = "2026-10-13T00:00:00Z"


@pytest.fixture
def semantic_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE semantic_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            confidence_score REAL DEFAULT 1.0,
            domain_key TEXT DEFAULT 'global',
            updated_at TEXT NOT NULL,
            UNIQUE(subject, predicate)
        )""")
    yield conn
    conn.close()


def _confidence(conn, subject, predicate):
    return conn.execute(
        "SELECT confidence_score FROM semantic_knowledge WHERE subject=? AND predicate=?",
        (subject, predicate),
    ).fetchone()[0]


def test_repeated_corroboration_never_exceeds_one(semantic_db):
    for _ in range(25):
        dream.upsert_semantic_rule(semantic_db, "Veil", "is anomalous", "global", TS)
    assert _confidence(semantic_db, "Veil", "is anomalous") == pytest.approx(1.0)


def test_step_still_applies_below_the_ceiling(semantic_db):
    semantic_db.execute(
        "INSERT INTO semantic_knowledge (subject, predicate, confidence_score, updated_at) VALUES ('a', 'b', 0.5, ?)",
        (TS,),
    )
    dream.upsert_semantic_rule(semantic_db, "a", "b", "global", TS)
    assert _confidence(semantic_db, "a", "b") == pytest.approx(0.6)


def test_row_already_above_one_is_pulled_back_to_the_ceiling(semantic_db):
    # Rows written before the clamp may already sit above 1.0; the next corroboration must not grow them.
    semantic_db.execute(
        "INSERT INTO semantic_knowledge (subject, predicate, confidence_score, updated_at) VALUES ('a', 'b', 3.7, ?)",
        (TS,),
    )
    dream.upsert_semantic_rule(semantic_db, "a", "b", "global", TS)
    assert _confidence(semantic_db, "a", "b") == pytest.approx(1.0)


def test_new_rule_starts_at_the_schema_default(semantic_db):
    dream.upsert_semantic_rule(semantic_db, "x", "y", "global", TS)
    assert _confidence(semantic_db, "x", "y") == pytest.approx(1.0)


def _connect(path):
    # core.get_connection sets sqlite3.Row; fetch_high_utility_shards relies on it.
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _make_shard_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, title TEXT, content TEXT, utility_score REAL)")
    conn.executemany("INSERT INTO shards VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def test_fetch_keeps_database_index_for_colliding_shard_ids(tmp_path, monkeypatch):
    paths = {1: tmp_path / "db1.sqlite", 2: tmp_path / "db2.sqlite"}
    _make_shard_db(paths[1], [(7, "from db one", "one", 0.9)])
    _make_shard_db(paths[2], [(7, "from db two", "two", 0.8)])

    monkeypatch.setattr(core, "MAX_DB_COUNT", 2)
    monkeypatch.setattr(core, "get_db_path", lambda i: paths[i])
    monkeypatch.setattr(core, "get_connection", lambda i: _connect(paths[i]))

    records = dream.fetch_high_utility_shards(limit=10)

    assert [(r["id"], r["_db_index"]) for r in records] == [(7, 1), (7, 2)]
    assert {r["title"] for r in records} == {"from db one", "from db two"}


def test_fetch_orders_globally_by_utility(tmp_path, monkeypatch):
    paths = {1: tmp_path / "db1.sqlite", 2: tmp_path / "db2.sqlite"}
    _make_shard_db(paths[1], [(1, "low", "", 0.1)])
    _make_shard_db(paths[2], [(2, "high", "", 0.9)])

    monkeypatch.setattr(core, "MAX_DB_COUNT", 2)
    monkeypatch.setattr(core, "get_db_path", lambda i: paths[i])
    monkeypatch.setattr(core, "get_connection", lambda i: _connect(paths[i]))

    records = dream.fetch_high_utility_shards(limit=1)
    assert records[0]["title"] == "high" and records[0]["_db_index"] == 2
