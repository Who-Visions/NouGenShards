"""recall_memory is bounded by default: one huge shard must not fill the packet.

Regression for WhoArt 2026-09-20: a 2-hit recall returned a 994k-char screenplay
shard untruncated and the MCP transport timed out. NOUGEN_RECALL_TOKEN_BUDGET
unset now means DEFAULT_RECALL_TOKEN_BUDGET; "0" keeps the old unbounded packet.
"""
import pytest

from nougen_shards import mcp as shards_mcp


def _huge_hits():
    return [
        {"id": 1, "_db_index": 1, "title": "huge", "content": "x" * 900_000, "final_score": 0.9,
         "timestamp": "2026-09-11T02:42:00Z"},
        {"id": 2, "_db_index": 2, "title": "small", "content": "y" * 200, "final_score": 0.5,
         "timestamp": "2026-09-11T02:43:00Z"},
    ]


@pytest.fixture
def stub_retrieve(monkeypatch):
    monkeypatch.setattr(shards_mcp, "federated_retrieve",
                        lambda query, limit=3, sweep_report=None: _huge_hits())


def test_default_budget_truncates_a_huge_first_record(stub_retrieve, monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_TOKEN_BUDGET", raising=False)
    packet = shards_mcp.recall_memory("anything")
    assert len(packet) < shards_mcp.DEFAULT_RECALL_TOKEN_BUDGET * 4 + 500
    assert "[truncated to budget]" in packet


def test_zero_restores_unbounded(stub_retrieve, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_TOKEN_BUDGET", "0")
    packet = shards_mcp.recall_memory("anything")
    assert len(packet) > 900_000 and "[truncated to budget]" not in packet


def test_explicit_budget_wins(stub_retrieve, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_TOKEN_BUDGET", "500")
    packet = shards_mcp.recall_memory("anything")
    assert len(packet) < 500 * 4 + 500
