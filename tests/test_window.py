"""Time-first recall is native to the substrate, not a phone-only tool."""
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from nougen_shards import window as w


NOW = datetime(2026, 11, 8, 1, 0, tzinfo=timezone.utc)


def test_split_temporal_whole_phrase_and_mixed():
    win, rest = w.split_temporal("recall march", now=NOW)
    assert win.label == "March 2026" and rest == ""
    win, rest = w.split_temporal("gemini upgrade in march", now=NOW)
    assert win.label == "March 2026" and rest == "gemini upgrade"
    win, rest = w.split_temporal("march 2026 gemini upgrade", now=NOW)
    assert win.label == "March 2026" and rest == "gemini upgrade"
    win, rest = w.split_temporal("gemini upgrade", now=NOW)
    assert win is None and rest == "gemini upgrade"
    win, rest = w.split_temporal("what happened last week", now=NOW)
    assert win is not None and rest == ""
    # Ordinary words that happen to contain a month abbreviation stay text.
    win, rest = w.split_temporal("marral surname rulings", now=NOW)
    assert win is None


@pytest.fixture
def grid(tmp_path, monkeypatch):
    """A one-DB grid with a bulk type, a burst day, and a few real records."""
    from nougen_shards import core
    monkeypatch.setenv("NOUGEN_TZ", "UTC")   # the operator shell may carry a local zone
    db = tmp_path / "nougen_shards_1.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,"
                 " event_type TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, tags TEXT,"
                 " utility_score REAL DEFAULT 1.0, access_count INTEGER DEFAULT 0)")
    rows = []
    topics = ["alpha", "beta", "gamma", "delta"]
    for i in range(40):   # bulk arXiv rows, one day, four title shapes
        rows.append((f"2026-03-04T10:{i:02d}:00Z", "ARXIV_RESEARCH", f"arxiv {topics[i % 4]} paper {i}", "x", "[]", 1.2, 0))
    for i in range(6):    # import burst, same shape, another day
        rows.append((f"2026-03-20T09:0{i}:00Z", "reference", f"Phoebus Memory {1400+i}: Project", "x", "[]", 0.95, 0))
    rows.append(("2026-03-19T14:05:00Z", "KNOWLEDGE", "Gemini Agent Upgrade: deep research orchestrator", "routing", '["gemini"]', 1.0, 3))
    rows.append(("2026-03-26T08:00:00Z", "DECISION", "Vault path rule locked", "no hardcode", "[]", 1.0, 1))
    rows.append(("2026-04-02T08:00:00Z", "KNOWLEDGE", "April thing", "x", "[]", 1.0, 0))
    conn.executemany("INSERT INTO shards (timestamp,event_type,title,content,tags,utility_score,access_count)"
                     " VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()
    monkeypatch.setattr(core, "get_db_path", lambda i: tmp_path / f"nougen_shards_{i}.db")

    def _conn(i):
        c = sqlite3.connect(tmp_path / f"nougen_shards_{i}.db"); c.row_factory = sqlite3.Row; return c
    monkeypatch.setattr(core, "get_connection", _conn)
    return tmp_path


def test_retrieve_window_counts_folds_bulk_and_spreads(grid):
    res = w.retrieve_window("march 2026", limit=6)
    assert res["window"]["label"] == "March 2026"
    assert res["total"] == 48 and "April thing" not in json.dumps(res)
    assert res["bulk_types_folded"] == {"ARXIV_RESEARCH": 40}
    titles = [s["title"] for s in res["shards"]]
    assert "Gemini Agent Upgrade: deep research orchestrator" in titles
    assert "Vault path rule locked" in titles
    assert sum(t.startswith("Phoebus Memory") for t in titles) == 1      # digit-blind dedupe
    assert not any(t.startswith("arxiv") for t in titles)                 # folded, not listed
    assert res["by_day"]["2026-03-04"] == 40 and res["by_type"]["KNOWLEDGE"] == 1


def test_retrieve_window_query_narrows_and_minute_precision(grid):
    res = w.retrieve_window("march 2026", query="gemini", limit=5)
    assert res["total"] == 1 and res["shards"][0]["locator"].endswith("#47")
    res = w.retrieve_window("2026-03-19 14:05")
    assert res["total"] == 1 and res["shards"][0]["title"].startswith("Gemini")
    res = w.retrieve_window("2026-03-19 14:06")
    assert res["total"] == 0 and "Nothing recorded" in w.format_packet(res)


def test_retrieve_window_refuses_non_temporal(grid):
    res = w.retrieve_window("marral")
    assert "could not read" in res["error"]
    assert w.format_packet(res).startswith("Window recall:")


def test_only_bulk_window_still_lists(grid):
    res = w.retrieve_window("2026-03-04", limit=3)
    assert res["total"] == 40 and len(res["shards"]) == 3 and res["bulk_types_folded"] == {}


def test_format_packet_shape(grid):
    text = w.format_packet(w.retrieve_window("march 2026", limit=4))
    assert text.startswith("Window: March 2026")
    assert "Recorded: 48 shards; folded bulk: ARXIV_RESEARCH x40" in text
    assert "Busiest days: 2026-03-04 (40)" in text
    assert "blade" not in text or "#" in text   # locators, never bare ids
