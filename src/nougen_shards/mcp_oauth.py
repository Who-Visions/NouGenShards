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
import json
import os
import secrets
import time
import urllib.request
from typing import Callable, Dict, Optional
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

# Refresh tokens: token -> {client_id, tenant_id, exp}. Single use: each refresh
# rotates it. In-process like the rest, so a restart still means one re-link.
_refresh: dict[str, dict] = {}
_REFRESH_TTL_SECONDS = 90 * 24 * 3600

# Authorize requests waiting on Google: id -> {client_id, redirect_uri, state,
# code_challenge, exp}. The id rides in Google's state after the relay tag.
_pending: dict[str, dict] = {}
_PENDING_TTL_SECONDS = 600

# Redirect schemes the IDE clients register with, the same list shards uses.
_APP_SCHEMES = ("vscode", "vscode-insiders", "cursor", "windsurf", "cursor-url")
_SCOPES = ["fleet"]


def _now() -> int:
    return int(time.time())


def _prune() -> None:
    """Drop expired codes. Called on the paths that write new state, so the
    dicts cannot grow without bound on a long-lived node."""
    cutoff = _now()
    for table in (_codes, _refresh, _pending):
        for key in [k for k, v in table.items() if v["exp"] < cutoff]:
            table.pop(key, None)


def redirect_allowed(uri: str) -> bool:
    """https, loopback http, or an IDE app scheme (VS Code, Cursor, Windsurf)."""
    parsed = urlparse(str(uri))
    if parsed.scheme == "https":
        return bool(parsed.netloc)
    if parsed.scheme == "http":
        return parsed.hostname in ("localhost", "127.0.0.1", "::1")
    return parsed.scheme in _APP_SCHEMES


