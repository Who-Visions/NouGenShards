"""/v1 routes after the v1 federation package was removed (2026-06-10, d2c5082).

Before this fix both routes imported nougen_shards.federation.config at the top of
the handler, so every call - including scope=local recall, which never federates -
raised ModuleNotFoundError and answered 500. Found by leakwatch load testing.
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")
from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as node  # noqa: E402

TOKEN = "v1-routes-token"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(node, "NODE_TOKEN", TOKEN)
    return TestClient(node.app, raise_server_exceptions=False)


H = {"X-NGS-Token": TOKEN}


def test_local_recall_works_again(client, monkeypatch):
    monkeypatch.setattr(node, "search", lambda req, resp, tenant: [{"id": 1, "title": req.query}])
    r = client.post("/v1/recall", json={"query": "march", "limit": 3, "scope": "local"}, headers=H)
    assert r.status_code == 200
    assert r.json()["scope"] == "local" and r.json()["hits"][0]["title"] == "march"


def test_federated_recall_and_fleet_health_say_501_not_500(client):
    r = client.post("/v1/recall", json={"query": "march", "scope": "federated"}, headers=H)
    assert r.status_code == 501 and r.json()["error"] == "federation_v1_unavailable"
    r = client.get("/v1/health/fleet", headers=H)
    assert r.status_code == 501 and "/search" in r.json()["detail"]
