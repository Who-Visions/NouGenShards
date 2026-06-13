"""Tests for Graph Memory (the latent mesh of shard edges)."""
# pylint: disable=duplicate-code, protected-access
import tempfile
import pytest
from pathlib import Path
import nougen_shards.core as core
from nougen_shards import graph


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Isolate the shard cluster + graph store in a temp vault."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(core, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(core, "get_db_path", mock_get_db_path)

        core.init_db(1)
        yield temp_path


def _make_three():
    """Capture three shards and return (id, db_index) for each."""
    core.capture("FIX", "Auth bug fix", "Fixed the JWT expiry check in auth middleware.")
    core.capture("FILE", "auth source", "The auth middleware source file content.")
    core.capture("DECISION", "Use RS256", "Decided to switch JWT signing to RS256 keys.")
    a = core.retrieve("Auth bug fix")[0]
    b = core.retrieve("auth middleware source")[0]
    c = core.retrieve("RS256 signing")[0]
    return (a["id"], a["_db_index"]), (b["id"], b["_db_index"]), (c["id"], c["_db_index"])


def test_link_and_count():
    (a, adb), (b, bdb), _ = _make_three()
    assert graph.link_shards(a, b, "touches", adb, bdb) is True
    assert graph.edge_count() == 1


def test_link_is_idempotent():
    (a, adb), (b, bdb), _ = _make_three()
    assert graph.link_shards(a, b, "touches", adb, bdb) is True
    assert graph.link_shards(a, b, "touches", adb, bdb) is False  # duplicate edge
    assert graph.edge_count() == 1


def test_self_link_rejected():
    (a, adb), _, _ = _make_three()
    assert graph.link_shards(a, a, "relates", adb, adb) is False
    assert graph.edge_count() == 0


def test_link_to_missing_shard_rejected():
    (a, adb), _, _ = _make_three()
    assert graph.link_shards(a, 99999, "relates", adb, 1) is False


def test_related_shards_follows_both_directions():
    (a, adb), (b, bdb), (c, cdb) = _make_three()
    graph.link_shards(a, b, "touches", adb, bdb)
    graph.link_shards(a, c, "caused_by", adb, cdb)

    rel = graph.related_shards(a, adb)
    titles = {r["title"] for r in rel}
    assert "auth source" in titles
    assert "Use RS256" in titles

    # c has only an inbound edge from a — undirected recall still surfaces a.
    rel_c = graph.related_shards(c, cdb)
    assert any(r["title"] == "Auth bug fix" and r["direction"] == "in" for r in rel_c)


def test_related_relation_filter():
    (a, adb), (b, bdb), (c, cdb) = _make_three()
    graph.link_shards(a, b, "touches", adb, bdb)
    graph.link_shards(a, c, "caused_by", adb, cdb)

    only_touches = graph.related_shards(a, adb, relation="touches")
    assert [r["title"] for r in only_touches] == ["auth source"]


def test_bidirectional_link():
    (a, adb), (b, bdb), _ = _make_three()
    assert graph.link_shards(a, b, "relates", adb, bdb, bidirectional=True) is True
    assert graph.edge_count() == 2


def test_related_empty_when_no_edges():
    (a, adb), _, _ = _make_three()
    assert graph.related_shards(a, adb) == []
