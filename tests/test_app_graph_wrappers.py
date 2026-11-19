"""The node's graph MCP wrappers must reach graph.* with its real signatures.

recall_related used to send the shard id as a text query to recall_graph, which
called graph.query_subgraph and vector_graph.search_graph -- neither exists -- so
every remote call failed with an AttributeError. link_shards had no remote tool at
all, and the connector faked it through link_destiny.
"""
import app
from nougen_shards import graph


def _call(tool, **kw):
    return app._unwrap_sync(tool)(**kw)


def test_recall_related_walks_the_real_graph(monkeypatch):
    seen = {}

    def fake_related(shard_id, db_index, relation, limit):
        seen.update(shard_id=shard_id, db_index=db_index, relation=relation, limit=limit)
        return [{"id": 7, "direction": "out", "relation": "fixes", "title": "t", "content": "c"}]

    monkeypatch.setattr(graph, "related_shards", fake_related)
    out = _call(app.recall_related, shard_id=30389, db_index=7, relation="fixes", limit=3)
    assert seen == {"shard_id": 30389, "db_index": 7, "relation": "fixes", "limit": 3}
    assert out["count"] == 1 and out["related"][0]["id"] == 7


def test_link_shards_reports_whether_an_edge_was_written(monkeypatch):
    calls = []
    monkeypatch.setattr(graph, "link_shards", lambda *a: calls.append(a) or True)
    made = _call(app.link_shards, src_id=1, dst_id=2, relation="caused_by", src_db=3, dst_db=4)
    assert calls == [(1, 2, "caused_by", 3, 4)]
    assert made["created"] is True and made["note"] is None

    monkeypatch.setattr(graph, "link_shards", lambda *a: False)
    refused = _call(app.link_shards, src_id=1, dst_id=1)
    assert refused["created"] is False and refused["note"]


def test_recall_graph_names_the_missing_backend_instead_of_crashing(monkeypatch):
    from nougen_shards import vector_graph
    monkeypatch.delattr(vector_graph, "search_graph", raising=False)
    monkeypatch.delattr(graph, "query_subgraph", raising=False)
    out = _call(app.recall_graph, query="anything")
    assert "no graph search backend" in out["error"]
