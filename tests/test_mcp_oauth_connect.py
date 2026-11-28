"""Connector parity with the shards standard: IDE redirects, scopes,
refresh-token rotation, a help page for a bare /authorize, and Google sign-in
through the fleet's shared client (relayed by the Eye connector)."""

import base64
import json
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")
pytest.importorskip("mcp")

from fastapi.testclient import TestClient  # noqa: E402

import app as node  # noqa: E402
from nougen_shards import mcp_oauth  # noqa: E402
from tests.test_mcp_oauth import NODE_TOKEN, PUBLIC_URL, REDIRECT_URI, _authorize, _pkce, _register  # noqa: E402

GOOGLE_ENV = {
    "NGS_GOOGLE_CLIENT_ID": "gid.apps.example",
    "NGS_GOOGLE_CLIENT_SECRET": "unit-test-secret",
    "NGS_GOOGLE_CALLBACK_URL": "https://relay.example.test/oauth/google/callback",
    "NGS_GOOGLE_ALLOWED_EMAILS": "operator@example.test",
}


@pytest.fixture()
def client():
    os.environ["NGS_PUBLIC_URL"] = PUBLIC_URL
    saved = node.NODE_TOKEN
    node.NODE_TOKEN = NODE_TOKEN
    try:
        yield TestClient(node.app, base_url="https://testserver")
    finally:
        node.NODE_TOKEN = saved
        os.environ.pop("NGS_PUBLIC_URL", None)


@pytest.fixture()
def google(monkeypatch):
    for k, v in GOOGLE_ENV.items():
        monkeypatch.setenv(k, v)
    seen = {}

    def fake_exchange(cfg, code):
        seen["code"] = code
        return {"id_token": seen["id_token"]}

    monkeypatch.setattr(mcp_oauth, "_google_exchange", fake_exchange)
    return seen


def _id_token(**claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"h.{body}.sig"


def _token(client, client_id, verifier, code):
    return client.post("/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
        "client_id": client_id, "code_verifier": verifier,
    })


def _allow(client, cb):
    """Press Allow on the consent page a sign-in callback returns."""
    assert cb.status_code == 200 and "/oauth/consent" in cb.text
    grant = cb.text.split('name="grant" value="')[1].split('"')[0]
    csrf = cb.text.split('name="csrf" value="')[1].split('"')[0]
    return client.post("/oauth/consent", data={"grant": grant, "csrf": csrf}, follow_redirects=False)


def _code_from(location):
    return location.split("code=")[1].split("&")[0]


@pytest.mark.parametrize("uri", [
    "vscode://anthropic.claude/callback", "cursor://anysphere.cursor/mcp/auth",
    "windsurf://codeium/callback", "http://127.0.0.1:33418/callback",
])
def test_ide_and_loopback_redirects_register(client, uri):
    r = client.post("/register", json={"redirect_uris": [uri], "client_name": "IDE"})
    assert r.status_code == 201
    assert "refresh_token" in r.json()["grant_types"]


def test_cleartext_still_refused(client):
    r = client.post("/register", json={"redirect_uris": ["http://evil.example/cb"]})
    assert r.status_code == 400


def test_metadata_lists_scopes_and_refresh(client):
    prm = client.get("/.well-known/oauth-protected-resource").json()
    asm = client.get("/.well-known/oauth-authorization-server").json()
    assert prm["scopes_supported"] == ["fleet"]
    assert asm["scopes_supported"] == ["fleet"]
    assert "refresh_token" in asm["grant_types_supported"]


def test_bare_authorize_shows_help(client):
    r = client.get("/authorize", headers={"accept": "text/html"})
    assert r.status_code == 400
    assert "Connect NouGen Msgs" in r.text and "<svg" in r.text
    assert f"{PUBLIC_URL}/mcp" in r.text


def test_refresh_rotates_and_is_single_use(client):
    cid = _register(client)
    verifier, challenge = _pkce()
    code = _code_from(_authorize(client, cid, challenge).headers["location"])
    first = _token(client, cid, verifier, code).json()
    assert first["scope"] == "fleet" and first["refresh_token"]

    r = client.post("/token", data={"grant_type": "refresh_token", "refresh_token": first["refresh_token"], "client_id": cid})
    assert r.status_code == 200
    second = r.json()
    assert second["access_token"] != first["access_token"]
    assert mcp_oauth.issued_token_tenant(second["access_token"]) == mcp_oauth.issued_token_tenant(first["access_token"])

    again = client.post("/token", data={"grant_type": "refresh_token", "refresh_token": first["refresh_token"], "client_id": cid})
    assert again.status_code == 400


