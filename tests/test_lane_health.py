"""HARDENING invariant 4: recall responses carry lane health.

A dead semantic index once returned "no relevant shards" while 27k shards sat
unembedded — a broken sensor reporting absence as fact. Empty recall must now
surface embedding coverage so callers don't assert absence from a degraded lane.

Rewritten 2026-07-24. The old version set NOUGEN_EMBED_MODEL="" and called that
"hermetic", then asserted 0% coverage. It was neither: an empty string is falsy,
so the model still resolved off the live /api/tags roster, and 0% was true only
because capture() was raising NameError before it ever reached the embedder. A
one-sided test that only ever asserts the DEGRADED outcome cannot tell a real
outage from a broken ingest path, so every test here now pins BOTH directions:
embedder down -> 0% and a degradation warning, embedder up -> 100% and silence.
"""
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards
from nougen_shards import embedding_backfill


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path",
                            lambda index: temp_path / f"test_shards_{index}.db")
        # Never touch a live host: the embedder is stubbed per-test below, so
        # these assertions describe capture()'s behaviour, not the operator's
        # current ollama state.
        monkeypatch.setattr(embedding_backfill, "resolve_embed_model",
                            lambda *a, **k: "stub-embed-model")
        shards.init_db(1)
        yield temp_path


@pytest.fixture
def embedder_down(monkeypatch):
    """A genuine outage: connection refused (an OSError), which capture()
    degrades on by design."""
    def _refuse(*a, **k):
        raise ConnectionRefusedError("ollama not listening")
    monkeypatch.setattr(embedding_backfill, "embed", _refuse)


@pytest.fixture
def embedder_up(monkeypatch):
    monkeypatch.setattr(embedding_backfill, "embed",
                        lambda *a, **k: [0.0, 1.0, 0.0])


def test_lane_health_reports_zero_coverage_when_embedder_is_down(embedder_down):
    for i in range(3):
        shards.capture("KNOWLEDGE", f"note {i}", f"unique body number {i} about pipelines")
    h = shards.lane_health()
    assert h["ok"] is True
    assert h["total_shards"] == 3
    assert h["embedding_coverage_pct"] == 0.0


def test_lane_health_reports_full_coverage_when_embedder_is_up(embedder_up):
    """The direction the old suite never checked: shards are born embedded.

    If capture() stops embedding — as it did on 2026-07-24 — coverage collapses
    to 0.0 and this fails. That is the whole point of asserting the healthy side.
    """
    for i in range(3):
        shards.capture("KNOWLEDGE", f"note {i}", f"unique body number {i} about pipelines")
    h = shards.lane_health()
    assert h["ok"] is True
    assert h["total_shards"] == 3
    assert h["embedding_coverage_pct"] == 100.0


def test_empty_recall_warns_when_lane_is_degraded(embedder_down):
    shards.capture("KNOWLEDGE", "seed", "some indexed content about retrieval")
    # Query that matches nothing -> empty packet, but it must not be a bare marker.
    packet = shards.compile_recall_packet([])
    assert "NO RELEVANT MEMORY" in packet
    assert "shards" in packet  # coverage annotation present
    # With 0% embedding coverage the notice must warn the lane is degraded.
    assert "DEGRADED SEMANTIC LANE" in packet


def test_empty_recall_does_not_cry_wolf_on_a_healthy_lane(embedder_up):
    """A fully embedded vault returning nothing is a real 'no match'; annotating
    it as degraded would train callers to ignore the warning."""
    shards.capture("KNOWLEDGE", "seed", "some indexed content about retrieval")
    packet = shards.compile_recall_packet([])
    assert "NO RELEVANT MEMORY" in packet
    assert "100.0% embedded" in packet
    assert "DEGRADED SEMANTIC LANE" not in packet


def test_populated_recall_unaffected():
    packet = shards.compile_recall_packet([
        {"id": 1, "_db_index": 1, "final_score": 0.9, "timestamp": None,
         "title": "t", "content": "hello vault"}])
    assert "hello vault" in packet
    assert "NO RELEVANT MEMORY" not in packet
