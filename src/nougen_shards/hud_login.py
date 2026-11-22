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
import functools
import hashlib
import hmac
import html
import json
import math
import os
import pathlib
import re
import secrets
import threading
import time
from typing import Optional

TICKET_PURPOSE = "hud-ticket"
SESSION_PURPOSE = "hud-session"
COOKIE = "nougen_hud"
TICKET_MAX_TTL = 300          # a ticket that claims to live longer is refused
SESSION_TTL = 7 * 24 * 3600   # a signed-in browser stays in for a week


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
    if (not secret or not token or not token.isascii() or token.count(".") != 1
            or len(token) > 2048):
        return None
    body, sig = token.split(".")
    if not hmac.compare_digest(sig.encode("ascii", "replace"),
                               _sig(secret, purpose, body).encode("ascii")):
        return None
    try:
        claims = json.loads(_unb64(body))
        exp = float(claims["exp"])
    except (ValueError, KeyError, TypeError, OverflowError):
        return None
    # json.loads accepts NaN/Infinity; a NaN exp makes every comparison False,
    # so the token would never expire. Refuse anything non-finite.
    if not math.isfinite(exp):
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


@functools.lru_cache(maxsize=8)
def _derive_session_key(user: str, base: str) -> str:
    # PBKDF2, not a bare hash: on owner nodes the base can be a typed password.
    # Cached per (user, base), so it costs once per process and changes when the
    # token or password does.
    return hashlib.pbkdf2_hmac("sha256", base.encode("utf-8"),
                               f"nougen-hud-session:{user}".encode("utf-8"), 200_000).hex()


def session_secret() -> str:
    """Key for the session cookie. Derived, so a cookie never doubles as a ticket."""
    base = ticket_secret() or hud_password()
    if not base:
        return ""
    return _derive_session_key(hud_user(), base)


def configured() -> bool:
    return bool(hud_user() and hud_password())


def join_url(host: str = "") -> str:
    """Where "Continue with Google" goes, resolved at runtime, never hard-coded.

    1. NGS_JOIN_URL, or ``join_url`` from the endpoints file (env NOUGEN_JOIN_URL);
       NGS_JOIN_URL="" turns the button off.
    2. Else the Join page beside this node: a tenant node is served at
       ``<account>-<hex>.<zone>`` and the Join worker at ``join.<zone>``, so the
       zone comes from the host the browser used. Loopback or a bare name gets
       no button (the username/password form is shown instead).
    """
    if "NGS_JOIN_URL" in os.environ:
        return os.environ["NGS_JOIN_URL"].strip().rstrip("/")
    from nougen_shards import endpoints
    configured = os.environ.get("NOUGEN_JOIN_URL", "").strip() or endpoints.resolve("join_url")
    if configured:
        return configured.rstrip("/")
    name = (host or "").split(",")[0].strip().lower().rsplit(":", 1)[0] if host and not host.startswith("[") else ""
    labels = name.split(".") if name else []
    if (len(labels) >= 3 and all(re.fullmatch(r"[a-z0-9-]{1,63}", x) for x in labels)
            and not all(x.isdigit() for x in labels)):
        return "https://join." + ".".join(labels[1:])
    return ""


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

_TOKENS = pathlib.Path(__file__).resolve().parents[2] / "designs" / "nougen-core" / "tokens.css"


@functools.lru_cache(maxsize=1)
def _design_tokens() -> str:
    """The generated nougen-core token package (designs/nougen-core/tokens.css).

    The page below only consumes these tokens, so its colours, spacing, focus and
    target sizes follow design.json and its lint and drift checks. Read once; a
    missing package leaves the page unstyled but working.
    """
    try:
        return _TOKENS.read_text(encoding="utf-8")
    except OSError:
        return ""


# Layout only: every colour, size and radius is a nougen-core token.
_PAGE_CSS = """
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);
font-family:var(--font-main);font-size:var(--type-body);line-height:var(--line-body);padding:var(--space-4)}
main{width:100%;max-width:26rem;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-lg);padding:var(--space-5)}
h1{font-size:1.5rem;margin:0 0 var(--space-4)}
.muted{color:var(--muted);font-size:var(--type-meta);margin:var(--space-2) 0 var(--space-5)}
.btn{display:flex;align-items:center;justify-content:center;width:100%;min-height:var(--target-touch);padding:var(--space-3) var(--space-4);
border-radius:var(--radius-md);border:1px solid var(--line);background:transparent;color:var(--text);font:inherit;font-weight:700;
text-decoration:none;cursor:pointer;transition:background var(--motion-fast) var(--motion-ease)}
.btn:hover{background:var(--panel-hover)}
.btn.primary{background:var(--accent);color:var(--control-ink);border-color:var(--accent)}
.btn:focus-visible,input:focus-visible,summary:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
summary{cursor:pointer;color:var(--muted);font-size:var(--type-meta);min-height:var(--target-min)}
form{display:grid;gap:var(--space-3);margin-top:var(--space-3)}
label{display:grid;gap:var(--space-1);font-size:var(--type-meta);color:var(--muted)}
input{min-height:var(--target-touch);padding:var(--space-2);border-radius:var(--radius-sm);border:1px solid var(--line);
background:var(--panel-solid);color:var(--text);font:inherit}
.err{color:var(--danger);font-size:var(--type-meta)}
"""


def login_page(error: str = "", host: str = "") -> str:
    join = join_url(host)
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
<style>{_design_tokens()}{_PAGE_CSS}</style></head><body><main><h1>Your NouGen node</h1>{err}{google}{form}</main></body></html>"""
