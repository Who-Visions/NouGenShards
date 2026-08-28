"""Minimal OAuth 2.1 layer so MCP clients can complete the Connect flow.

Why this exists
---------------
The node authenticates with the owner secret (``NGS_NODE_TOKEN``) or a hashed
tenant credential, supplied as ``X-NGS-Token``, ``Authorization: Bearer``, or
``?token=``. That
works for anything that can be handed a pre-baked URL, but it does not work
for the "Connect" button in a Claude custom connector: the client discovers
auth the way MCP's authorization spec prescribes.

    1. call the endpoint with no credential
    2. read ``WWW-Authenticate`` off the 401 to find the protected-resource
       metadata
    3. read ``authorization_servers`` out of that metadata
    4. fetch the authorization server's metadata
    5. register itself at ``registration_endpoint`` (RFC 7591 dynamic client
       registration), because it has no pre-issued client_id
    6. run authorization_code + PKCE

Before this module the node failed at step 2: ``_TokenGatedMCP`` returned a
bare JSON 401 with no ``WWW-Authenticate``, so the client fell back to probing
``/.well-known/oauth-authorization-server``, got a 404, and surfaced
"Couldn't register with NouGenShards's sign-in service."

The node is its own authorization server. The consent screen resolves the
typed credential to a tenant and exchanges it for a per-client access token
that carries the same tenant id. That keeps the durable credential out of the
connector's stored URL and request logs without collapsing tenants back into
one vault.

State is in-process and dies with the node. That matches the rest of the node
on ephemeral storage (see the ``persistent_storage`` warning in /health); a
restart forces connectors to re-authorize, which is an acceptable trade for
not standing up a datastore purely to hold OAuth grants.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import secrets
import time
from typing import Callable, Optional
from urllib.parse import urlencode, urlparse

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# Authorization codes are single-use and redeemed immediately by the client.
# Ten minutes is the ceiling RFC 6749 section 4.1.2 recommends.
_CODE_TTL_SECONDS = 600

# Registered clients: client_id -> {redirect_uris, client_name}. Dynamic
# registration is open, which is what the spec intends for public MCP servers:
# a client_id alone grants nothing, since every code still requires the node
# token to be entered at /authorize.
_clients: dict[str, dict] = {}

# Pending authorization codes: code -> {client_id, redirect_uri, challenge, exp, tenant_id}
_codes: dict[str, dict] = {}

# Issued access tokens: token -> {client_id, issued_at, tenant_id}
_tokens: dict[str, dict] = {}

# Google sign-in legs in flight: state -> pending authorize params + exp.
# Two stages share the dict: "start" rows await the Google redirect back,
# "grant" rows await the lane pick. Same in-process lifetime trade as _codes.
_google_pending: dict[str, dict] = {}

#: Ceiling for a human round-trip through Google's account chooser.
_GOOGLE_PENDING_TTL = int(os.environ.get("NOUGEN_GOOGLE_PENDING_TTL", "600"))

#: Endpoints are Google-stable but env-overridable for tests and any future
#: googleapis migration (dynamic-over-hardcode: the constant is the fallback).
_GOOGLE_AUTH_URL = os.environ.get(
    "NOUGEN_GOOGLE_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth")
_GOOGLE_TOKEN_URL = os.environ.get(
    "NOUGEN_GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")
_GOOGLE_TOKENINFO_URL = os.environ.get(
    "NOUGEN_GOOGLE_TOKENINFO_URL", "https://oauth2.googleapis.com/tokeninfo")


def _google_config() -> Optional[dict]:
    """Google RP credentials, or None when sign-in is not provisioned.

    Read per-request so the feature follows the environment without a code
    change; the launcher (start_grid) is responsible for peeling the values
    out of the keymaker into the child environment -- they never live in code.
    """
    client_id = os.environ.get("NOUGEN_GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NOUGEN_GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return {"client_id": client_id, "client_secret": client_secret}
    return None


def _google_exchange_code(code: str, redirect_uri: str, cfg: dict) -> Optional[str]:
    """Redeem a Google authorization code for its id_token; None on failure.

    Module-level and stdlib-only so tests monkeypatch it instead of the
    network."""
    import json as _json
    import urllib.request
    body = urlencode({
        "code": code,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("ascii")
    req = urllib.request.Request(
        _GOOGLE_TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = _json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    id_token = payload.get("id_token")
    return id_token if isinstance(id_token, str) and id_token else None


def _google_tokeninfo(id_token: str) -> Optional[dict]:
    """Ask Google to validate an id_token; None on any failure."""
    import json as _json
    import urllib.request
    url = f"{_GOOGLE_TOKENINFO_URL}?{urlencode({'id_token': id_token})}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return _json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _google_verified_email(id_token: str, cfg: dict) -> Optional[str]:
    """Verified, lowercased email carried by the id_token, or None.

    tokeninfo already checks signature and expiry; audience is checked here
    because a token minted for any other client must not open this node."""
    info = _google_tokeninfo(id_token)
    if not info:
        return None
    if info.get("aud") != cfg["client_id"]:
        return None
    if str(info.get("email_verified")).lower() not in ("true", "1"):
        return None
    email = info.get("email")
    return email.strip().casefold() if isinstance(email, str) and email else None


def _now() -> int:
    return int(time.time())


def _prune() -> None:
    """Drop expired codes and stale Google legs. Called on the paths that
    write new state, so the dicts cannot grow without bound on a long-lived
    node."""
    cutoff = _now()
    for code in [c for c, v in _codes.items() if v["exp"] < cutoff]:
        _codes.pop(code, None)
    for key in [k for k, v in _google_pending.items() if v["exp"] < cutoff]:
        _google_pending.pop(key, None)


def issued_token_valid(token: str) -> bool:
    """True if `token` is an access token this module minted.

    ``_TokenGatedMCP`` calls this after the node-token comparison fails, so a
    connector that completed the OAuth flow is accepted without the caller
    ever holding the shared secret.
    """
    return token in _tokens


def issued_token_tenant(token: str) -> Optional[str]:
    """Return the tenant carried by an issued token, never a default tenant."""
    entry = _tokens.get(token)
    if not entry:
        return None
    tenant_id = entry.get("tenant_id")
    return tenant_id if isinstance(tenant_id, str) and tenant_id else None


def public_base_url(request: Request) -> str:
    """Absolute origin clients should use for callbacks and metadata.

    Prefers ``NGS_PUBLIC_URL`` because the node runs behind Cloudflare in front
    of a managed platform: uvicorn sees an internal scheme and host, and every
    URL in OAuth metadata has to match what the browser actually reached or
    the client rejects the redirect. Falls back to forwarded headers, then to
    whatever the ASGI scope saw.
    """
    configured = os.environ.get("NGS_PUBLIC_URL")
    if configured:
        return configured.rstrip("/")
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if proto and host:
        return f"{proto}://{host}"
    return str(request.base_url).rstrip("/")


def _verify_pkce(verifier: str, challenge: str) -> bool:
    """S256 only. RFC 7636 permits ``plain``, but every MCP client sends S256
    and accepting ``plain`` would let a network observer replay a code."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return hmac.compare_digest(expected, challenge)


