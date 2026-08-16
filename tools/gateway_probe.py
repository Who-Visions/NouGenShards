"""Prove the shard gateway answers an AUTHENTICATED call, not just /health.

shards_status probes /health, which is unauthenticated, so it reports the
gateway "up - recall and search are live" while every real call 401s. That
false green hid a drifted SHARD_GATEWAY_TOKEN for hours on 2026-08-15 and is
the single most misleading signal in this stack.

Prints one line: OK <n> hits, or FAIL <reason>. Exit code mirrors it, so the
supervisor can branch on either.
"""
import hashlib
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

# Resolve sibling dirs relative to this file - a hardcoded absolute path here
# names the operator's disk layout on a public repo (test_published_surface
# catches exactly this).
from pathlib import Path
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "tools"))
sys.path.insert(0, str(_REPO / "src"))

ORIGIN = "https://fleet.nougenai.com"
REDIRECT = "http://localhost:8976/callback"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def b64url(raw: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def post(path, data, form=False, headers=None):
    body = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
    req = urllib.request.Request(ORIGIN + path, data=body, method="POST")
    req.add_header("content-type",
                   "application/x-www-form-urlencoded" if form else "application/json")
    req.add_header("user-agent", UA)  # Cloudflare 403s the default Python agent
    for h, v in (headers or {}).items():
        req.add_header(h, v)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


def main() -> int:
    try:
        from nougen_shards import keymaker
        fleet_key = keymaker.get_secret("FLEET_KEY_OUTPOST")
    except Exception as exc:
        print(f"FAIL vault unreadable ({type(exc).__name__})")
        return 1
    if not fleet_key:
        print("FAIL FLEET_KEY_OUTPOST missing from vault")
        return 1

    status, body, _ = post("/register", {"redirect_uris": [REDIRECT]})
    if status != 201:
        print(f"FAIL /register {status}")
        return 1
    cid = json.loads(body)["client_id"]
    ver = b64url(secrets.token_bytes(48))
    chal = b64url(hashlib.sha256(ver.encode()).digest())
    status, body, hdrs = post("/authorize", {
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code",
        "code_challenge": chal, "code_challenge_method": "S256",
        "scope": "fleet", "fleet_key": fleet_key}, form=True)
    if status != 302:
        print("FAIL consent rejected the fleet key")
        return 1
    code = urllib.parse.parse_qs(
        urllib.parse.urlparse(hdrs["Location"]).query)["code"][0]
    status, body, _ = post("/token", {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": cid, "code_verifier": ver}, form=True)
    if status != 200:
        print(f"FAIL /token {status}")
        return 1
    tok = json.loads(body)["access_token"]

    _, body, _ = post("/mcp", {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "shards_recall",
                   "arguments": {"query": "gateway", "limit": 1}}},
        headers={"authorization": "Bearer " + tok})
    result = json.loads(body).get("result", {})
    text = (result.get("content") or [{}])[0].get("text", "")
    if result.get("isError") or "Error:" in text:
        print("FAIL " + text.strip().replace("\n", " ")[:120])
        return 1
    if '"id"' not in text:
        print("FAIL recall returned no shard content")
        return 1
    print("OK authenticated recall returned content")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
