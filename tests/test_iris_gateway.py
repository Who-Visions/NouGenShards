"""Integration & regression tests for IRIS and roster agent gateway endpoints."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

import app
from nougen_shards import agents


TEST_TOKEN = "test-iris-node-token"
AUTH = {"X-NGS-Token": TEST_TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NGS_NODE_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(app, "NODE_TOKEN", TEST_TOKEN)
    return TestClient(app.app)


def test_node_mcp_has_iris_and_roster_tools():
    """Verify that node_mcp registers ask_iris, ask_agent, and list_agents."""
    tools = [t.name for t in app.node_mcp._tool_manager.list_tools()]
    assert "ask_iris" in tools
    assert "ask_agent" in tools
    assert "list_agents" in tools


def test_list_agents_mcp_tool():
    """Verify list_agents tool returns the roster."""
    roster_str = app.list_agents.fn()
    assert "Iris" in roster_str
    assert "Griot" in roster_str
    assert "Kaedra" in roster_str


def test_ask_iris_mcp_tool():
    """Verify ask_iris tool delegates to agents.run_agent."""
    with patch("nougen_shards.agents.run_agent", return_value="Iris verified answer.") as mock_run:
        ans = app.ask_iris.fn(question="Is this verified?")
        assert ans == "Iris verified answer."
        mock_run.assert_called_once_with("Iris", "Is this verified?", model=None)


def test_ask_agent_mcp_tool():
    """Verify ask_agent tool delegates to agents.run_agent."""
    with patch("nougen_shards.agents.run_agent", return_value="Griot rules consolidated.") as mock_run:
        ans = app.ask_agent.fn(name="Griot", prompt="Synthesize rules", model="griot:e2b")
        assert ans == "Griot rules consolidated."
        mock_run.assert_called_once_with("Griot", "Synthesize rules", model="griot:e2b")


@pytest.mark.asyncio
async def test_ask_iris_mcp_async():
    """Verify ask_iris tool works when awaited over the async MCP wire path."""
    with patch("nougen_shards.agents.run_agent", return_value="Iris async answer."):
        ans = await app.ask_iris(question="Async check")
        assert ans == "Iris async answer."


def test_iris_ask_rest_endpoint(client):
    """Verify POST /iris/ask endpoint returns structured response."""
    with patch("nougen_shards.agents.run_agent", return_value="Iris verified evidence."):
        resp = client.post("/iris/ask", json={"question": "Verify hypothesis"}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] == "Iris"
        assert data["answer"] == "Iris verified evidence."
        assert data["model"] == agents.ROSTER["Iris"].default_model


def test_agents_ask_rest_endpoint(client):
    """Verify POST /agents/ask endpoint returns structured response."""
    with patch("nougen_shards.agents.run_agent", return_value="Kaedra tensor math verified."):
        resp = client.post("/agents/ask", json={"name": "Kaedra", "prompt": "Explain softmax"}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] == "Kaedra"
        assert data["answer"] == "Kaedra tensor math verified."
        assert data["model"] == agents.ROSTER["Kaedra"].default_model


def test_agents_roster_rest_endpoint(client):
    """Verify GET /agents/roster endpoint returns full roster."""
    resp = client.get("/agents/roster", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "roster_text" in data
    assert "agents" in data
    agent_names = {a["name"] for a in data["agents"]}
    assert "Iris" in agent_names
    assert "Kaedra" in agent_names
    assert "Griot" in agent_names