_CONSENT_PAGE = """<!doctype html>
<title>Authorize {client}</title>
<style>
 body{{font:15px/1.5 system-ui,sans-serif;background:#111;color:#eee;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
 form{{background:#1c1c1c;padding:2rem;border-radius:12px;max-width:26rem;width:100%}}
 h1{{font-size:1.1rem;margin:0 0 .25rem}} p{{color:#aaa;margin:0 0 1.25rem}}
 input{{width:100%;padding:.6rem;border-radius:6px;border:1px solid #444;
        background:#111;color:#eee;box-sizing:border-box}}
 button{{margin-top:1rem;width:100%;padding:.6rem;border:0;border-radius:6px;
         background:#c96442;color:#fff;font-weight:600;cursor:pointer}}
 .err{{color:#f88;margin:.5rem 0 0}}
</style>
<form method="post" action="/authorize">
  <h1>Connect to NouGenShards</h1>
  <p><b>{client}</b> is requesting access to this memory node.</p>
  {google}
  <input type="password" name="node_token" placeholder="Node token" autofocus required>
  {error}
  <input type="hidden" name="client_id" value="{client_id}">
  <input type="hidden" name="redirect_uri" value="{redirect_uri}">
  <input type="hidden" name="state" value="{state}">
  <input type="hidden" name="code_challenge" value="{code_challenge}">
  <button type="submit">Authorize</button>
</form>
"""

