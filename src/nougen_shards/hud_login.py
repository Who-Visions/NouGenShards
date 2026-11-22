"""Sign-in for the Cortex HUD that never asks a tenant for a password they never made.

A tenant node is reached at its own public hostname, and the HUD there must stay
behind a login. Join-provisioned nodes are started with NGS_HUD_USER = the account
id and NGS_HUD_PASSWORD = the node token, which nobody is ever shown, so the stock
username/password form was a wall. The identity the tenant already proved at the
Join page (a verified Google email) is what opens the node instead:

* The Join worker, after Google sign-in, mints a short-lived ticket for the
  tenant's own node: ``body.sig`` where body is base64url JSON
  ``{"sub": <account id>, "exp": <unix s>, "n": <nonce>}`` and sig is
  HMAC-SHA256(node token, "hud-ticket:" + body), base64url without padding.
  Only the Join worker and the node hold that token (KV ``tenant:<email>.token``
  and node.json), so a ticket for one node is worthless on any other.
* ``/hud/ticket?t=`` on the node checks the signature, the expiry, that ``sub``
  is this node's account, and that the nonce was not used before; then it sets a
  signed, HttpOnly session cookie and sends the browser to the HUD.
* The username/password form stays as a fallback, so owner nodes and the HF
  Space that set NGS_HUD_USER / NGS_HUD_PASSWORD themselves keep working.

Nothing here reads anything but the environment at call time, so tests and a
supervisor restart with a new token behave the same way.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import threading
import time
from typing import Optional

TICKET_PURPOSE = "hud-ticket"
SESSION_PURPOSE = "hud-session"
COOKIE = "nougen_hud"
TICKET_MAX_TTL = 300          # a ticket that claims to live longer is refused
SESSION_TTL = 7 * 24 * 3600   # a signed-in browser stays in for a week
DEFAULT_JOIN_URL = "https://join.nougenai.com"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sig(secret: str, purpose: str, body: str) -> str:
    return _b64(hmac.new(secret.encode("utf-8"), f"{purpose}:{body}".encode("ascii"),
                         hashlib.sha256).digest())


def mint(secret: str, purpose: str, claims: dict) -> str:
    body = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_sig(secret, purpose, body)}"


def verify(secret: str, purpose: str, token: str, now: Optional[float] = None) -> Optional[dict]:
    """Claims of a well-signed, unexpired token, else None. Never raises."""
    if not secret or not token or token.count(".") != 1 or len(token) > 2048:
        return None
    body, sig = token.split(".")
    if not hmac.compare_digest(sig.encode("ascii", "replace"),
                               _sig(secret, purpose, body).encode("ascii")):
        return None
    try:
        claims = json.loads(_unb64(body))
        exp = float(claims["exp"])
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(claims, dict) or not isinstance(claims.get("sub"), str):
        return None
    if (now if now is not None else time.time()) >= exp:
        return None
    return claims


# ------------------------------------------------------------------ config

def hud_user() -> str:
    return os.environ.get("NGS_HUD_USER", "")


def hud_password() -> str:
    return os.environ.get("NGS_HUD_PASSWORD", "")


def ticket_secret() -> str:
    """The node token: the one secret this node shares with the Join worker."""
    return os.environ.get("NGS_NODE_TOKEN", "")


def session_secret() -> str:
    """Key for the session cookie. Derived, so a cookie never doubles as a ticket."""
    base = ticket_secret() or hud_password()
    if not base:
        return ""
    return hashlib.sha256(f"nougen-hud-session:{hud_user()}:{base}".encode("utf-8")).hexdigest()


def configured() -> bool:
    return bool(hud_user() and hud_password())


def join_url() -> str:
    """Where "Continue with Google" goes. NGS_JOIN_URL="" turns the button off."""
    return os.environ.get("NGS_JOIN_URL", DEFAULT_JOIN_URL).rstrip("/")


# ------------------------------------------------------------------ one-time tickets

_used: dict = {}
_used_lock = threading.Lock()


def _spend(nonce: str, exp: float, now: float) -> bool:
    """True the first time a nonce is seen before it expires; False on a replay."""
    with _used_lock:
        for k in [k for k, v in _used.items() if v <= now]:
            del _used[k]
        if nonce in _used:
            return False
        _used[nonce] = exp
        return True


def redeem_ticket(ticket: str, now: Optional[float] = None) -> Optional[str]:
    """The account id a valid, unused ticket for THIS node signs in, else None."""
    now = time.time() if now is None else now
    claims = verify(ticket_secret(), TICKET_PURPOSE, ticket, now)
    if not claims or not hud_user() or not hmac.compare_digest(claims["sub"], hud_user()):
        return None
    exp = float(claims["exp"])
    nonce = str(claims.get("n") or "")
    if exp - now > TICKET_MAX_TTL or len(nonce) < 8:
        return None
    if not _spend(nonce, exp, now):
        return None
    return claims["sub"]


def check_password(username: str, password: str) -> bool:
    user, pw = hud_user(), hud_password()
    if not user or not pw:
        return False
    ok_user = hmac.compare_digest((username or "").encode("utf-8"), user.encode("utf-8"))
    ok_pass = hmac.compare_digest((password or "").encode("utf-8"), pw.encode("utf-8"))
    return ok_user and ok_pass


def session_cookie(user: str, now: Optional[float] = None) -> str:
    now = time.time() if now is None else now
    return mint(session_secret(), SESSION_PURPOSE,
                {"sub": user, "exp": int(now + SESSION_TTL), "n": secrets.token_urlsafe(8)})


def session_user(cookie_value: Optional[str], now: Optional[float] = None) -> Optional[str]:
    """The signed-in account for a session cookie, if it belongs to this node."""
    claims = verify(session_secret(), SESSION_PURPOSE, cookie_value or "", now)
    if not claims or not hud_user() or not hmac.compare_digest(claims["sub"], hud_user()):
        return None
    return claims["sub"]


# ------------------------------------------------------------------ page

def login_page(error: str = "") -> str:
    join = join_url()
    google = (f'<a class="btn primary" href="{html.escape(join)}/open">Continue with Google</a>'
              '<p class="muted">Use the Google account you joined NouGen with.</p>') if join else ""
    err = f'<p class="err" role="alert">{html.escape(error)}</p>' if error else ""
    form = ('<details{open}><summary>Sign in with a username and password</summary>'
            '<form method="post" action="/hud/login">'
            '<label>Username<input name="username" autocomplete="username" required></label>'
            '<label>Password<input name="password" type="password" autocomplete="current-password" required></label>'
            '<button class="btn" type="submit">Sign in</button></form></details>'
            ).format(open=" open" if (error or not join) else "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in to your NouGen node</title>
<style>
:root{{color-scheme:light dark;--bg:#0d0d0d;--panel:#141414;--line:#262626;--text:#f2eee6;--muted:#9a9a9a;--cta:#e2b86b;--ink:#111}}
@media (prefers-color-scheme:light){{:root{{--bg:#f5f1e8;--panel:#fff;--line:#d8d2c6;--text:#202020;--muted:#555047;--cta:#765013;--ink:#fff}}}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;padding:1rem}}
main{{width:100%;max-width:26rem;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:1.5rem}}
h1{{font-size:1.5rem;margin:0 0 1rem}}.muted{{color:var(--muted);font-size:.85rem;margin:.5rem 0 1.25rem}}
.btn{{display:block;width:100%;box-sizing:border-box;padding:.8rem 1rem;border-radius:10px;border:1px solid var(--line);background:transparent;color:var(--text);font-weight:700;font-size:1rem;text-align:center;text-decoration:none;cursor:pointer}}
.btn.primary{{background:var(--cta);color:var(--ink);border:none}}
summary{{cursor:pointer;color:var(--muted);font-size:.9rem}}form{{display:grid;gap:.75rem;margin-top:.75rem}}
label{{display:grid;gap:.25rem;font-size:.85rem;color:var(--muted)}}
input{{padding:.6rem;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--text);font-size:1rem}}
.err{{color:#ffb4ab;font-size:.9rem}}
</style></head><body><main><h1>Your NouGen node</h1>{err}{google}{form}</main></body></html>"""