def test_refresh_bound_to_client(client):
    cid = _register(client)
    verifier, challenge = _pkce()
    code = _code_from(_authorize(client, cid, challenge).headers["location"])
    rt = _token(client, cid, verifier, code).json()["refresh_token"]
    other = _register(client)
    r = client.post("/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": other})
    assert r.status_code == 400


def test_consent_hides_google_without_config(client, monkeypatch):
    for k in GOOGLE_ENV:
        monkeypatch.delenv(k, raising=False)
    cid = _register(client)
    _, challenge = _pkce()
    r = client.get("/authorize", params={"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT_URI,
                                         "code_challenge": challenge, "code_challenge_method": "S256"})
    assert r.status_code == 200
    assert "/oauth/google/start" not in r.text


def _google_round_trip(client, google, claims):
    cid = _register(client)
    verifier, challenge = _pkce()
    page = client.get("/authorize", params={"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT_URI,
                                            "state": "s1", "code_challenge": challenge, "code_challenge_method": "S256"})
    assert "/oauth/google/start?req=" in page.text
    req = page.text.split("/oauth/google/start?req=")[1].split('"')[0]
    start = client.get("/oauth/google/start", params={"req": req}, follow_redirects=False)
    assert start.status_code == 302
    assert start.headers["location"].startswith("https://accounts.google.com/")
    assert "state=msgs~" in start.headers["location"]
    google["id_token"] = _id_token(**claims)
    cb = client.get("/oauth/google/callback", params={"code": "g-code", "state": "msgs~" + req}, follow_redirects=False)
    return cid, verifier, cb


GOOD = {"aud": GOOGLE_ENV["NGS_GOOGLE_CLIENT_ID"], "iss": "https://accounts.google.com",
        "email": "Operator@example.test", "email_verified": True}


def test_google_allowed_email_gets_a_working_token(client, google):
    cid, verifier, cb = _google_round_trip(client, google, GOOD)
    assert "location" not in cb.headers  # no code before Allow
    cb = _allow(client, cb)
    assert cb.status_code == 303
    assert cb.headers["location"].startswith(REDIRECT_URI) and "state=s1" in cb.headers["location"]
    tok = _token(client, cid, verifier, _code_from(cb.headers["location"])).json()
    assert mcp_oauth.issued_token_tenant(tok["access_token"]) == "owner"
    assert google["code"] == "g-code"


@pytest.mark.parametrize("bad", [
    {"email": "stranger@example.test"},
    {"aud": "someone-elses-client"},
    {"email_verified": False},
    {"iss": "https://evil.example"},
])
def test_google_refuses_wrong_account(client, google, bad):
    _, _, cb = _google_round_trip(client, google, {**GOOD, **bad})
    assert cb.status_code == 403
    assert "location" not in cb.headers


def test_google_request_is_single_use(client, google):
    _, _, cb = _google_round_trip(client, google, GOOD)
    assert cb.status_code == 200
    req_state = cb.request.url.params["state"]
    again = client.get("/oauth/google/callback", params={"code": "g-code", "state": req_state}, follow_redirects=False)
    assert again.status_code == 400


def test_google_leads_and_token_is_folded(client, google):
    cid = _register(client)
    _, challenge = _pkce()
    r = client.get("/authorize", params={"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT_URI,
                                         "code_challenge": challenge, "code_challenge_method": "S256"})
    assert r.text.index("Continue with Google") < r.text.index("Use a node token instead")
    assert "<details>" in r.text


FLEET = "https://fleet.example.test"


@pytest.fixture()
def fleet(monkeypatch):
    for k in GOOGLE_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NGS_FLEET_AUTH_URL", FLEET)
    monkeypatch.setenv("NGS_OWNER_EMAILS", "operator@example.test")
    seen = {}
    monkeypatch.setattr(mcp_oauth, "_fleet_register", lambda cfg, cb: seen.setdefault("cb", cb) and "fleet-client")

    def fake_exchange(cfg, code, client_id, callback, verifier):
        seen.update(code=code, client_id=client_id, callback=callback, verifier=verifier)
        return {"access_token": seen["token"]}

    monkeypatch.setattr(mcp_oauth, "_fleet_exchange", fake_exchange)
    return seen


def _fleet_token(**payload):
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"v1.{body}.sig"


