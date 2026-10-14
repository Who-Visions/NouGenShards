"""The no-hit-after-ingest-filter fallback must still find bulk-ingest rows, and
must get them from the trigram index rather than a LIKE scan of every row."""
# pylint: disable=protected-access
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def vault(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path", lambda i: temp_path / f"t_{i}.db")
        shards.init_db(1)
        yield temp_path


def _bulk_type():
    types = shards.bulk_ingest_event_types()
    return types[0] if types else None


def test_ingest_row_found_without_like_scan(monkeypatch):
    bulk = _bulk_type()
    if bulk is None:
        pytest.skip("no bulk ingest event types configured")
    shards.capture(bulk, "Transcript zq9xv", "uniquetokenzq9xv appears only in an ingested row",
                   domain_key="global")
    statements = []
    real_get = shards.get_connection

    def traced(i):
        conn = real_get(i)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(shards, "get_connection", traced)
    monkeypatch.delenv("NOUGEN_LIKE_ON_FTS_MISS", raising=False)
    rows = shards.retrieve("uniquetokenzq9xv", limit=3)
    assert any("uniquetokenzq9xv" in (r.get("content") or "") for r in rows)
    assert not any("content LIKE" in s for s in statements), "full LIKE scan ran despite a healthy index"


def test_like_scan_opt_in(monkeypatch):
    bulk = _bulk_type()
    if bulk is None:
        pytest.skip("no bulk ingest event types configured")
    shards.capture(bulk, "Transcript qq7", "optintokenqq7 only in ingested row", domain_key="global")
    monkeypatch.setenv("NOUGEN_LIKE_ON_FTS_MISS", "1")
    rows = shards.retrieve("optintokenqq7", limit=3)
    assert any("optintokenqq7" in (r.get("content") or "") for r in rows)


def test_short_query_uses_like_fallback_without_error():
    """All tokens < 3 chars -> no FTS expression; must take the LIKE path, not raise."""
    shards.capture("TEST", "short", "hi there friend", domain_key="global")
    rows = shards.retrieve("hi", limit=3)
    assert isinstance(rows, list)


def test_exact_ingest_row_fills_an_underfilled_filtered_pass():
    """Ingest row with an exact term is appended when filtered hits do not fill the page."""
    bulk = _bulk_type()
    if bulk is None:
        pytest.skip("no bulk ingest event types configured")
    shards.capture("KNOWLEDGE", "Note about rescuetokenab12", "memory note mentions rescuetokenab12",
                   domain_key="global")
    shards.capture(bulk, "Transcript", "transcript body contains rescuetokenab12 as its video id",
                   domain_key="global")
    rows = shards.retrieve("rescuetokenab12", limit=5)
    titles = [r.get("title") for r in rows]
    assert "Note about rescuetokenab12" in titles
    assert "Transcript" in titles, titles


def test_rescued_ingest_row_does_not_take_title_exact_tier():
    bulk = _bulk_type()
    if bulk is None:
        pytest.skip("no bulk ingest event types configured")
    shards.capture("KNOWLEDGE", "Memory about exacttitleqx7", "memory note body mentions exacttitleqx7",
                   domain_key="global")
    shards.capture(bulk, "exacttitleqx7", "ingested transcript body for exacttitleqx7", domain_key="global")
    rows = shards.retrieve("exacttitleqx7", limit=5)
    rescued = [r for r in rows if r.get("title") == "exacttitleqx7"]
    assert rescued and rescued[0].get("_ingest_rescue") is True
    assert rescued[0].get("_title_exact") is False, "rescued ingest row took the exact-title tier"
