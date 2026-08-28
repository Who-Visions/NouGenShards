"""Google sign-in leg of the OAuth flow, fully offline.

The two Google HTTPS calls are monkeypatched at the module seam
(mcp_oauth._google_exchange_code / _google_tokeninfo); everything else -- the
consent page, the pending-state store, lane policy, code issuance, and the
/token redemption -- runs for real against the node app.
"""
import base64
import hashlib
import json
import secrets

import pytest

pytest.importorskip("gradio")

from fastapi.testclient import TestClient  # noqa: E402

import app as node  # noqa: E402
from nougen_shards import mcp_oauth, tenants  # noqa: E402

NODE_TOKEN = "unit-test-node-token"
PUBLIC_URL = "https://shards.example.test"
REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"
GOOGLE_CLIENT_ID = "unit-test.apps.googleusercontent.com"
OWNER_EMAIL = "owner@example.test"
TENANT_EMAIL = "provider@example.test"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Function-scoped node client with Google configured and a real registry
    file holding one tenant bound to TENANT_EMAIL."""
    registry = tmp_path / "tenants.json"
    registry.write_text(json.dumps({"tenants": [{
        "tenant_id": "chatgpt-app",
        "label": "ChatGPT connector lane",
        "token_sha256": tenants.token_sha256("unit-test-tenant-token"),
        "shared_vault": True,
        "google_email": TENANT_EMAIL,
    }]}), encoding="utf-8")
    monkeypatch.setenv("NOUGEN_TENANTS_FILE", str(registry))
    monkeypatch.setenv("NGS_PUBLIC_URL", PUBLIC_URL)
    monkeypatch.setenv("NOUGEN_GOOGLE_OAUTH_CLIENT_ID", GOOGLE_CLIENT_ID)
    monkeypatch.setenv("NOUGEN_GOOGLE_OAUTH_CLIENT_SECRET", "unit-test-secret")
    monkeypatch.setenv("NOUGEN_GOOGLE_OWNER_EMAILS", f" {OWNER_EMAIL.upper()} ")
    monkeypatch.setattr(node, "NODE_TOKEN", NODE_TOKEN)
    yield TestClient(node.app)
    mcp_oauth._google_pending.clear()


@pytest.fixture()
def bare_client(monkeypatch):
    """Node client with Google sign-in NOT provisioned."""
    monkeypatch.delenv("NOUGEN_GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("NOUGEN_GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("NGS_PUBLIC_URL", PUBLIC_URL)
    monkeypatch.setattr(node, "NODE_TOKEN", NODE_TOKEN)
    yield TestClient(node.app)


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    return verifier, challenge


def _register(client):
    r = client.post("/register",
                    json={"redirect_uris": [REDIRECT_URI], "client_name": "Claude"})
    assert r.status_code == 201
    return r.json()["client_id"]


def _fake_google(monkeypatch, email, aud=GOOGLE_CLIENT_ID, verified="true"):
    monkeypatch.setattr(mcp_oauth, "_google_exchange_code",
                        lambda code, redirect_uri, cfg: "fake-id-token")
    monkeypatch.setattr(mcp_oauth, "_google_tokeninfo", lambda id_token: {
        "aud": aud, "email": email, "email_verified": verified})


def _start_and_callback(client, client_id, challenge, monkeypatch, email):
    r = client.get("/oauth/google/start", params={
        "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "state": "opaque-state", "code_challenge": challenge,
    }, follow_redirects=False)
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith("https://accounts.google.com/")
    assert GOOGLE_CLIENT_ID in location
    assert f"{PUBLIC_URL}/oauth/google/callback".replace(":", "%3A").replace("/", "%2F") in location
    leg = location.split("state=")[1].split("&")[0]
    _fake_google(monkeypatch, email)
    return client.get("/oauth/google/callback",
                      params={"code": "fake-google-code", "state": leg},
                      follow_redirects=False)


def _redeem(client, client_id, location, verifier):
    code = location.split("code=")[1].split("&")[0]
    r = client.post("/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT_URI, "client_id": client_id,
        "code_verifier": verifier,
    })
    assert r.status_code == 200
    return r.json()["access_token"]


def test_feature_off_hides_button_and_routes(bare_client):
    client_id = _register(bare_client)
    _verifier, challenge = _pkce()
    r = bare_client.get("/authorize", params={
        "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "state": "s", "code_challenge": challenge})
    assert r.status_code == 200
    assert "Sign in with Google" not in r.text
    r = bare_client.get("/oauth/google/start", params={
        "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "state": "s", "code_challenge": challenge})
    assert r.status_code == 404


def test_consent_page_offers_google_when_configured(client):
    client_id = _register(client)
    _verifier, challenge = _pkce()
    r = client.get("/authorize", params={
        "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "state": "s", "code_challenge": challenge})
    assert "Sign in with Google" in r.text
    assert 'name="node_token"' in r.text  # paste fallback stays


def test_tenant_email_auto_issues_its_single_lane(client, monkeypatch):
    client_id = _register(client)
    verifier, challenge = _pkce()
    r = _start_and_callback(client, client_id, challenge, monkeypatch, TENANT_EMAIL)
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith(REDIRECT_URI)
    assert "state=opaque-state" in location
    token = _redeem(client, client_id, location, verifier)
    assert mcp_oauth.issued_token_tenant(token) == "chatgpt-app"


def test_owner_email_gets_lane_picker_and_grants(client, monkeypatch):
    client_id = _register(client)
    verifier, challenge = _pkce()
    r = _start_and_callback(client, client_id, challenge, monkeypatch, OWNER_EMAIL)
    assert r.status_code == 200
    assert "chatgpt-app" in r.text and "owner" in r.text.lower()
    grant_key = r.text.split('name="grant_key" value="')[1].split('"')[0]
    r = client.post("/oauth/google/grant",
                    data={"grant_key": grant_key, "lane": "chatgpt-app"},
                    follow_redirects=False)
    assert r.status_code == 303
    token = _redeem(client, client_id, r.headers["location"], verifier)
    assert mcp_oauth.issued_token_tenant(token) == "chatgpt-app"


def test_unknown_email_is_refused(client, monkeypatch):
    client_id = _register(client)
    _verifier, challenge = _pkce()
    r = _start_and_callback(client, client_id, challenge, monkeypatch,
                            "stranger@example.test")
    assert r.status_code == 403


def test_wrong_audience_is_refused(client, monkeypatch):
    client_id = _register(client)
    _verifier, challenge = _pkce()
    r = client.get("/oauth/google/start", params={
        "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "state": "s", "code_challenge": challenge}, follow_redirects=False)
    leg = r.headers["location"].split("state=")[1].split("&")[0]
    _fake_google(monkeypatch, OWNER_EMAIL, aud="someone-else.apps.googleusercontent.com")
    r = client.get("/oauth/google/callback",
                   params={"code": "fake", "state": leg}, follow_redirects=False)
    assert r.status_code == 401


def test_forged_lane_is_refused(client, monkeypatch):
    client_id = _register(client)
    _verifier, challenge = _pkce()
    r = _start_and_callback(client, client_id, challenge, monkeypatch, TENANT_EMAIL)
    # tenant email auto-issued; now forge a grant with a random key
    r = client.post("/oauth/google/grant",
                    data={"grant_key": "forged", "lane": "owner"})
    assert r.status_code == 400


def test_unknown_state_is_refused(client, monkeypatch):
    _fake_google(monkeypatch, OWNER_EMAIL)
    r = client.get("/oauth/google/callback",
                   params={"code": "fake", "state": "never-issued"})
    assert r.status_code == 400
