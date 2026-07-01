"""federated_retrieve must auto-embed queries when the caller passes None.

The MCP recall path (the lane agents use) never computed a query embedding,
so the vector lane / ANN index / semantic scoring were dead in production.
"""
import pytest

import nougen_shards.federation as federation


@pytest.fixture(autouse=True)
def reset_embed_client():
    federation._EMBED_CLIENT = None
    yield
    federation._EMBED_CLIENT = None


def test_auto_embed_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(federation, "AUTO_EMBED", False)
    assert federation._auto_query_embedding("anything") is None


def test_dead_client_is_probed_once_and_cached(monkeypatch):
    probes = []

    class DeadClient:
        def __init__(self):
            probes.append(1)

        def is_alive(self):
            return False

    monkeypatch.setattr(federation, "AUTO_EMBED", True)
    import nougen_shards.models_client as mc
    monkeypatch.setattr(mc, "OllamaClient", DeadClient)
    assert federation._auto_query_embedding("q") is None
    assert federation._auto_query_embedding("q") is None
    assert len(probes) == 1, "dead endpoint must not be re-probed per query"


def test_live_client_embedding_is_used(monkeypatch):
    class LiveClient:
        def is_alive(self):
            return True

        def embed(self, model, text):
            return [0.1, 0.2, 0.3]

    monkeypatch.setattr(federation, "AUTO_EMBED", True)
    federation._EMBED_CLIENT = LiveClient()
    assert federation._auto_query_embedding("q") == [0.1, 0.2, 0.3]


def test_embed_failure_degrades_to_none(monkeypatch):
    class FlakyClient:
        def is_alive(self):
            return True

        def embed(self, model, text):
            raise OSError("socket down")

    monkeypatch.setattr(federation, "AUTO_EMBED", True)
    federation._EMBED_CLIENT = FlakyClient()
    assert federation._auto_query_embedding("q") is None


def test_federated_retrieve_wires_auto_embedding_through(monkeypatch):
    captured = {}

    def fake_retrieve(query, limit=3, query_embedding=None, domain_key=None):
        captured["embedding"] = query_embedding
        return []

    monkeypatch.setattr(federation.core, "retrieve", fake_retrieve)
    monkeypatch.setattr(federation.keymaker, "list_external_dbs", lambda: [])
    monkeypatch.setattr(federation.keymaker, "list_cloud_nodes", lambda: [])
    monkeypatch.setattr(federation, "_auto_query_embedding", lambda q: [1.0, 0.0])
    federation.federated_retrieve("test query", limit=2)
    assert captured["embedding"] == [1.0, 0.0]


def test_caller_embedding_is_not_overridden(monkeypatch):
    captured = {}

    def fake_retrieve(query, limit=3, query_embedding=None, domain_key=None):
        captured["embedding"] = query_embedding
        return []

    monkeypatch.setattr(federation.core, "retrieve", fake_retrieve)
    monkeypatch.setattr(federation.keymaker, "list_external_dbs", lambda: [])
    monkeypatch.setattr(federation.keymaker, "list_cloud_nodes", lambda: [])
    monkeypatch.setattr(federation, "_auto_query_embedding",
                        lambda q: pytest.fail("must not auto-embed when caller provided one"))
    federation.federated_retrieve("q", limit=1, query_embedding=[9.0])
    assert captured["embedding"] == [9.0]
