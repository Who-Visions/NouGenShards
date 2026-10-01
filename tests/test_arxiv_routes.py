"""Test registration and exposure of the 5 canonical arXiv tools on node_mcp and FastAPI."""
import os
import sys
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from fastapi.testclient import TestClient
import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app.app)


def test_arxiv_openapi_routes_exposed(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    paths = schema.get("paths", {})
    expected = [
        "/arxiv/capabilities",
        "/arxiv/radar",
        "/arxiv/lab-watch",
        "/arxiv/paper",
        "/arxiv/morph-gate",
    ]
    for p in expected:
        assert p in paths, f"Route {p} must be present in OpenAPI schema"


def test_arxiv_capabilities_endpoint(client):
    resp = client.get("/arxiv/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "capabilities" in data
    cap_names = [c["name"] for c in data["capabilities"]]
    assert "arxiv_radar" in cap_names
    assert "arxiv_lab_watch" in cap_names
    assert "arxiv_paper" in cap_names
    assert "morph_gate" in cap_names


def test_arxiv_radar_preview_endpoint(client):
    resp = client.post("/arxiv/radar", json={"channels": ["cs"], "mode": "preview", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("provenance", {}).get("mode") == "preview"
    assert "lanes" in data


def test_arxiv_node_mcp_tools_registered():
    tools = [t.name for t in app.node_mcp._tool_manager.list_tools()]
    expected = [
        "arxiv_capabilities",
        "arxiv_radar",
        "arxiv_lab_watch",
        "arxiv_paper",
        "morph_gate",
    ]
    for tool_name in expected:
        assert tool_name in tools, f"Tool {tool_name} must be registered on node_mcp"
