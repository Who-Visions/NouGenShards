"""/search fast mode: local keyword index only, remote lanes skipped and reported, no vector/embedding work."""
from nougen_shards import core, federation


def test_core_retrieve_fast_local_uses_only_the_keyword_index(monkeypatch):
    seen = {}

    def kw(query, limit, emb, domain, include_research=False):
        seen["args"] = (query, limit, emb, domain)
        return [{"id": 1, "title": "t", "content": "c"}, {"id": 2, "title": "u", "content": "d"}]

    def boom(*a, **k):
        raise AssertionError("fast path must not touch the vector lane, embeddings or schema sweep")
    monkeypatch.setattr(core, "_keyword_retrieve", kw)
    monkeypatch.setattr(core, "_vector_retrieve", boom)
    monkeypatch.setattr(core, "_embed_query", boom)
    monkeypatch.setattr(core, "init_db", boom)
    token = core.FAST_LOCAL.set(True)
    try:
        out = core.retrieve("memory latency", limit=1)
    finally:
        core.FAST_LOCAL.reset(token)
    assert [r["id"] for r in out] == [1] and seen["args"] == ("memory latency", 1, None, "*")


def test_federated_retrieve_fast_local_skips_remote_lanes_and_reports_it(monkeypatch):
    monkeypatch.setattr(core, "retrieve", lambda *a, **k: [{"id": 9, "title": "t", "content": "c"}])
    rep = {}
    token = core.FAST_LOCAL.set(True)
    try:
        out = federation.federated_retrieve("memory latency", limit=3, sweep_report=rep)
    finally:
        core.FAST_LOCAL.reset(token)
    assert out and rep["fast_local"] is True and rep["lanes_skipped"] == ["external", "cloud", "vaults"]
    assert not rep.get("lanes_timed_out")            # skipped is not failed: no deadline trailer


def test_fast_local_defaults_off():
    assert core.FAST_LOCAL.get() is False
