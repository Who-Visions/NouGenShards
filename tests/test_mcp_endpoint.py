"""Functional tests for the remote MCP endpoint mounted at /mcp (app.py).

Drives real JSON-RPC over streamable HTTP through the token gate: auth
denials (header and query-param forms), initialize, tools/list, and a
capture -> recall round trip through the MCP tool surface. Skipped when the
node's web stack isn't installed - CI installs the full package so it runs
there.
"""
import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")
pytest.importorskip("mcp")

TEST_TOKEN = "test-mcp-token"

# app.py reads NGS_NODE_TOKEN and the vault location at import time, so the
# environment must be prepared before the module is first imported.
_tmp = tempfile.mkdtemp(prefix="ngs_mcp_endpoint_")
os.environ["NGS_NODE_TOKEN"] = TEST_TOKEN
os.environ["NOUGEN_HOME"] = _tmp
os.environ["NOUGEN_VAULT_DIR"] = os.path.join(_tmp, ".vault")

from fastapi.testclient import TestClient  # noqa: E402

import app as node  # noqa: E402
import nougen_shards.core as core  # noqa: E402

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
AUTH = {"X-NGS-Token": TEST_TOKEN, **MCP_HEADERS}


def _rpc(method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


# The streamable-HTTP session manager's run() is once-per-process, so all
# tests share one lifespan-entered client (module scope) instead of the
# per-test clients the REST suite uses.
@pytest.fixture(scope="module")
def client():
    from pathlib import Path
    vault = Path(tempfile.mkdtemp(prefix="ngs_mcp_vault_"))
    saved = (core.GLOBAL_DIR, core.get_db_path, node.NODE_TOKEN)
    core.GLOBAL_DIR = vault
    core.get_db_path = lambda index: vault / f"mcp_{index}.db"
    node.NODE_TOKEN = TEST_TOKEN
    core.init_db(1)
    try:
        with TestClient(node.app) as c:  # context manager runs the lifespan
            yield c
    finally:
        core.GLOBAL_DIR, core.get_db_path, node.NODE_TOKEN = saved


# --- auth gate ---------------------------------------------------------------

def test_mcp_denies_without_token(client):
    r = client.post("/mcp/", json=_rpc("tools/list"), headers=MCP_HEADERS)
    assert r.status_code == 401

    r = client.post("/mcp/", json=_rpc("tools/list"),
                    headers={**MCP_HEADERS, "X-NGS-Token": "wrong"})
    assert r.status_code == 401


def test_mcp_denies_when_unconfigured(client):
    saved = node.NODE_TOKEN
    node.NODE_TOKEN = None
    try:
        r = client.post("/mcp/", json=_rpc("tools/list"), headers=AUTH)
        assert r.status_code == 503
    finally:
        node.NODE_TOKEN = saved


def test_mcp_accepts_query_param_token(client):
    # The Claude app's connectors cannot set custom headers - the ?token=
    # query form is the mobile path and must be equivalent to the header.
    r = client.post(f"/mcp/?token={TEST_TOKEN}",
                    json=_rpc("tools/list"), headers=MCP_HEADERS)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert "recall_memory" in names

    r = client.post("/mcp/?token=wrong", json=_rpc("tools/list"),
                    headers=MCP_HEADERS)
    assert r.status_code == 401


# --- protocol ----------------------------------------------------------------

def test_mcp_initialize(client):
    r = client.post("/mcp/", headers=AUTH, json=_rpc("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    }))
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["serverInfo"]["name"] == "NouGenShards"


def test_mcp_tool_surface_excludes_code_execution(client):
    r = client.post("/mcp/", json=_rpc("tools/list"), headers=AUTH)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {"recall_memory", "capture_experience",
                     "mark_utility", "node_status"}
    # The stdio-only tools must never leak onto the network surface.
    assert "execute_sandboxed_code" not in names
    assert "run_brain_scan" not in names


# --- tools -------------------------------------------------------------------

def _call_tool(client, name, arguments, id_=9):
    r = client.post("/mcp/", headers=AUTH, json=_rpc(
        "tools/call", {"name": name, "arguments": arguments}, id_=id_))
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError"), result
    return result


def test_mcp_capture_then_recall_roundtrip(client):
    _call_tool(client, "capture_experience", {
        "title": "Remote MCP shard",
        "content": "Captured over the streamable HTTP connector end to end.",
    })
    result = _call_tool(client, "recall_memory",
                        {"query": "streamable connector", "limit": 5})
    text = "".join(c.get("text", "") for c in result["content"])
    assert "Remote MCP shard" in text


def test_mcp_node_status(client):
    result = _call_tool(client, "node_status", {})
    text = "".join(c.get("text", "") for c in result["content"])
    assert "ignited" in text
