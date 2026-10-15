"""shard_bundle: read-only constellation under a token budget."""
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as core
from nougen_shards import graph


@pytest.fixture
def vault(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        monkeypatch.setenv("NOUGEN_VAULT_DIR", str(t))
        monkeypatch.setattr(core, "GLOBAL_DIR", t)
        monkeypatch.setattr(core, "get_db_path", lambda i: t / f"t_{i}.db")
        core.init_db(1)
        monkeypatch.setattr(graph, "get_graph_db_path", lambda: t / "graph.db")
        graph.init_graph_db()
        yield t


def test_bundle_returns_seed_and_linked_neighbour(vault):
    a = core.capture("KNOWLEDGE", "Seed shard bzq11", "seed body bzq11", domain_key="global")
    b = core.capture("KNOWLEDGE", "Neighbour shard bzq22", "neighbour body bzq22", domain_key="global")
    graph.link_shards(a.shard_id, b.shard_id, "relates", src_db=a.db_index, dst_db=b.db_index)
    out = graph.shard_bundle([(a.shard_id, a.db_index)], depth=1, token_budget=4000)
    assert out["included"] == 2
    assert "Seed shard bzq11" in out["markdown"] and "Neighbour shard bzq22" in out["markdown"]


def test_budget_truncates_and_reports(vault):
    big = core.capture("KNOWLEDGE", "Big shard bzq33", "x" * 20000, domain_key="global")
    out = graph.shard_bundle([(big.shard_id, big.db_index)], depth=0, token_budget=300)
    assert out["approx_tokens"] <= 300
    assert "[truncated]" in out["markdown"]


def test_unknown_seed_is_empty(vault):
    out = graph.shard_bundle([(999, 1)], depth=1, token_budget=500)
    assert out["included"] == 0 and out["markdown"] == ""
