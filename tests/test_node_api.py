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


def test_hud_placeholder_serves_root_when_hud_locked():
    # On a network-exposed host with no HUD creds, app.py registers this
    # placeholder instead of mounting Gradio — root must explain itself
    # (200 + pointers) rather than fall through to a bare 404.
    from fastapi import FastAPI
    locked_app = FastAPI()
    node._register_hud_placeholder(locked_app)
    r = TestClient(locked_app).get("/")
    assert r.status_code == 200
    assert "NouGenShards" in r.text
    assert "/health" in r.text
    assert "NGS_HUD_USER" in r.text


def test_capture_search_roundtrip(client):
    r = client.post("/capture", json={
        "title": "Cloud automation shard",
        "content": "This shard proves the cloud capture endpoint works end to end.",
    }, headers=AUTH)
    assert r.status_code == 200 and r.json()["captured"] is True

    r = client.post("/search", json={"query": "automation", "limit": 5}, headers=AUTH)
    assert r.status_code == 200
    assert any(h.get("title") == "Cloud automation shard" for h in r.json())


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