def _google_config() -> Optional[dict]:
    """Google sign-in through the fleet's shared Google client.

    The shared Google client has one registered callback, on the Eye
    connector, and ``NGS_GOOGLE_CALLBACK_URL`` is that address. Eye sends a
    browser whose state starts with this node's tag on to this node's
    ``/oauth/google/callback``. Every value comes from the environment, so no
    host is named in code. Missing any of the first four, the consent page
    offers the node-token form only, as before.
    """
    cfg = {
        "client_id": os.environ.get("NGS_GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("NGS_GOOGLE_CLIENT_SECRET", ""),
        "callback": os.environ.get("NGS_GOOGLE_CALLBACK_URL", ""),
        "allowed": _owner_emails(),
        "tag": os.environ.get("NGS_GOOGLE_STATE_TAG", "msgs~"),
    }
    if cfg["client_id"] and cfg["client_secret"] and cfg["callback"] and cfg["allowed"]:
        return cfg
    return None


def _google_exchange(cfg: dict, code: str) -> dict:
    """Trade Google's code for its token response, server to server over TLS.

    The id_token comes straight from Google's token endpoint with our client
    secret, so its claims are read without a second signature check (OpenID
    Connect Core 3.1.3.7). Tests replace this function.
    """
    data = urlencode({
        "code": code, "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["callback"], "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data,
                                 headers={"content-type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as res:  # noqa: S310 (fixed https URL)
        return json.loads(res.read().decode())


def _id_token_claims(id_token: str) -> dict:
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:
        return {}


def _owner_emails() -> set:
    raw = os.environ.get("NGS_OWNER_EMAILS", "") or os.environ.get("NGS_GOOGLE_ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _fleet_config() -> Optional[dict]:
    """Google sign-in borrowed from the fleet connector.

    The fleet connector (``NGS_FLEET_AUTH_URL``) already signs people in with
    Google. This node registers there as an ordinary OAuth client, sends the
    browser to sign in, and trades the returned code for a fleet token over
    TLS. The token names the verified Google email; only an email listed in
    ``NGS_OWNER_EMAILS`` becomes this node's owner. No Google secret lives on
    the node and no Google console change is needed.
    """
    base = os.environ.get("NGS_FLEET_AUTH_URL", "").strip().rstrip("/")
    owners = _owner_emails()
    if base.startswith("https://") and owners:
        return {"base": base, "owners": owners}
    return None


_fleet_clients: Dict[str, str] = {}  # our callback URL -> client_id at the fleet


def _http_json(url: str, data: Optional[bytes] = None, content_type: str = "application/json") -> dict:
    req = urllib.request.Request(url, data=data, headers={"content-type": content_type, "accept": "application/json",
                                                         "user-agent": "nougen-node-oauth"})
    with urllib.request.urlopen(req, timeout=15) as res:  # noqa: S310 (https only, checked in _fleet_config)
        return json.loads(res.read().decode())


def _fleet_register(cfg: dict, callback: str) -> str:
    """Register (once per callback URL) as a client of the fleet connector. Tests replace this."""
    cached = _fleet_clients.get(callback)
    if cached:
        return cached
    body = json.dumps({"redirect_uris": [callback], "client_name": os.environ.get("NGS_CONNECT_NAME", "NouGen Msgs"),
                       "token_endpoint_auth_method": "none"}).encode()
    client_id = _http_json(cfg["base"] + "/register", body)["client_id"]
    _fleet_clients[callback] = client_id
    return client_id


def _fleet_exchange(cfg: dict, code: str, client_id: str, callback: str, verifier: str) -> dict:
    """Trade the fleet's code for its token response. Tests replace this."""
    data = urlencode({"grant_type": "authorization_code", "code": code, "client_id": client_id,
                      "redirect_uri": callback, "code_verifier": verifier}).encode()
    return _http_json(cfg["base"] + "/token", data, "application/x-www-form-urlencoded")


def _fleet_token_email(token: str) -> str:
    """The email inside a fleet access token (v1.<payload>.<sig>). The token came
    straight from the fleet's token endpoint over TLS, so it is read as is."""
    parts = (token or "").split(".")
    if len(parts) != 3 or parts[0] != "v1":
        return ""
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except Exception:
        return ""
    if payload.get("typ") != "access" or not isinstance(payload.get("exp"), (int, float)) or payload["exp"] < _now():
        return ""
    return str(payload.get("eml", "")).lower()


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


def issue_local_access_token(client_id: str = "nougen-chrome-capture") -> str:
    """Mint an in-memory OAuth access token for a locally paired client."""
    access_token = secrets.token_urlsafe(32)
    _tokens[access_token] = {
        "client_id": client_id,
        "issued_at": _now(),
        "tenant_id": "owner",
    }
    return access_token


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


# The shards look: obsidian black, purple smoke, cracked glass and a shattered
# glass brain, the design every NouGen connector shares (nougen-fleet-mcp
# src/connect-kit.mjs, theme "shards"). Pure CSS and inline SVG, no assets.
_CRACKS = ("data:image/svg+xml,%3Csvg%20xmlns%3D'http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg'%20viewBox%3D'0%200%20800%20800'"
           "%20fill%3D'none'%20stroke%3D'white'%20stroke-opacity%3D'.09'%20stroke-width%3D'1'%3E%3Cpath%20d%3D'"
           "M400%20380%20L120%2040%20M400%20380%20L20%20300%20M400%20380%20L60%20640%20M400%20380%20L300%20790%20"
           "M400%20380%20L620%20780%20M400%20380%20L790%20560%20M400%20380%20L760%20180%20M400%20380%20L520%2010'%2F%3E"
           "%3Cpath%20d%3D'M300%20260%20L250%20330%20L330%20420%20L280%20520%20M480%20250%20L560%20320%20L520%20430%20"
           "L600%20520%20M210%20180%20L170%20300%20L120%20420%20M640%20150%20L700%20300%20M330%20600%20L470%20640%20"
           "L560%20600%20M180%20520%20L260%20610'%2F%3E%3C%2Fsvg%3E")

_BRAIN = """<svg viewBox="0 0 64 64" width="44" height="44" aria-hidden="true" fill="none" stroke-linejoin="round">
<defs><linearGradient id="gb" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e9d5ff"/><stop offset=".55" stop-color="#b26bff"/><stop offset="1" stop-color="#5b21b6"/></linearGradient></defs>
<path d="M30 12c-4-4-12-3-14 3-5 0-8 5-6 9-4 3-3 9 1 11-1 5 3 9 8 8 2 4 8 5 11 1V12z" fill="url(#gb)" fill-opacity=".22" stroke="url(#gb)" stroke-width="1.6"/>
<path d="M34 12c4-4 12-3 14 3 5 0 8 5 6 9" stroke="url(#gb)" stroke-width="1.6"/>
<path d="M54 24c2 2 3 5 2 8" stroke="url(#gb)" stroke-width="1.6" stroke-dasharray="3 3"/>
<path d="M34 12v14l6 4-4 8 5 6-7 3" stroke="url(#gb)" stroke-width="1.4"/>
<path d="M16 15l6 7-5 6 7 4-3 7 6 3M10 24l7 4M11 35l6-3M30 22l-6 3M30 36l-6-4" stroke="#e9d5ff" stroke-opacity=".75" stroke-width="1"/>
<path d="M46 34l6-2 1 6-6 1zM50 44l5 1-2 5-5-2zM43 48l3 4-4 3-2-4z" fill="url(#gb)" fill-opacity=".55" stroke="#e9d5ff" stroke-opacity=".8" stroke-width=".8"/>
<path d="M57 28l3-1M58 40l3 1M52 54l2 3" stroke="#e9d5ff" stroke-opacity=".6" stroke-width="1"/>
</svg>"""

_STYLE_RAW = """
:root{color-scheme:dark;--accent:#b26bff;--ink:#f3eaff;--muted:#a99bbd;--line:rgba(178,107,255,.24)}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px 16px;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--ink);
background:url("CRACKS") center/900px no-repeat,radial-gradient(40% 30% at 20% 15%,rgba(178,107,255,.22),transparent 70%),
radial-gradient(45% 35% at 85% 80%,rgba(120,40,200,.18),transparent 70%),radial-gradient(60% 50% at 50% 0%,rgba(178,107,255,.14),transparent 70%),#050308;background-attachment:fixed}
body::before,body::after{content:"";position:fixed;inset:-20%;pointer-events:none;z-index:0;filter:blur(60px);opacity:.5;
background:radial-gradient(30% 25% at 30% 40%,rgba(160,90,255,.22),transparent 70%),radial-gradient(25% 20% at 70% 60%,rgba(90,40,160,.25),transparent 70%);
animation:smoke 28s ease-in-out infinite alternate}
body::after{animation-duration:41s;animation-direction:alternate-reverse;opacity:.35}
@keyframes smoke{from{transform:translate3d(-4%,-2%,0) rotate(0deg) scale(1)}to{transform:translate3d(4%,3%,0) rotate(8deg) scale(1.1)}}
@media (prefers-reduced-motion:reduce){body::before,body::after{animation:none}}
main{position:relative;z-index:1;width:100%;max-width:WIDTH;padding:28px 24px;border:1px solid var(--line);border-radius:24px;backdrop-filter:blur(20px);
background:linear-gradient(160deg,rgba(178,107,255,.10),rgba(10,6,16,.72) 40%,rgba(10,6,16,.85));
box-shadow:0 0 0 1px rgba(178,107,255,.08) inset,0 30px 80px rgba(0,0,0,.7),0 0 60px rgba(178,107,255,.12)}
main::before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;
background:linear-gradient(115deg,transparent 46%,rgba(255,255,255,.06) 47%,transparent 48%),linear-gradient(25deg,transparent 70%,rgba(255,255,255,.05) 71%,transparent 72%)}
.mark{width:64px;height:64px;margin:0 auto 14px;border-radius:50%;display:grid;place-items:center;border:1px solid var(--line);
background:radial-gradient(circle,rgba(178,107,255,.25),rgba(178,107,255,.04));box-shadow:0 0 24px rgba(178,107,255,.35)}
h1{margin:0 0 12px;font-size:22px;line-height:1.25;font-weight:600;text-align:center}
p{margin:0 0 16px;color:var(--muted)}
.c{text-align:center}
input{width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--line);background:rgba(0,0,0,.45);color:var(--ink);font:inherit}
.btn{display:flex;align-items:center;justify-content:center;width:100%;min-height:52px;margin:12px 0 0;border-radius:14px;font:inherit;font-weight:600;
text-decoration:none;cursor:pointer;border:1px solid var(--line);background:rgba(255,255,255,.04);color:var(--ink)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#12041f;box-shadow:0 0 24px rgba(178,107,255,.35)}
.or{text-align:center;margin:18px 0 6px;font-size:13px;color:var(--muted)}
details{margin:18px 0 0}summary{cursor:pointer;text-align:center;font-size:13px;color:var(--muted);list-style:none}
summary::-webkit-details-marker{display:none}details[open] summary{margin:0 0 10px}
.err{margin:12px 0 0;padding:10px 14px;border-radius:12px;border:1px solid rgba(255,120,140,.4);background:rgba(164,19,60,.25);color:#ffccd5}
code{display:block;padding:10px 14px;border:1px solid var(--line);border-radius:12px;background:rgba(0,0,0,.45);word-break:break-all;font:13px ui-monospace,Menlo,monospace}
""".replace("CRACKS", _CRACKS)


def _style(width: str) -> str:
    # Escaped for str.format, which fills the page templates below.
    return _STYLE_RAW.replace("WIDTH", width).replace("{", "{{").replace("}", "}}")


def _brand() -> str:
    """The name the sign-in pages show; one node can sit behind several hosts."""
    return html.escape(os.environ.get("NGS_CONNECT_NAME", "NouGen Msgs"))


_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">"""

_CONSENT_PAGE = _HEAD + """
<title>Connect {client} to {brand}</title><style>""" + _style("420px") + """</style></head>
<body><main><div class="mark">""" + _BRAIN + """</div>
  <h1>Connect {client} to {brand}</h1>
  <p class="c"><b>{client}</b> is asking to use this memory node.</p>
  {google}
  {fold_open}<form method="post" action="/authorize" style="margin:0">
  <input type="password" name="node_token" placeholder="Node token" aria-label="Node token" {autofocus} required>
  {error}
  <input type="hidden" name="client_id" value="{client_id}">
  <input type="hidden" name="redirect_uri" value="{redirect_uri}">
  <input type="hidden" name="state" value="{state}">
  <input type="hidden" name="code_challenge" value="{code_challenge}">
  <button class="btn" type="submit">Authorize with a node token</button>
  </form>{fold_close}
</main></body></html>
"""

_HELP_PAGE = _HEAD + """
<title>{title}</title><style>""" + _style("520px") + """</style></head>
<body><main><div class="mark">""" + _BRAIN + """</div>
  <h1>{title}</h1>
  <p>{body}</p>
  <code>{mcp}</code>
</main></body></html>
"""


def _help(request: Request, status: int, title: str = "", body: str = "") -> HTMLResponse:
    return HTMLResponse(_HELP_PAGE.format(
        title=title or f"Connect {_brand()}",
        body=body or ("This sign-in page is opened by your app while it connects, not directly. Add this address as a "
                      "custom connector in Claude, ChatGPT, Codex, Gemini CLI, Cursor or VS Code, then sign in when your app asks:"),
        mcp=html.escape(public_base_url(request) + "/mcp"),
    ), status_code=status)


def _google_button(pending_id: str, route: str) -> str:
    return f'<a class="btn primary" href="/oauth/{route}/start?req={html.escape(pending_id)}">Continue with Google</a>'


def install(
    app,
    node_token_getter: Optional[Callable[[], Optional[str]]] = None,
    tenant_resolver: Optional[Callable[[str], Optional[str]]] = None,
    credentials_configured_getter: Optional[Callable[[], bool]] = None,
) -> None:
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
            "scopes_supported": _SCOPES,
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
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": _SCOPES,
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
            # https, loopback for local clients and inspectors, or an IDE app
            # scheme (VS Code, Cursor, Windsurf). Nothing in cleartext elsewhere.
            if not redirect_allowed(str(uri)):
                raise HTTPException(
                    status_code=400,
                    detail=f"redirect_uri must be https, loopback or an IDE app scheme: {uri}",
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
                "grant_types": ["authorization_code", "refresh_token"],
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
        if not client_id and "text/html" in request.headers.get("accept", ""):
            # A person opened the sign-in page without an app: say how to connect.
            return _help(request, 400)
        if response_type != "code":
            raise HTTPException(status_code=400, detail="Only response_type=code is supported.")
        if code_challenge_method != "S256":
            raise HTTPException(status_code=400, detail="Only code_challenge_method=S256 is supported.")
        _check_authorize_params(client_id, redirect_uri, code_challenge)
        client = _clients[client_id]
        google = ""
        route = "fleet" if _fleet_config() else ("google" if _google_config() else "")
        if route:
            _prune()
            pending_id = secrets.token_urlsafe(24)
            _pending[pending_id] = {
                "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
                "code_challenge": code_challenge, "exp": _now() + _PENDING_TTL_SECONDS,
            }
            google = _google_button(pending_id, route)
        return HTMLResponse(_CONSENT_PAGE.format(
            brand=_brand(),
            client=html.escape(client["client_name"]),
            client_id=html.escape(client_id),
            redirect_uri=html.escape(redirect_uri),
            state=html.escape(state),
            code_challenge=html.escape(code_challenge),
            google=google,
            fold_open="<details><summary>Use a node token instead</summary>" if google else "",
            fold_close="</details>" if google else "",
            autofocus="" if google else "autofocus",
            error="",
        ))

    def _issue_code(client_id: str, redirect_uri: str, state: str, code_challenge: str, tenant_id: str):
        # Defense-in-depth: re-validate at the point of use, so the redirect
        # sink is closed even if a future caller skips _check_authorize_params.
        # Exact match against the client's registered redirect_uris, same as
        # _check_authorize_params. Silences the CodeQL open-redirect alert.
        client = _clients.get(client_id)
        if not client or redirect_uri not in client["redirect_uris"]:
            raise HTTPException(status_code=400, detail="redirect_uri not registered.")
        code = secrets.token_urlsafe(32)
        _codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "challenge": code_challenge,
            "exp": _now() + _CODE_TTL_SECONDS,
            "tenant_id": tenant_id,
        }
        params = {"code": code}
        if state:
            params["state"] = state
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=303)

    def _fleet_callback_url(request: Request) -> str:
        return public_base_url(request) + "/oauth/fleet/callback"

    @app.get("/oauth/fleet/start")
    def fleet_start(request: Request, req: str = ""):
        cfg = _fleet_config()
        pending = _pending.get(req) if cfg else None
        if not pending or pending["exp"] < _now():
            raise HTTPException(status_code=400, detail="Sign-in request expired; start again from your app.")
        callback = _fleet_callback_url(request)
        try:
            client_id = _fleet_register(cfg, callback)
        except Exception:
            raise HTTPException(status_code=502, detail="The sign-in service did not answer; try again.")
        verifier = secrets.token_urlsafe(48)
        pending["fleet"] = {"client_id": client_id, "callback": callback, "verifier": verifier}
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
        query = urlencode({
            "response_type": "code", "client_id": client_id, "redirect_uri": callback, "state": req,
            "code_challenge": challenge, "code_challenge_method": "S256", "scope": "fleet",
        })
        return RedirectResponse(f"{cfg['base']}/authorize?{query}", status_code=302)

    @app.get("/oauth/fleet/callback")
    def fleet_callback(request: Request, code: str = "", state: str = ""):
        cfg = _fleet_config()
        pending = _pending.pop(state, None) if cfg else None
        hop = (pending or {}).get("fleet")
        if not pending or not hop or pending["exp"] < _now() or not code:
            raise HTTPException(status_code=400, detail="Sign-in request expired; start again from your app.")
        try:
            token = _fleet_exchange(cfg, code, hop["client_id"], hop["callback"], hop["verifier"]).get("access_token", "")
        except Exception:
            raise HTTPException(status_code=502, detail="Google sign-in failed; try again.")
        if _fleet_token_email(token) not in cfg["owners"]:
            return _help(request, 403, title=f"That account can't use {_brand()}",
                         body="Sign in with a Google account this node knows, or use a node token. The connector address is:")
        return _issue_code(pending["client_id"], pending["redirect_uri"], pending["state"],
                           pending["code_challenge"], "owner")

    @app.get("/oauth/google/start")
    def google_start(req: str = ""):
        cfg = _google_config()
        if not cfg or req not in _pending:
            raise HTTPException(status_code=400, detail="Sign-in request expired; start again from your app.")
        query = urlencode({
            "client_id": cfg["client_id"], "redirect_uri": cfg["callback"], "response_type": "code",
            "scope": "openid email", "state": cfg["tag"] + req, "prompt": "select_account",
        })
        return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}", status_code=302)

    @app.get("/oauth/google/callback")
    def google_callback(request: Request, code: str = "", state: str = ""):
        cfg = _google_config()
        if not cfg or not state.startswith(cfg["tag"]):
            raise HTTPException(status_code=400, detail="Unknown sign-in.")
        pending = _pending.pop(state[len(cfg["tag"]):], None)
        if not pending or pending["exp"] < _now() or not code:
            raise HTTPException(status_code=400, detail="Sign-in request expired; start again from your app.")
        try:
            claims = _id_token_claims(_google_exchange(cfg, code).get("id_token", ""))
        except Exception:
            raise HTTPException(status_code=502, detail="Google sign-in failed; try again.")
        email = str(claims.get("email", "")).lower()
        if (claims.get("aud") != cfg["client_id"]
                or claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com")
                or claims.get("email_verified") is not True
                or email not in cfg["allowed"]):
            return _help(request, 403, title=f"That account can't use {_brand()}",
                         body="Sign in with a Google account this node knows, or use a node token. The connector address is:")
        # An enrolled Google account is the owner, the same tenant the node token maps to.
        return _issue_code(pending["client_id"], pending["redirect_uri"], pending["state"],
                           pending["code_challenge"], "owner")

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
            return HTMLResponse(
                _CONSENT_PAGE.format(
                    brand=_brand(),
                    client=html.escape(client["client_name"]),
                    client_id=html.escape(client_id),
                    redirect_uri=html.escape(redirect_uri),
                    state=html.escape(state),
                    code_challenge=html.escape(code_challenge),
                    google="",
                    fold_open="",
                    fold_close="",
                    autofocus="autofocus",
                    error='<p class="err">Invalid node token.</p>',
                ),
                status_code=401,
            )

        return _issue_code(client_id, redirect_uri, state, code_challenge, tenant_id)

    def _mint(client_id: str, tenant_id: str) -> JSONResponse:
        access_token = secrets.token_urlsafe(32)
        _tokens[access_token] = {"client_id": client_id, "issued_at": _now(), "tenant_id": tenant_id}
        refresh_token = secrets.token_urlsafe(32)
        _refresh[refresh_token] = {"client_id": client_id, "tenant_id": tenant_id,
                                   "exp": _now() + _REFRESH_TTL_SECONDS}
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            "refresh_token": refresh_token,
            "scope": " ".join(_SCOPES),
        })

    @app.post("/token")
    def token_exchange(
        grant_type: str = Form(""),
        code: str = Form(""),
        redirect_uri: str = Form(""),
        client_id: str = Form(""),
        code_verifier: str = Form(""),
        refresh_token: str = Form(""),
    ):
        _prune()
        if grant_type == "refresh_token":
            # Single use: popped before checks, so a stolen-and-used token is dead.
            entry = _refresh.pop(refresh_token, None)
            if not entry or entry["exp"] < _now() or entry["client_id"] != client_id:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            return _mint(client_id, entry["tenant_id"])
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

        tenant_id = entry.get("tenant_id")
        if not tenant_id:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        return _mint(client_id, tenant_id)
