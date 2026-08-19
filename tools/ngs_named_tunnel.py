"""Create/repair the permanent Cloudflare named tunnel for blade's NGS node.

Replaces the cloudflared *quick* tunnel, whose hostname is regenerated on every
restart. A named tunnel keeps one hostname forever, so downstream consumers bind
it once and never edit it again.

Nothing here is hardcoded to an environment: the API token and account come from
keymaker, the zone id is looked up from the apex of the target hostname, the
tunnel is found by name before being created (so re-running is idempotent), and
the local service port is discovered from whatever the node is actually
listening on rather than assumed.

Reads (env overrides first, then keymaker):
  CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
Env knobs:
  NOUGEN_GATEWAY_HOSTNAME  public hostname to publish   (default mcp.nougenai.com)
  NGS_PORT                 node port; probed when unset (default probe 4444,4445,8766,8767)
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

API = "https://api.cloudflare.com/client/v4"
DEFAULT_HOSTNAME = "mcp.nougenai.com"
PORT_CANDIDATES = "4444,4445,8766,8767"


def secret(name: str) -> str | None:
    """Env override wins, then the DPAPI keymaker store."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        from nougen_shards import keymaker
        return keymaker.get_secret(name)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] keymaker lookup for {name} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def api(token: str, method: str, path: str, body=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b'{"success":false,"errors":[{"message":"http error"}]}')


def need(resp, what: str):
    if not resp.get("success"):
        msgs = "; ".join(e.get("message", "?") for e in resp.get("errors", []))
        raise SystemExit(f"[!] {what} failed: {msgs}")
    return resp["result"]


def discover_node_port() -> int:
    """The port the node is ACTUALLY listening on — never an assumed constant."""
    pinned = os.environ.get("NGS_PORT")
    candidates = [pinned] if pinned else os.environ.get("NGS_PORT_CANDIDATES", PORT_CANDIDATES).split(",")
    for raw in candidates:
        raw = (raw or "").strip()
        if not raw:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", int(raw))) == 0:
                return int(raw)
    raise SystemExit(f"[!] no NGS node listening on any of: {candidates}. Start it first.")


def main() -> int:
    token = secret("CLOUDFLARE_API_TOKEN")
    account = secret("CLOUDFLARE_ACCOUNT_ID")
    if not token or not account:
        raise SystemExit("[!] CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID not available")

    hostname = os.environ.get("NOUGEN_GATEWAY_HOSTNAME", DEFAULT_HOSTNAME)
    apex = ".".join(hostname.split(".")[-2:])
    port = discover_node_port()
    print(f"[*] node port  : {port} (discovered)")
    print(f"[*] hostname   : {hostname} (zone {apex})")

    # Account-owned tokens (cfat_*) verify under /accounts/{id}/tokens/verify;
    # user-owned ones under /user/tokens/verify. Try the account path first and
    # fall back, so this works for either kind without being told which it got.
    verify = api(token, "GET", f"/accounts/{account}/tokens/verify")
    if not verify.get("success"):
        verify = api(token, "GET", "/user/tokens/verify")
    if not verify.get("success"):
        msgs = "; ".join(e.get("message", "?") for e in verify.get("errors", []))
        raise SystemExit(f"[!] API token failed verification: {msgs}")
    print("[*] token      : verified")

    zone_id = None
    for z in need(api(token, "GET", f"/zones?name={apex}"), "zone lookup"):
        zone_id = z["id"]
    if not zone_id:
        raise SystemExit(f"[!] zone {apex} not found on this account")
    print(f"[*] zone id    : {zone_id[:12]}...")

    # Idempotent: adopt an existing tunnel of this name rather than duplicating.
    tunnel_name = os.environ.get("NOUGEN_TUNNEL_NAME", "nougen-shards-blade")
    existing = [
        t for t in need(api(token, "GET", f"/accounts/{account}/cfd_tunnel?name={tunnel_name}&is_deleted=false"),
                        "tunnel list")
        if t.get("name") == tunnel_name
    ]
    if existing:
        tunnel = existing[0]
        print(f"[*] tunnel     : reusing {tunnel_name}")
    else:
        tunnel = need(
            api(token, "POST", f"/accounts/{account}/cfd_tunnel",
                {"name": tunnel_name,
                 "tunnel_secret": secrets.token_bytes(32).hex(),
                 "config_src": "cloudflare"}),
            "tunnel create")
        print(f"[*] tunnel     : created {tunnel_name}")
    tunnel_id = tunnel["id"]

    # Ingress: the public hostname to the local node, everything else refused.
    need(
        api(token, "PUT", f"/accounts/{account}/cfd_tunnel/{tunnel_id}/configurations",
            {"config": {"ingress": [
                {"hostname": hostname, "service": f"http://127.0.0.1:{port}"},
                {"service": "http_status:404"},
            ]}}),
        "ingress config")
    print(f"[*] ingress    : {hostname} -> http://127.0.0.1:{port}")

    # DNS: proxied CNAME to the tunnel. Update in place when it already exists.
    target = f"{tunnel_id}.cfargotunnel.com"
    records = need(api(token, "GET", f"/zones/{zone_id}/dns_records?name={hostname}"), "dns lookup")
    if records:
        need(api(token, "PUT", f"/zones/{zone_id}/dns_records/{records[0]['id']}",
                 {"type": "CNAME", "name": hostname, "content": target, "proxied": True}),
             "dns update")
        print(f"[*] dns        : updated {hostname}")
    else:
        need(api(token, "POST", f"/zones/{zone_id}/dns_records",
                 {"type": "CNAME", "name": hostname, "content": target, "proxied": True}),
             "dns create")
        print(f"[*] dns        : created {hostname}")

    run_token = need(api(token, "GET", f"/accounts/{account}/cfd_tunnel/{tunnel_id}/token"), "tunnel token")
    try:
        from nougen_shards import keymaker
        keymaker.ingest_secret("NOUGEN_TUNNEL_RUN_TOKEN", run_token)
        fp = hashlib.sha256(run_token.encode()).hexdigest()[:12]
        print(f"[*] run token  : stored in keymaker (fp={fp})")
    except Exception as exc:  # noqa: BLE001
        print(f"[!] could not store run token: {type(exc).__name__}: {exc}", file=sys.stderr)

    print(f"\n[=] PUBLIC URL : https://{hostname}")
    print("[=] start with : tools/ngs_tunnel_run.cmd  (reads the run token from keymaker)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
