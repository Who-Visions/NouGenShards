"""OAuth 2.1 connector flow: discovery -> registration -> PKCE -> Bearer.

Guards the failure that motivated the module: a bare 401 with no
WWW-Authenticate sends MCP clients probing for authorization-server metadata
that does not exist, and they report it as "couldn't register with the
sign-in service" rather than as an auth failure.
"""

import base64
import hashlib
import os
import secrets

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")
pytest.importorskip("mcp")

from fastapi.testclient import TestClient  # noqa: E402

import app as node  # noqa: E402

NODE_TOKEN = "unit-test-node-token"
PUBLIC_URL = "https://shards.example.test"
REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture(scope="module")
def client():
    """Client for the OAuth routes.

    Deliberately NOT lifespan-entered: StreamableHTTPSessionManager.run() is
    once-per-process and test_mcp_endpoint.py already claims it, so entering
    it here would raise in a full-suite run. None of the OAuth endpoints need
    the session manager, and the token gate is exercised separately against a
    stub inner app in `gated` below.
    """
    os.environ["NGS_PUBLIC_URL"] = PUBLIC_URL
    saved = node.NODE_TOKEN
    node.NODE_TOKEN = NODE_TOKEN
    try:
        yield TestClient(node.app)
    finally:
        node.NODE_TOKEN = saved
        os.environ.pop("NGS_PUBLIC_URL", None)


@pytest.fixture(scope="module")
def gated():
    """The token gate wrapped around a stub inner app.

    Lets the auth decision be tested on its own - a 200 here means the gate
    passed the request through, without dragging in the real MCP transport.
    """
    async def _stub(scope, receive, send):
        body = b'{"ok":true}'
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    saved = node.NODE_TOKEN
    node.NODE_TOKEN = NODE_TOKEN
    os.environ["NGS_PUBLIC_URL"] = PUBLIC_URL
    try:
        yield TestClient(node._TokenGatedMCP(_stub))
    finally:
        node.NODE_TOKEN = saved
        os.environ.pop("NGS_PUBLIC_URL", None)


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    return verifier, challenge


def _register(client, redirect_uri=REDIRECT_URI):
    r = client.post(
        "/register",
        json={"redirect_uris": [redirect_uri], "client_name": "Claude"},
    )
    assert r.status_code == 201
    return r.json()["client_id"]


def _authorize(client, client_id, challenge, token=NODE_TOKEN):
    return client.post(
        "/authorize",
        data={
            "node_token": token,
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "state": "opaque-state",
            "code_challenge": challenge,
        },
        follow_redirects=False,
    )


def test_unauthenticated_mcp_points_at_resource_metadata(gated):
    """The regression this module exists for: without WWW-Authenticate the
    client cannot find the authorization server and reports a registration
    failure instead of an auth failure."""
    r = gated.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r.status_code == 401
    header = r.headers.get("www-authenticate", "")
    assert header.startswith("Bearer ")
    assert f'resource_metadata="{PUBLIC_URL}/.well-known/oauth-protected-resource"' in header


def test_discovery_documents_are_served(client):
    pr = client.get("/.well-known/oauth-protected-resource")
    assert pr.status_code == 200
    assert pr.json()["authorization_servers"] == [PUBLIC_URL]
    assert pr.json()["resource"] == f"{PUBLIC_URL}/mcp"

    # Clients derive the suffixed form from the resource path; both must work.
    assert client.get("/.well-known/oauth-protected-resource/mcp").status_code == 200

    asm = client.get("/.well-known/oauth-authorization-server")
    assert asm.status_code == 200
    body = asm.json()
    assert body["registration_endpoint"] == f"{PUBLIC_URL}/register"
    assert body["code_challenge_methods_supported"] == ["S256"]


def test_registration_rejects_cleartext_redirect(client):
    r = client.post(
        "/register",
        json={"redirect_uris": ["http://evil.example.com/cb"], "client_name": "x"},
    )
    assert r.status_code == 400


def test_registration_allows_loopback(client):
    r = client.post(
        "/register",
        json={"redirect_uris": ["http://127.0.0.1:8080/cb"], "client_name": "inspector"},
    )
    assert r.status_code == 201


def test_authorize_rejects_unregistered_redirect(client):
    client_id = _register(client)
    _, challenge = _pkce()
    r = client.post(
        "/authorize",
        data={
            "node_token": NODE_TOKEN,
            "client_id": client_id,
            "redirect_uri": "https://attacker.example/cb",
            "state": "s",
            "code_challenge": challenge,
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_authorize_rejects_wrong_node_token(client):
    client_id = _register(client)
    _, challenge = _pkce()
    r = _authorize(client, client_id, challenge, token="not-the-token")
    assert r.status_code == 401
    # Re-renders the form rather than redirecting, so the flow can be retried.
    assert "node_token" in r.text


def test_full_flow_issues_token_that_opens_mcp(client, gated):
    client_id = _register(client)
    verifier, challenge = _pkce()

    redirect = _authorize(client, client_id, challenge)
    assert redirect.status_code == 303
    location = redirect.headers["location"]
    assert "state=opaque-state" in location
    code = location.split("code=")[1].split("&")[0]

    tok = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert tok.status_code == 200
    assert tok.json()["token_type"] == "Bearer"
    access_token = tok.json()["access_token"]

    # The issued token must open the same gate the shared secret opens.
    r = gated.post(
        "/",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_code_is_single_use(client):
    client_id = _register(client)
    verifier, challenge = _pkce()
    location = _authorize(client, client_id, challenge).headers["location"]
    code = location.split("code=")[1].split("&")[0]
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    assert client.post("/token", data=payload).status_code == 200
    replay = client.post("/token", data=payload)
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"


def test_wrong_pkce_verifier_is_rejected(client):
    client_id = _register(client)
    _, challenge = _pkce()
    location = _authorize(client, client_id, challenge).headers["location"]
    code = location.split("code=")[1].split("&")[0]
    r = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": secrets.token_urlsafe(48),
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


def test_shared_secret_paths_still_work(gated):
    """The OAuth layer must not regress the pre-baked-URL paths the fleet
    Worker and mobile connector already use."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}

    assert gated.post("/", headers={"X-NGS-Token": NODE_TOKEN}, json=body).status_code == 200
    assert gated.post(f"/?token={NODE_TOKEN}", json=body).status_code == 200
    assert gated.post(
        "/", headers={"Authorization": f"Bearer {NODE_TOKEN}"}, json=body
    ).status_code == 200


def test_bogus_bearer_is_rejected(gated):
    r = gated.post(
        "/",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert r.status_code == 401


def test_gate_503s_when_node_token_unset(gated):
    """Deny-by-default: an unconfigured node must not fall open."""
    saved = node.NODE_TOKEN
    node.NODE_TOKEN = None
    try:
        r = gated.post("/", headers={"Authorization": "Bearer anything"},
                       json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert r.status_code == 503
    finally:
        node.NODE_TOKEN = saved
