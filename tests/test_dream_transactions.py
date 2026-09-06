"""Use real throwaway SQLite transactions to verify Dream's reported outcomes."""
import sqlite3

import pytest

from nougen_shards import dream


@pytest.fixture
def grid(tmp_path, monkeypatch):
    def path(index):
        return tmp_path / f"db{index}.sqlite"

    def connection(index):
        conn = sqlite3.connect(path(index))
        conn.row_factory = sqlite3.Row
        return conn

    for index in (1, 2):
        with connection(index) as conn:
            conn.executescript("""
                CREATE TABLE shards (id INTEGER PRIMARY KEY, content TEXT,
                    domain_key TEXT DEFAULT 'global', utility_score REAL DEFAULT 1,
                    consolidated INTEGER DEFAULT 0);
                CREATE TABLE semantic_knowledge (subject TEXT, predicate TEXT,
                    domain_key TEXT, updated_at TEXT, confidence_score REAL DEFAULT 1,
                    UNIQUE(subject, predicate));
                INSERT INTO shards (id, content, utility_score) VALUES (1, 'source', 2);
            """)
    monkeypatch.setattr(dream.core, "MAX_DB_COUNT", 2)
    monkeypatch.setattr(dream.core, "get_db_path", path)
    monkeypatch.setattr(dream.core, "get_connection", connection)
    return connection


def test_rolled_back_rules_are_not_reported_as_saved(grid, monkeypatch):
    with grid(1) as conn:
        conn.execute("""CREATE TRIGGER reject_bad BEFORE INSERT ON semantic_knowledge
            WHEN NEW.subject = 'bad' BEGIN SELECT RAISE(ABORT, 'rejected'); END""")
    monkeypatch.setattr(dream, "extract_semantic_invariants_via_llm", lambda _: [
        {"subject": "good", "predicate": "candidate"},
        {"subject": "bad", "predicate": "candidate"},
    ])
    result = dream.consolidate_episodic_data(limit=1)
    assert result["new_invariants_extracted"] == 0
    assert result["shards_consolidated"] == 0
    assert result["rules"] == []
    assert not result["complete"]
    assert result["errors"][0]["stage"] == "save"
    with grid(1) as conn:
        assert conn.execute("SELECT COUNT(*) FROM semantic_knowledge").fetchone()[0] == 0
        assert conn.execute("SELECT consolidated FROM shards").fetchone()[0] == 0


def test_budget_selects_highest_utility_across_databases(grid, monkeypatch):
    with grid(2) as conn:
        conn.execute("INSERT INTO shards (id, content, utility_score) VALUES (2, 'best', 10)")
    seen = []

    def extract(content):
        seen.append(content)
        return [{"subject": "Memory", "predicate": "candidate"}]

    monkeypatch.setattr(dream, "extract_semantic_invariants_via_llm", extract)
    result = dream.consolidate_episodic_data(limit=1)
    assert seen == ["best"]
    assert result["shards_consolidated"] == 1
    assert result["shards_scanned"] == 1
    assert result["complete"]


@pytest.mark.parametrize("value", [True, -1, 1.5, "10"])
def test_invalid_budget_is_rejected(grid, value):
    with pytest.raises(ValueError):
        dream.consolidate_episodic_data(limit=value)


def test_whitespace_rules_do_not_retire_source(grid, monkeypatch):
    monkeypatch.setattr(dream, "extract_semantic_invariants_via_llm",
                        lambda _: [{"subject": "  ", "predicate": "fact"}])
    assert dream.consolidate_episodic_data(1)["shards_consolidated"] == 0


def test_malformed_extraction_reports_failure(grid, monkeypatch):
    monkeypatch.setattr(dream, "extract_semantic_invariants_via_llm", lambda _: 42)
    result = dream.consolidate_episodic_data(1)
    assert not result["complete"]
    assert result["errors"][0]["stage"] == "extract"
