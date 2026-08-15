"""Verify a fleet key end to end against nougen-fleet-mcp.

Runs the same OAuth 2.1 + PKCE flow a claude.ai custom connector runs -
dynamic registration, consent with the key, code exchange, then an
authenticated MCP tools/call - without a browser. Use it after rotating
FLEET_KEYS to confirm a key works before wiring it into a connector.

    python tools/fleet_key_check.py                  # checks FLEET_KEY_OUTPOST
    python tools/fleet_key_check.py FLEET_KEY_GM_PHONE

The key is read from the keymaker vault by name; it is never printed.
"""
import base64
import hashlib
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

ORIGIN = "https://nougen-fleet-mcp.whoentertains.workers.dev"
REDIRECT = "http://localhost:8976/callback"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """The authorize step signals success with a 302 whose Location carries the
    code; following it would just fail against a localhost port nobody serves."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


opener = urllib.request.build_opener(NoRedirect)


def post(path, data, form=False, headers=None):
    body = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
    req = urllib.request.Request(ORIGIN + path, data=body, method="POST")
    req.add_header("content-type",
                   "application/x-www-form-urlencoded" if form else "application/json")
    # Cloudflare's browser-integrity check answers the default Python-urllib
    # agent with a 403 (error 1010) before the Worker ever runs.
    req.add_header("user-agent", USER_AGENT)
    for h, v in (headers or {}).items():
        req.add_header(h, v)
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


def main() -> int:
    vault_key = sys.argv[1] if len(sys.argv) > 1 else "FLEET_KEY_OUTPOST"
    from nougen_shards import keymaker as k

    fleet_key = k.get_secret(vault_key)
    if not fleet_key:
        print(f"FAIL  {vault_key} not in vault {k.DB_PATH}")
        return 1

    # 1. dynamic client registration
    status, body, _ = post("/register", {"redirect_uris": [REDIRECT],
                                         "client_name": "fleet_key_check"})
    if status != 201:
        print(f"FAIL  /register -> {status} {body[:200]}")
        return 1
    client_id = json.loads(body)["client_id"]
    print(f"ok    /register        client_id={client_id}")

    # 2. consent, with PKCE S256
    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    status, body, headers = post("/authorize", {
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
        "code_challenge": challenge, "code_challenge_method": "S256",
        "scope": "fleet", "state": "probe", "fleet_key": fleet_key,
    }, form=True)

    if status != 302:
        # A 200 here is the consent page re-rendered with an error - the key
        # was rejected. Anything else is a malformed request.
        reason = ("key rejected - not present in FLEET_KEYS"
                  if "does not open this door" in body else f"{status}")
        print(f"FAIL  /authorize       {reason}")
        return 1
    code = urllib.parse.parse_qs(
        urllib.parse.urlparse(headers["Location"]).query)["code"][0]
    print("ok    /authorize       key accepted, code issued")

    # 3. code -> tokens
    status, body, _ = post("/token", {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": client_id,
        "code_verifier": verifier,
    }, form=True)
    if status != 200:
        print(f"FAIL  /token           {status} {body[:200]}")
        return 1
    access = json.loads(body)["access_token"]
    print(f"ok    /token           access token, {json.loads(body)['expires_in']}s ttl")

    # 4. authenticated MCP call
    status, body, _ = post("/mcp", {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "fleet_whoami", "arguments": {}},
    }, headers={"authorization": "Bearer " + access})
    if status != 200:
        print(f"FAIL  /mcp             {status} {body[:200]}")
        return 1
    result = json.loads(body).get("result", {})
    print("ok    /mcp fleet_whoami")
    print()
    for line in (result.get("content") or [{}])[0].get("text", "").splitlines():
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
