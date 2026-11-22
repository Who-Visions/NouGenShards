"""HUD sign-in for join tenants: no password they were never given.

A join-provisioned node runs with NGS_HUD_USER = account id and NGS_HUD_PASSWORD =
NGS_NODE_TOKEN (tools/nougen-supervisor). The tenant is shown neither, so the node
must let them in on the Google identity the Join worker verified: a one-time ticket
minted by workers/join/worker.js hudTicket(). These tests pin the ticket format to
the worker (cross-language), the ticket rules, and the routes in app.py.
"""
import importlib
import json
import os
import shutil
import subprocess
import tempfile
import time

import pytest

from nougen_shards import hud_login

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "node-token-0123456789abcdef0123456789"


@pytest.fixture
def tenant_env(monkeypatch):
    monkeypatch.setenv("NGS_HUD_USER", "pat")
    monkeypatch.setenv("NGS_HUD_PASSWORD", TOKEN)
    monkeypatch.setenv("NGS_NODE_TOKEN", TOKEN)
    hud_login._used.clear()
    yield
    hud_login._used.clear()


def _ticket(sub="pat", ttl=120, nonce="nonce-123456", secret=TOKEN, now=None):
    now = time.time() if now is None else now
    return hud_login.mint(secret, hud_login.TICKET_PURPOSE, {"sub": sub, "exp": int(now + ttl), "n": nonce})


def test_ticket_signs_in_this_nodes_account_once(tenant_env):
    t = _ticket()
    assert hud_login.redeem_ticket(t) == "pat"
    assert hud_login.redeem_ticket(t) is None, "a ticket is single-use"


@pytest.mark.parametrize("kwargs", [
    {"sub": "someone-else"},           # another account's ticket
    {"secret": "other-node-token"},    # signed for another node
    {"ttl": -5},                       # expired
    {"ttl": 3600},                     # claims to live too long
    {"nonce": "short"},                # no real nonce
])
def test_bad_tickets_are_refused(tenant_env, kwargs):
    assert hud_login.redeem_ticket(_ticket(**kwargs)) is None


def test_garbage_never_raises(tenant_env):
    for junk in ["", ".", "a.b", "a.b.c", "x" * 5000, "%%%.%%%", "eyJ9.sig"]:
        assert hud_login.redeem_ticket(junk) is None
        assert hud_login.session_user(junk) is None


def test_session_cookie_is_not_a_ticket_and_vice_versa(tenant_env):
    cookie = hud_login.session_cookie("pat")
    assert hud_login.session_user(cookie) == "pat"
    assert hud_login.redeem_ticket(cookie) is None
    assert hud_login.session_user(_ticket()) is None


def test_session_dies_when_the_node_token_changes(tenant_env, monkeypatch):
    cookie = hud_login.session_cookie("pat")
    monkeypatch.setenv("NGS_NODE_TOKEN", "rotated-token")
    assert hud_login.session_user(cookie) is None


def test_password_fallback(tenant_env):
    assert hud_login.check_password("pat", TOKEN)
    assert not hud_login.check_password("pat", "wrong")
    assert not hud_login.check_password("", "")


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_join_worker_ticket_redeems_on_the_node(tenant_env):
    """The ticket the Join worker mints is the one the node accepts (format pinned both sides)."""
    script = ("import('./workers/join/worker.js').then(async m => "
              f"process.stdout.write(await m.hudTicket({{ id: 'pat', token: {json.dumps(TOKEN)} }})))")
    out = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                         capture_output=True, text=True, timeout=60, check=True)
    assert hud_login.redeem_ticket(out.stdout.strip()) == "pat"


# ------------------------------------------------------------------ app routes

pytest.importorskip("fastapi")
pytest.importorskip("gradio")


@pytest.fixture
def client(monkeypatch, tenant_env):
    from fastapi.testclient import TestClient
    tmp = tempfile.mkdtemp(prefix="ngs_hud_")
    monkeypatch.setenv("NOUGEN_HOME", tmp)
    monkeypatch.setenv("NOUGEN_VAULT_DIR", os.path.join(tmp, ".vault"))
    import app as node
    node = importlib.reload(node)
    yield TestClient(node.app, base_url="https://pat-ab12.example.com")
    for k in ("NGS_HUD_USER", "NGS_HUD_PASSWORD"):
        os.environ.pop(k, None)
    importlib.reload(node)


def test_signed_out_browser_gets_the_sign_in_page_not_a_password_wall(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/hud/login"
    page = client.get("/hud/login").text
    assert "Continue with Google" in page and "https://join.nougenai.com/open" in page


def test_join_ticket_opens_the_hud(client):
    r = client.get("/hud/ticket", params={"t": _ticket()}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    set_cookie = r.headers["set-cookie"]
    assert "nougen_hud=" in set_cookie and "HttpOnly" in set_cookie and "Secure" in set_cookie
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200 and "gradio" in home.text.lower()


def test_replayed_or_foreign_ticket_does_not_open_the_hud(client):
    t = _ticket()
    assert client.get("/hud/ticket", params={"t": t}, follow_redirects=False).status_code == 303
    client.cookies.clear()
    assert client.get("/hud/ticket", params={"t": t}, follow_redirects=False).status_code == 401
    assert client.get("/hud/ticket", params={"t": _ticket(secret="x")}, follow_redirects=False).status_code == 401
    assert client.get("/", follow_redirects=False).status_code == 303


def test_password_form_still_works(client):
    bad = client.post("/hud/login", data={"username": "pat", "password": "nope"}, follow_redirects=False)
    assert bad.status_code == 401
    ok = client.post("/hud/login", data={"username": "pat", "password": TOKEN}, follow_redirects=False)
    assert ok.status_code == 303 and "nougen_hud=" in ok.headers["set-cookie"]
    assert client.get("/", follow_redirects=False).status_code == 200


def test_gradio_api_stays_closed_without_a_session(client):
    r = client.get("/gradio_api/info", follow_redirects=False)
    assert r.status_code in (401, 403)
