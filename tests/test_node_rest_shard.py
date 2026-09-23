import pytest
from fastapi.testclient import TestClient
import os
import tempfile

TEST_TOKEN = "test-node-token"
_tmp = tempfile.mkdtemp(prefix="ngs_node_rest_")
os.environ["NGS_NODE_TOKEN"] = TEST_TOKEN
os.environ["NOUGEN_HOME"] = _tmp
os.environ["NOUGEN_VAULT_DIR"] = os.path.join(_tmp, ".vault")

import app as node
import nougen_shards.core as core


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(core, "get_db_path", lambda index: tmp_path / f"node_rest_{index}.db")
    monkeypatch.setattr(node, "NODE_TOKEN", TEST_TOKEN)
    core.init_db(1)
    return TestClient(node.app)


AUTH = {"X-NGS-Token": TEST_TOKEN}


def test_get_shard_rest_endpoint_returns_404_when_absent(client):
    res = client.get("/shard/99999", headers=AUTH)
    assert res.status_code == 404


def test_get_shard_rest_endpoint_returns_captured_shard(client):
    cap_res = client.post(
        "/capture",
        json={
            "event_type": "KNOWLEDGE",
            "title": "Rest Endpoint Shard Test",
            "content": "Body content for direct REST ID verification test.",
            "tags": ["test_rest", "canary"],
        },
        headers=AUTH,
    )
    assert cap_res.status_code == 200
    data = cap_res.json()
    assert data["captured"] is True
    shard_id = data["shard_id"]
    db_idx = data["db_index"]

    get_res = client.get(f"/shard/{shard_id}", headers=AUTH)
    assert get_res.status_code == 200
    shard_data = get_res.json()
    assert shard_data["title"] == "Rest Endpoint Shard Test"
    assert shard_data["content"] == "Body content for direct REST ID verification test."
    assert shard_data["_db_index"] == db_idx
    assert "source_node" in shard_data
    assert "content_hash" in shard_data
    correct_hash = shard_data["content_hash"]

    # Match verification
    get_res_match = client.get(f"/shard/{shard_id}?content_hash={correct_hash}", headers=AUTH)
    assert get_res_match.status_code == 200

    # Mismatch verification (409 Conflict)
    get_res_mismatch = client.get(f"/shard/{shard_id}?content_hash=badhash123", headers=AUTH)
    assert get_res_mismatch.status_code == 409

    get_res_plural = client.get(f"/shards/{shard_id}?db_index={db_idx}", headers=AUTH)
    assert get_res_plural.status_code == 200
    assert get_res_plural.json()["id"] == shard_id


def test_health_write_path_probe(client):
    res = client.get("/health", headers=AUTH)
    assert res.status_code == 200
    data = res.json()
    assert "write_path" in data
    assert data["write_path"]["ok"] is True
    assert data["write_path"]["checked"] > 0
