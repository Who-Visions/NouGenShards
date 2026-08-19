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
    """The invariant is what must NOT be on the wire, not the exact roster.

    An exact-set assertion here rotted twice in one day as legitimate memory
    tools landed (substrate_coverage, recall_window, shard_amend/retract/
    forget, vault_*). The security property is one-directional: the memory
    core must be present, and the stdio-only tools - remote code execution
    and container-filesystem recon - must never leak onto the network
    surface, no matter what else is added.
    """
    r = client.post("/mcp/", json=_rpc("tools/list"), headers=AUTH)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"recall_memory", "capture_experience",
            "mark_utility", "node_status"} <= names
    forbidden = {"execute_sandboxed_code", "run_brain_scan", "run_brain_import"}
    leaked = forbidden & names
    assert not leaked, f"stdio-only tools leaked onto the network surface: {leaked}"


def test_mcp_tool_surface_exact_roster_tripwire(client):
    """Exact roster, grouped by what each grant costs if the token leaks.

    This test is SUPPOSED to fail when someone widens the network surface -
    that is its whole job. It is deliberately separate from the invariant
    above so the two never share a fate: the invariant must never rot, and
    this tripwire is expected to need an argued-for update whenever the
    roster legitimately changes.

    Keeping them fused is what broke this file: the exact-set assertion went
    stale, the stale failure made the whole module easy to skip, and the
    one-directional security check got skipped along with it.
    """
    r = client.post("/mcp/", json=_rpc("tools/list"), headers=AUTH)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}

    read_only = {"recall_memory", "recall_window", "node_status", "vault_list",
                 "substrate_coverage"}
    additive = {"capture_experience", "mark_utility", "vault_put", "shard_amend"}
    destructive = {"shard_forget", "shard_retract"}
    expected = read_only | additive | destructive

    assert names == expected, (
        "network tool roster changed - argue for it, then update this set.\n"
        f"  added:   {sorted(names - expected)}\n"
        f"  removed: {sorted(expected - names)}"
    )


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


def test_mcp_401_explains_the_query_token_path():
    # A bare "Invalid node token." made the Claude connector UI report a
    # sign-in-service failure: it reads 401 on an MCP endpoint as "sign in
    # here", attempts OAuth dynamic client registration, and finds no metadata.
    # The 401 must name the fix the node actually supports.
    import app as node_app
    detail = node_app._BAD_TOKEN_DETAIL
    assert "?token=" in detail
    assert "X-NGS-Token" in detail


def test_mcp_401_points_at_a_reachable_authorization_server(client):
    """The /mcp 401 must hand back an RFC 9728 pointer, not a bare Bearer.

    History worth keeping, because this test asserted the exact opposite for
    months while sitting unrunnable behind merge markers: the original rule was
    "this node has no OAuth layer, so it must never advertise one." That was
    true then. mcp_oauth now mounts /.well-known/oauth-protected-resource and
    /.well-known/oauth-authorization-server, so the node DOES have one, and
    _TokenGatedMCP._reject rightly emits the pointer (RFC 9728 s5.1). Without
    it the connector probes on its own, 404s, and reports "couldn't register
    with the sign-in service".

    The danger the old rule was groping at is real but narrower: a BARE
    `Bearer` with no resource_metadata, or a pointer to somewhere the client
    cannot reach. So that is what this pins - the pointer exists, is
    same-origin, and actually answers.
    """
    r = client.post("/mcp/", json=_rpc("tools/list"), headers=MCP_HEADERS)
    assert r.status_code == 401

    header = next((v for k, v in r.headers.items()
                   if k.lower() == "www-authenticate"), None)
    assert header is not None, "no WWW-Authenticate: connector cannot discover auth"

    # A bare "Bearer" is the failure mode - it starts a blind hunt.
    assert "resource_metadata=" in header, f"bare challenge, no pointer: {header!r}"

    url = header.split('resource_metadata="', 1)[1].split('"', 1)[0]
    assert url.endswith("/.well-known/oauth-protected-resource"), url

    # The pointer must not dangle: same-origin path has to actually answer.
    meta = client.get("/.well-known/oauth-protected-resource")
    assert meta.status_code == 200, (
        f"WWW-Authenticate points at {url} but it returns {meta.status_code}")


def test_rest_401_still_withholds_the_oauth_challenge():
    """The REST token gate is NOT the /mcp mount and must stay bare.

    Only the /mcp mount speaks OAuth. The REST endpoints want a token and
    nothing else, so their 401 deliberately carries no challenge - see the
    _BAD_TOKEN_DETAIL comment in app.py. Pinned separately so a future change
    to the /mcp policy above cannot quietly drag the REST path along with it.
    """
    import app as node_app
    detail = node_app._BAD_TOKEN_DETAIL
    assert "OAuth" not in detail and "oauth" not in detail
