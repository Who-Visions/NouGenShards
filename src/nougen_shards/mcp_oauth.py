"""Minimal OAuth 2.1 layer so MCP clients can complete the Connect flow.

Why this exists
---------------
The node authenticates with a single shared secret (``NGS_NODE_TOKEN``),
supplied as ``X-NGS-Token``, ``Authorization: Bearer``, or ``?token=``. That
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

The node is its own authorization server. There is no user directory to
authenticate against and no per-user data to scope, so the consent screen asks
for the one credential that already exists - the node token - and exchanges it
for a per-client access token. That keeps the shared secret out of the
connector's stored URL and out of request logs, which is the main thing the
``?token=`` path gives up.

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

# Pending authorization codes: code -> {client_id, redirect_uri, challenge, exp}
_codes: dict[str, dict] = {}

# Issued access tokens: token -> {client_id, issued_at}
_tokens: dict[str, dict] = {}


def _now() -> int:
    return int(time.time())


def _prune() -> None:
    """Drop expired codes. Called on the paths that write new state, so the
    dicts cannot grow without bound on a long-lived node."""
    cutoff = _now()
    for code in [c for c, v in _codes.items() if v["exp"] < cutoff]:
        _codes.pop(code, None)


def issued_token_valid(token: str) -> bool:
    """True if `token` is an access token this module minted.

    ``_TokenGatedMCP`` calls this after the node-token comparison fails, so a
    connector that completed the OAuth flow is accepted without the caller
    ever holding the shared secret.
    """
    return token in _tokens


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
  <input type="password" name="node_token" placeholder="Node token" autofocus required>
  {error}
  <input type="hidden" name="client_id" value="{client_id}">
  <input type="hidden" name="redirect_uri" value="{redirect_uri}">
  <input type="hidden" name="state" value="{state}">
  <input type="hidden" name="code_challenge" value="{code_challenge}">
  <button type="submit">Authorize</button>
</form>
"""


def install(app, node_token_getter: Callable[[], Optional[str]]) -> None:
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
        return HTMLResponse(_CONSENT_PAGE.format(
            client=html.escape(client["client_name"]),
            client_id=html.escape(client_id),
            redirect_uri=html.escape(redirect_uri),
            state=html.escape(state),
            code_challenge=html.escape(code_challenge),
            error="",
        ))

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

        expected = node_token_getter()
        if not expected:
            raise HTTPException(status_code=503, detail="Node write-auth not configured.")
        if not node_token or not hmac.compare_digest(str(node_token), str(expected)):
            # Re-render rather than redirect: a wrong token is a user typo, not
            # a protocol error, and bouncing to the client would abort the flow.
            return HTMLResponse(
                _CONSENT_PAGE.format(
                    client=html.escape(client["client_name"]),
                    client_id=html.escape(client_id),
                    redirect_uri=html.escape(redirect_uri),
                    state=html.escape(state),
                    code_challenge=html.escape(code_challenge),
                    error='<p class="err">Invalid node token.</p>',
                ),
                status_code=401,
            )

        code = secrets.token_urlsafe(32)
        _codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "challenge": code_challenge,
            "exp": _now() + _CODE_TTL_SECONDS,
        }
        params = {"code": code}
        if state:
            params["state"] = state
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=303)

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
        _tokens[access_token] = {"client_id": client_id, "issued_at": _now()}
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
        })
