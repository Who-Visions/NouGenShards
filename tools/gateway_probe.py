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
import os
import secrets
import sys
import time
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

_NOUGEN_HOME = Path(os.environ.get("NOUGEN_HOME", str(Path.home() / ".nougen"))).expanduser()
sys.path.insert(0, str(_NOUGEN_HOME / "bin"))
_SECRETS_DB = Path(os.environ.get(
    "NOUGEN_SECRETS_DB", str(_NOUGEN_HOME / "secrets" / "shards_secrets.db"))).expanduser()
_STATE_DIR = Path(os.environ.get(
    "NOUGEN_PROBE_STATE_DIR", str(_NOUGEN_HOME / "state"))).expanduser()
_TIMEOUT_S = max(1.0, float(os.environ.get("NOUGEN_PROBE_TIMEOUT_S", "8")))


def _resolve_origin() -> str:
    """Resolve the probe target without binding the repo to one machine."""
    candidates = [
        os.environ.get("NOUGEN_GATEWAY_PROBE_ORIGIN", "").strip(),
        os.environ.get("SHARD_GATEWAY_URL", "").strip(),
        os.environ.get("NOUGEN_SHARDS_GATEWAY_URL", "").strip(),
    ]
    config_path = Path(os.environ.get(
        "NOUGEN_CONFIG", str(_NOUGEN_HOME / "config.json"))).expanduser()
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        candidates.extend(str(cfg.get(k, "")).strip() for k in (
            "gateway_url", "shard_gateway_url", "mcp_url"))
    except (OSError, ValueError, TypeError):
        pass
    # OAuth control-plane compatibility fallback; deployments can pin their
    # canonical gateway with NOUGEN_GATEWAY_PROBE_ORIGIN.
    return next((v.rstrip("/") for v in candidates if v),
                "https://fleet.nougenai.com")


ORIGIN = _resolve_origin()
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
        with opener.open(req, timeout=_TIMEOUT_S) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, f"{type(e).__name__}: {e}", {}


def _write_state(ok: bool, detail: str) -> None:
    """Persist a non-secret result so Task Scheduler failures are inspectable."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ok": ok,
            "origin": ORIGIN,
            "detail": detail[:500],
        }
        tmp = _STATE_DIR / "gateway_probe.json.tmp"
        tmp.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(_STATE_DIR / "gateway_probe.json")
        alert = _STATE_DIR / "gateway_probe.alert"
        if ok:
            alert.unlink(missing_ok=True)
        else:
            alert.write_text(detail[:1000] + "\n", encoding="utf-8")
    except OSError:
        # Probe health must never be masked by an unwritable diagnostics path.
        pass


def fail(detail: str) -> int:
    print("FAIL " + detail)
    _write_state(False, detail)
    return 1


def succeed(detail: str) -> int:
    print("OK " + detail)
    _write_state(True, detail)
    return 0


def _fleet_key():
    """Read the fleet key by name; support the legacy secrets DB only."""
    try:
        from nougen_shards import keymaker
        fleet_key = keymaker.get_secret("FLEET_KEY_OUTPOST")
    except Exception as exc:
        fleet_key = None
        print(f"INFO canonical vault lookup unavailable ({type(exc).__name__})",
              file=sys.stderr)
    if fleet_key:
        return fleet_key
    try:
        import keymaker_peel
        rows = keymaker_peel.load("FLEET_KEY_OUTPOST", db=_SECRETS_DB)
        return rows[0][1] if rows else None
    except Exception:
        return None


def main() -> int:
    fleet_key = _fleet_key()
    if not fleet_key:
        return fail("FLEET_KEY_OUTPOST missing from vault")

    status, body, _ = post("/register", {"redirect_uris": [REDIRECT]})
    if status != 201:
        return fail(f"/register {status}")
    cid = json.loads(body)["client_id"]
    ver = b64url(secrets.token_bytes(48))
    chal = b64url(hashlib.sha256(ver.encode()).digest())
    status, body, hdrs = post("/authorize", {
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code",
        "code_challenge": chal, "code_challenge_method": "S256",
        "scope": "fleet", "fleet_key": fleet_key}, form=True)
    if status != 302:
        return fail("consent rejected the fleet key")
    try:
        code = urllib.parse.parse_qs(
            urllib.parse.urlparse(hdrs["Location"]).query)["code"][0]
    except (KeyError, IndexError, ValueError):
        return fail("/authorize returned no code")
    status, body, _ = post("/token", {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT, "client_id": cid, "code_verifier": ver}, form=True)
    if status != 200:
        return fail(f"/token {status}")
    try:
        tok = json.loads(body)["access_token"]
    except (KeyError, TypeError, ValueError):
        return fail("/token returned no access token")

    status, body, _ = post("/mcp", {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "shards_recall",
                   "arguments": {"query": "gateway", "limit": 1}}},
        headers={"authorization": "Bearer " + tok})
    if status != 200:
        return fail(f"/mcp {status}")
    try:
        result = json.loads(body).get("result", {})
    except (TypeError, ValueError):
        return fail("/mcp returned invalid JSON")
    text = (result.get("content") or [{}])[0].get("text", "")
    if result.get("isError") or "Error:" in text:
        return fail(text.strip().replace("\n", " ")[:120])
    if '"id"' not in text:
        return fail("recall returned no shard content")
    return succeed("authenticated recall returned content")


if __name__ == "__main__":
    raise SystemExit(main())
