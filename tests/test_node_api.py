"""Functional tests for the Space node's REST API (app.py).

Boots the FastAPI app against a throwaway vault and exercises the full
auth + data surface: deny-by-default, capture->search round trip, JSON-clean
export, dedup-aware bulk ingest. Skipped when the node's web stack (fastapi/
gradio) isn't installed - CI installs the full package so it runs there.
"""
import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")

TEST_TOKEN = "test-node-token"

# app.py reads NGS_NODE_TOKEN and the vault location at import time, so the
# environment must be prepared before the module is first imported.
_tmp = tempfile.mkdtemp(prefix="ngs_node_api_")
os.environ["NGS_NODE_TOKEN"] = TEST_TOKEN
os.environ["NOUGEN_HOME"] = _tmp
os.environ["NOUGEN_VAULT_DIR"] = os.path.join(_tmp, ".vault")

from fastapi.testclient import TestClient  # noqa: E402

import app as node  # noqa: E402
import nougen_shards.core as core  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # Point the substrate at a fresh per-test vault.
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(core, "get_db_path",
                        lambda index: tmp_path / f"node_api_{index}.db")
    monkeypatch.setattr(node, "NODE_TOKEN", TEST_TOKEN)
    core.init_db(1)
    return TestClient(node.app)


AUTH = {"X-NGS-Token": TEST_TOKEN}


def test_health_is_open_and_reports_readiness(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ignited"
    assert body["node_token_configured"] is True
    assert isinstance(body["total_shards"], int)
    assert isinstance(body["warnings"], list)
    # HUD creds aren't set in tests -> not ready for a public flip.
    assert body["hud_auth_configured"] is False
    assert body["public_ready"] is False


def test_data_endpoints_deny_without_token(client):
    assert client.post("/search", json={"query": "x"}).status_code == 401
    assert client.get("/sync/pull").status_code == 401
    assert client.post("/capture", json={"title": "t", "content": "c"}).status_code == 401
    assert client.post("/search", json={"query": "x"},
                       headers={"X-NGS-Token": "wrong"}).status_code == 401


def test_deny_by_default_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr(node, "NODE_TOKEN", None)
    assert client.post("/search", json={"query": "x"}, headers=AUTH).status_code == 503


def test_capture_search_roundtrip(client):
    r = client.post("/capture", json={
        "title": "Cloud automation shard",
        "content": "This shard proves the cloud capture endpoint works end to end.",
    }, headers=AUTH)
    assert r.status_code == 200 and r.json()["captured"] is True

    r = client.post("/search", json={"query": "automation", "limit": 5}, headers=AUTH)
    assert r.status_code == 200
    assert any(h.get("title") == "Cloud automation shard" for h in r.json())


def test_search_degrades_instead_of_500(client, monkeypatch):
    """A crash in the full retrieval stack must not 500 the endpoint - federated
    callers read any non-200 as 'node down' and drop the relay. It must fall back
    to keyword-only, and to [] if that fails too."""
    def boom(*a, **k):
        raise RuntimeError("vector lane exploded")

    # Full retrieve blows up; keyword fallback still answers -> 200, not 500.
    monkeypatch.setattr(core, "retrieve", boom)
    r = client.post("/search", json={"query": "anything", "limit": 3}, headers=AUTH)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # Both lanes blow up -> still 200 with an empty list, never an exception.
    monkeypatch.setattr(core, "_keyword_retrieve", boom)
    r = client.post("/search", json={"query": "anything", "limit": 3}, headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


def test_pull_and_dedup_aware_push(client):
    client.post("/capture", json={"title": "Seed", "content": "Seed content for pull."},
                headers=AUTH)

    r = client.get("/sync/pull", headers=AUTH)
    assert r.status_code == 200
    exported = r.json()
    assert len(exported) == 1  # and JSON-serializable end to end

    # Re-pushing the export dedups; a new shard ingests; junk is skipped.
    shards = exported + [
        {"title": "Second shard", "content": "Bulk pushed shard content.", "tags": '["a","b"]'},
        {"title": "", "content": "missing title -> skipped"},
    ]
    r = client.post("/sync/push", json={"shards": shards}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["count"] == 1
    assert body["skipped"] == 2


def test_sync_push_preserves_original_timestamp(client):
    """Bulk ingest must stamp a shard at its true era, like /capture does.

    /sync/push forwarded event_type, tags, embedding, domain_key and
    density_score to capture() but not original_timestamp, so every bulk-pushed
    shard was re-dated to ingest time. The damage is permanent rather than
    cosmetic: capture() dedups on a content hash, so a corrected re-push is a
    silent no-op and the true era cannot be recovered. Verified against a live
    node before the fix -- a shard sent stamped 2020-01-01 came back stamped
    at push time.
    """
    r = client.post("/sync/push", json={"shards": [{
        "title": "Era-true bulk shard",
        "content": "Pushed in bulk, but it happened in 2020.",
        "original_timestamp": "2020-01-01T00:00:00Z",
    }]}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["count"] == 1

    row = client.get("/sync/pull", headers=AUTH).json()[0]
    assert row["timestamp"].startswith("2020-01-01"), (
        f"bulk push must not re-date the shard to ingest time, got {row['timestamp']}")


def test_sync_pull_push_round_trip_keeps_era(client):
    """pull -> push must not flatten history to the migration date.

    Exported rows carry their date under `timestamp`, not `original_timestamp`,
    so a round trip through the export format is the realistic migration path
    and the one most likely to silently re-date an entire vault.
    """
    client.post("/capture", json={
        "title": "Old memory", "content": "Captured long ago.",
        "original_timestamp": "2021-06-15T08:30:00Z",
    }, headers=AUTH)
    exported = client.get("/sync/pull", headers=AUTH).json()
    assert exported[0]["timestamp"].startswith("2021-06-15")

    # Same content dedups, so re-push a distinct body carrying the exported date.
    replay = dict(exported[0])
    replay["content"] = "Captured long ago, replayed to a sibling node."
    r = client.post("/sync/push", json={"shards": [replay]}, headers=AUTH)
    assert r.status_code == 200 and r.json()["count"] == 1

    dates = sorted(row["timestamp"] for row in
                   client.get("/sync/pull", headers=AUTH).json())
    assert all(d.startswith("2021-06-15") for d in dates), (
        f"round trip must preserve the era on both copies, got {dates}")
