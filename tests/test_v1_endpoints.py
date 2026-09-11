from __future__ import annotations

import os
import json
import pytest
from fastapi.testclient import TestClient
from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_local_health_returns_vault_detail(client, monkeypatch):
    monkeypatch.setenv("NOUGEN_MACHINE_ID", "hyperion")
    monkeypatch.setenv("NOUGEN_VAULT_ID", "whoart")
    monkeypatch.setenv("NOUGEN_INSTANCE_ID", "hyperion-test-1")

    res = client.get("/v1/health/local")
    assert res.status_code == 200
    data = res.json()
    assert data["vault_id"] == "whoart"
    assert data["machine_id"] == "hyperion"
    assert data["instance_id"] == "hyperion-test-1"
    assert "db_count" in data
    assert "db_expected" in data
    assert "shard_count" in data


def test_v1_recall_local_loop_prevention(client, monkeypatch):
    import app as app_mod
    monkeypatch.setattr(app_mod, "NODE_TOKEN", "test-token-1234567890123456789012")
    monkeypatch.setenv("NGS_NODE_TOKEN", "test-token-1234567890123456789012")

    res = client.post(
        "/v1/recall",
        headers={
            "X-NGS-Token": "test-token-1234567890123456789012",
            "X-NouGen-Federated-Hop": "1",
        },
        json={"query": "test query", "limit": 3, "scope": "local"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["scope"] == "local"
    assert data["federation_fanout_count"] == 0
    assert "hits" in data