#: Rendered into the consent page only when _google_config() resolves; the
#: token input stays underneath as the bootstrap fallback.
_GOOGLE_BUTTON = """
  <a href="/oauth/google/start?{query}" style="display:block;text-align:center;
     padding:.6rem;border-radius:6px;background:#fff;color:#222;font-weight:600;
     text-decoration:none;margin-bottom:1rem">Sign in with Google</a>
  <p style="text-align:center;color:#777;margin:0 0 1rem">or paste a node token</p>
"""

_LANE_PAGE = """<!doctype html>
<title>Choose a lane</title>
<style>
 body{{font:15px/1.5 system-ui,sans-serif;background:#111;color:#eee;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
 form{{background:#1c1c1c;padding:2rem;border-radius:12px;max-width:26rem;width:100%}}
 h1{{font-size:1.1rem;margin:0 0 .25rem}} p{{color:#aaa;margin:0 0 1.25rem}}
 button{{margin-top:.5rem;width:100%;padding:.6rem;border:0;border-radius:6px;
         background:#c96442;color:#fff;font-weight:600;cursor:pointer}}
</style>
<form method="post" action="/oauth/google/grant">
  <h1>Signed in as {email}</h1>
  <p>Grant <b>{client}</b> access as which lane?</p>
  <input type="hidden" name="grant_key" value="{grant_key}">
  {buttons}
</form>
"""