def _fleet_round_trip(client, fleet, payload):
    cid = _register(client)
    verifier, challenge = _pkce()
    page = client.get("/authorize", params={"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT_URI,
                                            "state": "s9", "code_challenge": challenge, "code_challenge_method": "S256"})
    assert "/oauth/fleet/start?req=" in page.text
    req = page.text.split("/oauth/fleet/start?req=")[1].split('"')[0]
    start = client.get("/oauth/fleet/start", params={"req": req}, follow_redirects=False)
    assert start.status_code == 302
    loc = start.headers["location"]
    assert loc.startswith(FLEET + "/authorize?") and "client_id=fleet-client" in loc and "code_challenge_method=S256" in loc
    assert fleet["cb"] == PUBLIC_URL + "/oauth/fleet/callback"
    fleet["token"] = _fleet_token(**payload)
    cb = client.get("/oauth/fleet/callback", params={"code": "f-code", "state": req}, follow_redirects=False)
    return cid, verifier, cb


def test_fleet_google_owner_reaches_a_working_token(client, fleet):
    import time
    cid, verifier, cb = _fleet_round_trip(client, fleet, {"typ": "access", "eml": "Operator@Example.test", "exp": time.time() + 600})
    assert "location" not in cb.headers  # no code before Allow
    cb = _allow(client, cb)
    assert cb.status_code == 303 and "state=s9" in cb.headers["location"]
    tok = _token(client, cid, verifier, _code_from(cb.headers["location"])).json()
    assert mcp_oauth.issued_token_tenant(tok["access_token"]) == "owner"
    assert fleet["code"] == "f-code" and fleet["client_id"] == "fleet-client"


@pytest.mark.parametrize("payload", [
    {"typ": "access", "eml": "stranger@example.test", "exp": 4102444800},
    {"typ": "refresh", "eml": "operator@example.test", "exp": 4102444800},
    {"typ": "access", "eml": "operator@example.test", "exp": 1},
    {"typ": "access", "exp": 4102444800},
])
def test_fleet_refuses_anyone_else(client, fleet, payload):
    _, _, cb = _fleet_round_trip(client, fleet, payload)
    assert cb.status_code == 403 and "location" not in cb.headers


def test_fleet_state_is_single_use(client, fleet):
    _, _, cb = _fleet_round_trip(client, fleet, {"typ": "access", "eml": "operator@example.test", "exp": 4102444800})
    again = client.get("/oauth/fleet/callback", params={"code": "f-code", "state": cb.request.url.params["state"]},
                       follow_redirects=False)
    assert again.status_code == 400


def test_token_path_still_works_beside_google(client, fleet):
    cid = _register(client)
    verifier, challenge = _pkce()
    code = _code_from(_authorize(client, cid, challenge).headers["location"])
    assert _token(client, cid, verifier, code).status_code == 200


def test_allow_needs_the_signed_in_browser(client, google):
    """A stranger holding the grant cannot redeem it without the sign-in cookie."""
    _, _, cb = _google_round_trip(client, google, GOOD)
    grant = cb.text.split('name="grant" value="')[1].split('"')[0]
    csrf = cb.text.split('name="csrf" value="')[1].split('"')[0]
    client.cookies.clear()
    r = client.post("/oauth/consent", data={"grant": grant, "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 400 and "location" not in r.headers


def test_allow_needs_the_page_token(client, google):
    _, _, cb = _google_round_trip(client, google, GOOD)
    grant = cb.text.split('name="grant" value="')[1].split('"')[0]
    r = client.post("/oauth/consent", data={"grant": grant, "csrf": "forged"}, follow_redirects=False)
    assert r.status_code == 400 and "location" not in r.headers


def test_allow_page_names_client_and_destination(client, google):
    _, _, cb = _google_round_trip(client, google, GOOD)
    from urllib.parse import urlparse
    assert "Allow" in cb.text and urlparse(REDIRECT_URI).netloc in cb.text
    assert "samesite=strict" in cb.headers.get("set-cookie", "").lower()
    assert "httponly" in cb.headers.get("set-cookie", "").lower()


def test_allow_is_single_use(client, google):
    _, _, cb = _google_round_trip(client, google, GOOD)
    grant = cb.text.split('name="grant" value="')[1].split('"')[0]
    csrf = cb.text.split('name="csrf" value="')[1].split('"')[0]
    first = client.post("/oauth/consent", data={"grant": grant, "csrf": csrf}, follow_redirects=False)
    assert first.status_code == 303
    client.cookies.set("ngs_consent", grant, path="/oauth/consent")
    again = client.post("/oauth/consent", data={"grant": grant, "csrf": csrf}, follow_redirects=False)
    assert again.status_code == 400
