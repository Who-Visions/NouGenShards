"""Prove the shard gateway answers an AUTHENTICATED call, not just /health.

shards_status probes /health, which is unauthenticated, so it reports the
gateway "up - recall and search are live" while every real call 401s. That
false green hid a drifted SHARD_GATEWAY_TOKEN for hours on 2026-08-15 and is
the single most misleading signal in this stack.

The other half, added 2026-08-29 after this probe produced the mirror-image
lie: a healthy gateway in front of an empty node used to print a
gateway-shaped FAIL and exit 1. The whole OAuth chain had passed - register,
authorize, consent accepting the fleet key, token issue, an accepted
authenticated MCP call - and the ONLY failed assertion was that the reply
carried no shard. Anyone reading the last line went and fixed the gateway,
which was never broken. Auth health and data health are two questions and this
prints two answers.

Three states, so a caller never has to infer one from the other:

    OK <detail>               exit 0  authenticated AND the node returned content
    AUTH-OK-NO-DATA <detail>  exit 2  auth chain proven; the node behind it is
                                      empty or down. NOT a gateway fault.
    SKIPPED <reason>          exit 3  this host CANNOT run the probe: it
                                      authenticates with FLEET_KEY_OUTPOST, the
                                      OUTPOST host's key, legitimately absent
                                      anywhere else. Not a gateway fault and not
                                      a failure of anything.
    FAIL <reason>             exit 1  a step in the OAuth chain actually failed

Every line names the origin it probed. Health claims that do not name their
origin are unfalsifiable: two lanes can report different health for "the
gateway" and both be right, because they resolved different gateways.
"""
import hashlib
import json
import os
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

# Resolve at run time: a pinned origin here is a claim about somebody else's
# deployment, and this probe exists to stop unfalsifiable claims.
ORIGIN = os.environ.get("NOUGEN_FLEET_ORIGIN", "https://fleet.nougenai.com").rstrip("/")
REDIRECT = os.environ.get("NOUGEN_FLEET_REDIRECT", "http://localhost:8976/callback")
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
        print(f"SKIPPED vault unreadable ({type(exc).__name__}) "
              f"- cannot probe {ORIGIN} from this host")
        return 3
    if not fleet_key:
        # NOT a failure, and the difference is operational. This probe
        # authenticates with the OUTPOST host's fleet key, so on any other box
        # the key is legitimately absent and the probe simply cannot run.
        # Exiting 1 here made blade's "NouGen Shards Authenticated Probe"
        # scheduled task go red every five minutes about a gateway it was never
        # able to check - noise that trains a reader to ignore the one signal
        # that matters. Verified 2026-08-29: rc=1 on a 5-minute schedule.
        print(f"SKIPPED FLEET_KEY_OUTPOST not on this host "
              f"- cannot probe {ORIGIN} from here; run it from Outpost")
        return 3

    status, body, _ = post("/register", {"redirect_uris": [REDIRECT]})
    if status != 201:
        print(f"FAIL /register {status} [origin {ORIGIN}]")
        return 1
    cid = json.loads(body)["client_id"]
    ver = b64url(secrets.token_bytes(48))
    chal = b64url(hashlib.sha256(ver.encode()).digest())
    status, body, hdrs = post("/authorize", {
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code",
        "code_challenge": chal, "code_challenge_method": "S256",
        "scope": "fleet", "fleet_key": fleet_key}, form=True)
    if status != 302:
        print(f"FAIL consent rejected the fleet key [origin {ORIGIN}]")
        return 1
    code = urllib.parse.parse_qs(
        urllib.parse.urlparse(hdrs["Location"]).query)["code"][0]
    status, body, _ = post("/token", {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": cid, "code_verifier": ver}, form=True)
    if status != 200:
        print(f"FAIL /token {status} [origin {ORIGIN}]")
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
        # Auth is PROVEN at this point: register, authorize, consent, token and
        # an accepted authenticated MCP call all passed. An empty recall is the
        # node behind the gateway having nothing to give - a data-plane answer,
        # not a gateway fault. Saying FAIL here sends the reader to fix the one
        # component that just demonstrated it works.
        print(f"AUTH-OK-NO-DATA authenticated recall accepted but returned no "
              f"shard content - the node behind {ORIGIN} is empty or down")
        return 2
    print(f"OK authenticated recall returned content [origin {ORIGIN}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
