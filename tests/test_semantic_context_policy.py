import json

import pytest

from nougen_shards.context_policy import assemble_context, canonical, evaluate_context


def row(id, content='alpha', **kw):
    return {'id': id, 'content': content, **kw}


def correction(old, new):
    return {'previous': f'local:0:{old}', 'current': f'local:0:{new}', 'provenance': 'owner correction'}


def ids(packet):
    return {r['id'] for layer in ('identity', 'global', 'recall') for r in packet['context'][layer]}


def test_budget_includes_unicode_structure_and_active_state():
    for budget in (64, 100, 300, 1000):
        packet = assemble_context('alpha', recall=[row(1, 'alpha😀' * 80)],
                                  active={'objective': 'repair'}, budget_bytes=budget)
        assert len(canonical(packet['context']).encode()) <= budget
        assert packet['metrics']['context_bytes'] <= budget


def test_supersession_chain_is_order_independent_and_history_unchanged():
    rows = [row(1), row(2), row(3)]
    before = json.dumps(rows)
    for corrections in ([correction(1, 2), correction(2, 3)], [correction(2, 3), correction(1, 2)]):
        p = assemble_context('alpha', recall=rows, required_handles=['local:0:1'], corrections=corrections)
        assert p['ready']
        assert ids(p) == {'local:0:3'}
    assert json.dumps(rows) == before


@pytest.mark.parametrize('corrections', [[correction(1, 2), correction(2, 1)],
                                        [correction(1, 2), correction(1, 3)], [correction(1, 9)]])
def test_invalid_lineage_fails_readiness(corrections):
    p = assemble_context('alpha', recall=[row(1), row(2), row(3)], corrections=corrections)
    assert not p['ready']
    assert 'local:0:1' not in ids(p)


def test_required_state_is_selected_even_without_query_overlap():
    p = assemble_context('alpha', recall=[row(1, 'do not spawn workers'), row(2)],
                         required_handles=['local:0:1'])
    assert p['ready']
    assert 'local:0:1' in ids(p)


def test_current_identity_retains_priority_without_query_overlap():
    p = assemble_context('alpha', identity=[row(1, 'old')], recall=[row(2, 'current rule')],
                         corrections=[correction(1, 2)])
    assert p['ready']
    assert p['context']['identity'][0]['id'] == 'local:0:2'


def test_required_dependency_cannot_be_silently_omitted():
    p = assemble_context('alpha', identity=[row(1, dependencies=[{'id': 9}])])
    assert not p['ready']
    assert not ids(p)


def test_feedback_does_not_claim_utilization_without_observation():
    p = assemble_context('alpha', recall=[row(1)], upstream_complete=False)
    assert p['metrics']['context_efficiency'] is None
    assert p['retrieval_complete'] is False
    feedback = evaluate_context(p, used_handles=['local:0:1'], critical_handles=['local:0:9'], task_success=False)
    assert feedback['critical_recall_misses'] == ['local:0:9']
    with pytest.raises(ValueError):
        evaluate_context(p, used_handles=['local:0:9'], critical_handles=[], task_success=True)


def test_append_only_session_state_and_correction_isolation(tmp_path, monkeypatch):
    from nougen_shards import nougen_context as ctx
    monkeypatch.setattr(ctx, 'SESSION_DB_PATH', str(tmp_path / 'state.db'))
    first = ctx.append_task_state('one', {'objective': 'first'}, provenance='owner')
    ctx.append_task_state('two', {'objective': 'other'}, provenance='owner')
    ctx.append_task_state('one', {'objective': 'current'}, provenance='owner')
    ctx.append_context_correction('one', 'local:0:1', 'local:0:2', provenance='owner')
    assert ctx.current_task_state('one')['state']['objective'] == 'current'
    assert ctx.current_task_state('two')['state']['objective'] == 'other'
    assert ctx.get_event(first['event_id'])['content'] == '{"objective":"first"}'
    assert len(ctx.context_corrections('one')) == 1
    assert ctx.context_corrections('two') == []


def test_session_consumer_uses_federation_and_preserves_incomplete(tmp_path, monkeypatch):
    from nougen_shards import nougen_context as ctx, federation
    monkeypatch.setattr(ctx, 'SESSION_DB_PATH', str(tmp_path / 'state.db'))
    ctx.append_task_state('one', {'objective': 'repair'}, provenance='owner')
    calls = []
    class Partial(list):
        complete = False
    def retrieve(query, limit):
        calls.append((query, limit))
        return Partial([row(1)])
    monkeypatch.setattr(federation, 'federated_retrieve', retrieve)
    p = ctx.assemble_session_context('one', 'alpha')
    assert calls == [('alpha', 20)]
    assert p['retrieval_complete'] is False
    assert p['context']['active'] == [{'objective': 'repair'}]
    assert 'local:0:1' in ids(p)
    ctx.assemble_session_context('one', 'alpha', '{"recall":[]}')
    assert len(calls) == 1


def test_selected_records_retain_content_provenance():
    p = assemble_context('alpha', recall=[row(1, source_uri='shard:1', timestamp='2026-10-07')])
    provenance = p['provenance_chain'][0]
    assert provenance['id'] == 'local:0:1'
    assert len(provenance['content_hash']) == 71
    assert provenance['source_uri'] == 'shard:1'
    assert provenance['timestamp'] == '2026-10-07'


def test_shared_required_dependency_is_not_injected_twice():
    p = assemble_context('alpha', identity=[row(9, 'required')],
                         recall=[row(1, dependencies=[{'id': 9}])])
    injected = [r['id'] for layer in ('identity', 'global', 'recall') for r in p['context'][layer]]
    assert injected.count('local:0:9') == 1
    assert set(injected) == {'local:0:1', 'local:0:9'}


def test_empty_partial_retrieval_is_not_ready(tmp_path, monkeypatch):
    from nougen_shards import nougen_context as ctx, federation
    monkeypatch.setattr(ctx, 'SESSION_DB_PATH', str(tmp_path / 'state.db'))
    class Partial(list):
        complete = False
    monkeypatch.setattr(federation, 'federated_retrieve', lambda *a, **kw: Partial())
    p = ctx.assemble_session_context('one', 'alpha')
    assert not p['ready']
    assert p['readiness_reasons'] == ['incomplete_retrieval_without_candidates']
