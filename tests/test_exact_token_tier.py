"""Identifier-shaped queries rank shards that contain the identifier first."""
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


def test_id_query_ranks_the_containing_shard_first():
    for n in range(6):
        shards.capture("KNOWLEDGE", f"Video notes {n}", f"unrelated commentary about video transcripts {n}",
                       domain_key="global")
    shards.capture("KNOWLEDGE", "The one", "contains ZxQ9vTbL7mA exactly", domain_key="global")
    rows = shards.retrieve("ZxQ9vTbL7mA", limit=3)
    assert rows and rows[0]["title"] == "The one"
    assert rows[0]["_token_exact"] is True


def test_prose_query_is_not_token_mode(monkeypatch):
    shards.capture("KNOWLEDGE", "Plain", "some plain text with abc123 inside", domain_key="global")
    rows = shards.retrieve("plain text", limit=3)
    assert all(r.get("_token_exact") is False for r in rows)


def test_env_disables(monkeypatch):
    monkeypatch.setenv("NOUGEN_TOKEN_EXACT_TIER", "0")
    shards.capture("KNOWLEDGE", "Off", "has tok12345 here", domain_key="global")
    rows = shards.retrieve("tok12345", limit=3)
    assert all(r.get("_token_exact") is False for r in rows)


def test_id_token_in_ingest_row_surfaces_even_when_page_is_full():
    bulk = (shards.bulk_ingest_event_types() or [None])[0]
    if bulk is None:
        pytest.skip("no bulk ingest types")
    for n in range(8):
        shards.capture("KNOWLEDGE", f"Filler about qx9zz1 {n}", f"filler body qx9zz1 number {n}",
                       domain_key="global")
    shards.capture(bulk, "Transcript", "video id Zk3mP9xQw2L lives only in this ingested transcript",
                   domain_key="global")
    rows = shards.retrieve("Zk3mP9xQw2L", limit=3)
    assert rows and rows[0]["title"] == "Transcript"
