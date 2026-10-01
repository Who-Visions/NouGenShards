import copy
import json

from nougen_shards.context_packet import graph_context_packet


def shard(id, content, **kwargs):
    return {"id": id, "content": content, **kwargs}


def test_importance_breaks_relevance_ties_and_replay_is_deterministic():
    rows = [shard(1, "alpha", utility_score=1), shard(2, "alpha", utility_score=9)]
    first = graph_context_packet("alpha", rows)
    second = graph_context_packet("alpha", list(reversed(rows)))
    assert first == second
    assert first['content_payload'][0]['id'] == 'local:0:2'
    assert len(first['provenance_chain'][0]['content_hash']) == 71


def test_dependency_closure_atomic_and_does_not_mutate_durable_inputs():
    rows = [shard(1, "alpha", dependencies=[{"id": 2}]), shard(2, "prerequisite")]
    original = copy.deepcopy(rows)
    packet = graph_context_packet("alpha", rows)
    assert [x['id'] for x in packet['content_payload']] == ['local:0:2', 'local:0:1']
    assert rows == original
    assert packet['metrics']['dependencies'] == 1


def test_missing_dependency_rejects_root_with_provenance_decision():
    packet = graph_context_packet("alpha", [shard(1, "alpha", dependencies=[{"id": 99}])])
    assert packet['content_payload'] == []
    assert packet['decisions'][0]['outcome'] == 'missing_dependency'


def test_budget_never_truncates_dependency_or_unicode_source():
    rows = [shard(1, "alpha" * 100, dependencies=[{"id": 2}]), shard(2, "😀" * 100)]
    packet = graph_context_packet("alpha", rows, token_budget=100)
    assert packet['content_payload'] == []
    assert packet['metrics']['tokens_consumed'] <= 100


def test_cycle_terminates_and_expansion_ceiling_is_enforced():
    rows = [shard(1, "alpha", dependencies=[{"id": 2}]),
            shard(2, "support", dependencies=[{"id": 1}])]
    assert len(graph_context_packet("alpha", rows)['content_payload']) == 2
    denied = graph_context_packet("alpha", rows, max_dependencies=0)
    assert denied['content_payload'] == []


def test_sufficiency_stops_before_expanded_stage():
    packet = graph_context_packet("alpha", [shard(1, "alpha")],
                                  [shard(2, "alpha", importance=100)])
    assert len(packet['decisions']) == 1
    assert packet['decisions'][0]['stage'] == 'narrow'


def test_expansion_fills_query_coverage_without_irrelevant_importance():
    packet = graph_context_packet("alpha beta", [shard(1, "alpha")],
                                  [shard(2, "beta"), shard(3, "noise", importance=1e9)])
    assert packet['metrics']['query_coverage'] == 1
    assert [x['id'] for x in packet['content_payload']] == ['local:0:1', 'local:0:2']


def test_registered_search_uses_projection_and_retains_legacy_contract(monkeypatch):
    from nougen_shards import mcp
    from nougen_shards import federation
    calls = []

    def retrieve(query, limit):
        calls.append(limit)
        return [shard(1, "alpha")]

    monkeypatch.setattr(federation, 'federated_retrieve', retrieve)
    legacy = json.loads(mcp.search_shards('alpha', limit=2))
    packet = json.loads(mcp.search_shards('alpha', limit=2, context_budget=500))
    assert legacy['count'] == 1
    assert packet['policy_version'] == 'graph-context-v1'
    assert calls == [2, 8]


def test_database_qualified_dependency_identity_prevents_numeric_collision():
    rows = [shard(1, 'alpha', _db_index=2, dependencies=[{'id': 2}]),
            shard(2, 'wrong prerequisite', _db_index=1)]
    assert graph_context_packet('alpha', rows)['content_payload'] == []


def test_registered_search_resolves_local_dependency_from_durable_store(monkeypatch):
    from nougen_shards import mcp, federation, core
    monkeypatch.setattr(federation, 'federated_retrieve',
                        lambda *args, **kwargs: [shard(1, 'alpha', _db_index=2,
                                                       dependencies=[{'id': 9}])])
    calls = []

    def lookup(id, db):
        calls.append((id, db))
        return shard(id, 'durable prerequisite')

    monkeypatch.setattr(core, 'get_shard_by_id', lookup)
    packet = json.loads(mcp.search_shards('alpha', context_budget=1000))
    assert calls == [(9, 2)]
    assert [x['id'] for x in packet['content_payload']] == ['local:2:9', 'local:2:1']