def install(
    app,
    node_token_getter: Optional[Callable[[], Optional[str]]] = None,
    tenant_resolver: Optional[Callable[[str], Optional[str]]] = None,
    credentials_configured_getter: Optional[Callable[[], bool]] = None,
    lanes_for_email: Optional[Callable[[str], list]] = None,
) -> None:

    def _render_consent(client_name: str, client_id: str, redirect_uri: str,
                        state: str, code_challenge: str, error: str = "",
                        status_code: int = 200) -> HTMLResponse:
        google_block = ""
        if _google_config() and lanes_for_email:
            google_block = _GOOGLE_BUTTON.format(query=urlencode({
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
            }))
        return HTMLResponse(_CONSENT_PAGE.format(
            client=html.escape(client_name),
            client_id=html.escape(client_id),
            redirect_uri=html.escape(redirect_uri),
            state=html.escape(state),
            code_challenge=html.escape(code_challenge),
            google=google_block,
            error=error,
        ), status_code=status_code)

    def _issue_code_redirect(client_id: str, redirect_uri: str, challenge: str,
                             state: str, tenant_id: str) -> RedirectResponse:
        code = secrets.token_urlsafe(32)
        _codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "challenge": challenge,
            "exp": _now() + _CODE_TTL_SECONDS,
            "tenant_id": tenant_id,
        }
        params = {"code": code}
        if state:
            params["state"] = state
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=303)
    """Register the OAuth endpoints on `app`.

    `node_token_getter` is read at request time rather than captured, so tests
    and runtime reconfiguration can swap the node token without re-importing.
    Must be called before the Gradio catch-all is mounted at "/", otherwise
    these routes are shadowed.
    """

    @app.get("/.well-known/oauth-protected-resource")
    @app.get("/.well-known/oauth-protected-resource/mcp")
    def protected_resource_metadata(request: Request):
        """RFC 9728. The path-suffixed variant exists because clients derive it
        from the resource path (`/mcp`), and the spec allows either form."""
        base = public_base_url(request)
        return JSONResponse({
            "resource": f"{base}/mcp",
            "authorization_servers": [base],
            "bearer_methods_supported": ["header"],
        })

    @app.get("/.well-known/oauth-authorization-server")
    @app.get("/.well-known/oauth-authorization-server/mcp")
    def authorization_server_metadata(request: Request):
        """RFC 8414."""
        base = public_base_url(request)
        return JSONResponse({
            "issuer": base,
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token",
            "registration_endpoint": f"{base}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        })

    @app.post("/register", status_code=201)
    async def register_client(request: Request):
        """RFC 7591 dynamic client registration.

        Open by design: the client_id it hands back is not a credential. Every
        authorization still requires the node token at the consent screen, so
        an unsolicited registration buys an attacker nothing but a dict entry.
        """
        _prune()
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body.")

        redirect_uris = body.get("redirect_uris") or []
        if not isinstance(redirect_uris, list) or not redirect_uris:
            raise HTTPException(status_code=400, detail="redirect_uris is required.")
        for uri in redirect_uris:
            parsed = urlparse(str(uri))
            # Loopback stays permitted for local MCP clients and inspectors;
            # everything else must be TLS so a code cannot leak in cleartext.
            if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
                raise HTTPException(
                    status_code=400,
                    detail=f"redirect_uri must be https or loopback: {uri}",
                )

        client_id = secrets.token_urlsafe(24)
        _clients[client_id] = {
            "redirect_uris": [str(u) for u in redirect_uris],
            "client_name": str(body.get("client_name") or "MCP client"),
        }
        return JSONResponse(
            {
                "client_id": client_id,
                "redirect_uris": _clients[client_id]["redirect_uris"],
                "client_name": _clients[client_id]["client_name"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
            },
            status_code=201,
        )

    def _check_authorize_params(client_id: str, redirect_uri: str, code_challenge: str) -> dict:
        client = _clients.get(client_id)
        if not client:
            raise HTTPException(status_code=400, detail="Unknown client_id.")
        # Exact match, not prefix: a prefix check would let a registered
        # client redirect a code to an attacker-chosen path on its own origin.
        if redirect_uri not in client["redirect_uris"]:
            raise HTTPException(status_code=400, detail="redirect_uri not registered.")
        if not code_challenge:
            raise HTTPException(status_code=400, detail="code_challenge is required (S256).")
        return client

    @app.get("/authorize")
    def authorize_form(
        request: Request,
        client_id: str = "",
        redirect_uri: str = "",
        state: str = "",
        code_challenge: str = "",
        code_challenge_method: str = "S256",
        response_type: str = "code",
    ):
        if response_type != "code":
            raise HTTPException(status_code=400, detail="Only response_type=code is supported.")
        if code_challenge_method != "S256":
            raise HTTPException(status_code=400, detail="Only code_challenge_method=S256 is supported.")
        _check_authorize_params(client_id, redirect_uri, code_challenge)
        client = _clients[client_id]
        return _render_consent(client["client_name"], client_id, redirect_uri,
                               state, code_challenge)

    @app.post("/authorize")
    def authorize_submit(
        node_token: str = Form(""),
        client_id: str = Form(""),
        redirect_uri: str = Form(""),
        state: str = Form(""),
        code_challenge: str = Form(""),
    ):
        _prune()
        client = _check_authorize_params(client_id, redirect_uri, code_challenge)

        configured = (credentials_configured_getter() if credentials_configured_getter
                      else bool(node_token_getter and node_token_getter()))
        if not configured:
            raise HTTPException(status_code=503, detail="Node write-auth not configured.")
        if tenant_resolver:
            tenant_id = tenant_resolver(node_token) if node_token else None
        else:
            expected = node_token_getter() if node_token_getter else None
            tenant_id = ("owner" if node_token and expected
                         and hmac.compare_digest(str(node_token), str(expected)) else None)
        if not tenant_id:
            # Re-render rather than redirect: a wrong token is a user typo, not
            # a protocol error, and bouncing to the client would abort the flow.
            return _render_consent(
                client["client_name"], client_id, redirect_uri, state,
                code_challenge, error='<p class="err">Invalid node token.</p>',
                status_code=401)

        return _issue_code_redirect(client_id, redirect_uri, code_challenge,
                                    state, tenant_id)

    @app.get("/oauth/google/start")
    def google_start(
        request: Request,
        client_id: str = "",
        redirect_uri: str = "",
        state: str = "",
        code_challenge: str = "",
    ):
        cfg = _google_config()
        if not cfg or not lanes_for_email:
            raise HTTPException(status_code=404, detail="Google sign-in is not configured.")
        _prune()
        _check_authorize_params(client_id, redirect_uri, code_challenge)
        leg = secrets.token_urlsafe(32)
        _google_pending[leg] = {
            "stage": "start",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "challenge": code_challenge,
            "exp": _now() + _GOOGLE_PENDING_TTL,
        }
        callback = f"{public_base_url(request)}/oauth/google/callback"
        return RedirectResponse(f"{_GOOGLE_AUTH_URL}?" + urlencode({
            "client_id": cfg["client_id"],
            "redirect_uri": callback,
            "response_type": "code",
            "scope": "openid email",
            "state": leg,
            "prompt": "select_account",
        }), status_code=303)

    @app.get("/oauth/google/callback")
    def google_callback(request: Request, code: str = "", state: str = "",
                        error: str = ""):
        cfg = _google_config()
        if not cfg or not lanes_for_email:
            raise HTTPException(status_code=404, detail="Google sign-in is not configured.")
        _prune()
        # Pop unconditionally: a leg is single-use whatever Google answered.
        pending = _google_pending.pop(state, None)
        if not pending or pending.get("stage") != "start" or pending["exp"] < _now():
            raise HTTPException(status_code=400, detail="Sign-in expired; start over.")
        if error or not code:
            raise HTTPException(status_code=400, detail="Google sign-in was cancelled.")
        callback = f"{public_base_url(request)}/oauth/google/callback"
        id_token = _google_exchange_code(code, callback, cfg)
        email = _google_verified_email(id_token, cfg) if id_token else None
        if not email:
            raise HTTPException(status_code=401, detail="Google sign-in could not be verified.")
        lanes = list(lanes_for_email(email) or [])
        if not lanes:
            raise HTTPException(
                status_code=403,
                detail="This Google account is not mapped to any lane on this node.")
        client = _clients.get(pending["client_id"]) or {}
        if len(lanes) == 1:
            return _issue_code_redirect(
                pending["client_id"], pending["redirect_uri"],
                pending["challenge"], pending["state"], lanes[0][0])
        grant_key = secrets.token_urlsafe(32)
        _google_pending[grant_key] = {
            **pending,
            "stage": "grant",
            "email": email,
            "lanes": [lane_id for lane_id, _label in lanes],
            "exp": _now() + _GOOGLE_PENDING_TTL,
        }
        buttons = "\n".join(
            f'<button type="submit" name="lane" value="{html.escape(lane_id)}">'
            f'{html.escape(label)} ({html.escape(lane_id)})</button>'
            for lane_id, label in lanes)
        return HTMLResponse(_LANE_PAGE.format(
            email=html.escape(email),
            client=html.escape(client.get("client_name", "this client")),
            grant_key=html.escape(grant_key),
            buttons=buttons,
        ))

    @app.post("/oauth/google/grant")
    def google_grant(grant_key: str = Form(""), lane: str = Form("")):
        _prune()
        pending = _google_pending.pop(grant_key, None)
        if not pending or pending.get("stage") != "grant" or pending["exp"] < _now():
            raise HTTPException(status_code=400, detail="Grant expired; start over.")
        # The pick must come from the set the verified email was offered --
        # the form is client-side and a POSTed lane is attacker-choosable.
        if lane not in pending.get("lanes", []):
            raise HTTPException(status_code=403, detail="Lane not offered to this account.")
        return _issue_code_redirect(pending["client_id"], pending["redirect_uri"],
                                    pending["challenge"], pending["state"], lane)

    @app.post("/token")
    def token_exchange(
        grant_type: str = Form(""),
        code: str = Form(""),
        redirect_uri: str = Form(""),
        client_id: str = Form(""),
        code_verifier: str = Form(""),
    ):
        if grant_type != "authorization_code":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

        # Pop first: a code is single-use, and popping before validation means
        # a failed exchange cannot be retried against the same code.
        entry = _codes.pop(code, None)
        if not entry:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if entry["exp"] < _now():
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if entry["client_id"] != client_id or entry["redirect_uri"] != redirect_uri:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if not code_verifier or not _verify_pkce(code_verifier, entry["challenge"]):
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

        access_token = secrets.token_urlsafe(32)
        tenant_id = entry.get("tenant_id")
        if not tenant_id:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        _tokens[access_token] = {
            "client_id": client_id,
            "issued_at": _now(),
            "tenant_id": tenant_id,
        }
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
        })
