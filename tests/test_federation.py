"""Federation resilience: local results must survive remote source failures."""
from nougen_shards import federation


LOCAL = [{"id": "local_1", "title": "Local Shard", "final_score": 0.9}]


def _patch_local(monkeypatch):
    """Stub local retrieval + keymaker so both remote lanes are exercised."""
    # Hermetic: a developer machine with NOUGEN_SECONDARY_VAULT_DIRS set adds a
    # real sibling-vault lane, and the stubbed retrieve() below answers for that
    # lane too -- so local_1 comes back once per configured store and the exact
    # result assertion turns into a function of the ambient environment.
    monkeypatch.delenv("NOUGEN_SECONDARY_VAULT_DIRS", raising=False)
    monkeypatch.setattr(federation.core, "retrieve", lambda *a, **k: list(LOCAL))
    monkeypatch.setattr(
        federation.core,
        "reciprocal_rank_fusion",
        lambda lists, k=60: [s for sub in lists for s in sub],
    )
    monkeypatch.setattr(federation.keymaker, "list_external_dbs",
                        lambda: [{"id": 1, "name": "ext"}])
    monkeypatch.setattr(federation.keymaker, "list_cloud_nodes",
                        lambda: [{"id": 1, "name": "cloud"}])


def test_external_failure_preserves_local(monkeypatch, caplog):
    _patch_local(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("external DB down")

    monkeypatch.setattr(federation, "query_external_dbs", boom)
    monkeypatch.setattr(federation, "query_cloud_shards", lambda *a, **k: [])

    results = federation.federated_retrieve("q", limit=5)
    assert any(r["id"] == "local_1" for r in results)


def test_cloud_failure_preserves_local(monkeypatch, caplog):
    _patch_local(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("cloud node unreachable")

    monkeypatch.setattr(federation, "query_external_dbs", lambda *a, **k: [])
    monkeypatch.setattr(federation, "query_cloud_shards", boom)

    results = federation.federated_retrieve("q", limit=5)
    assert any(r["id"] == "local_1" for r in results)


def test_both_remotes_fail_local_survives(monkeypatch):
    _patch_local(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("remote down")

    monkeypatch.setattr(federation, "query_external_dbs", boom)
    monkeypatch.setattr(federation, "query_cloud_shards", boom)

    results = federation.federated_retrieve("q", limit=5)
    assert [r["id"] for r in results] == ["local_1"]
