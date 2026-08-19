"""Keep the public gateway pointed at this box, across reboots, unattended.

The node sits behind a cloudflared *quick* tunnel whose hostname is regenerated
on every restart. Rather than let that rotation leak downstream, exactly one
thing learns the new hostname: the nougen-shard-gateway Worker, whose public
workers.dev URL never changes. Consumers bind that URL once.

This script is the whole loop:
  1. confirm the node is actually listening (discovered, not assumed)
  2. start the quick tunnel and read the hostname it was assigned
  3. redeploy the gateway Worker with NODE_ORIGIN set to that hostname
  4. verify the public URL reaches the node before declaring success
  5. stay in the foreground supervising cloudflared, so the scheduled task
     restarts the whole loop if the tunnel dies

A named tunnel would remove step 2-3 entirely, but needs a zone-level DNS:Edit
credential this box does not have. When one exists, run tools/ngs_named_tunnel.py
and point consumers straight at the hostname; this script becomes unnecessary.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATEWAY_DIR = Path(os.environ.get(
    "NOUGEN_GATEWAY_DIR", str(REPO.parent / "nougen-shard-gateway")))
PORT_CANDIDATES = "4444,4445,8766,8767"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_node_port() -> int | None:
    pinned = os.environ.get("NGS_PORT")
    cands = [pinned] if pinned else os.environ.get("NGS_PORT_CANDIDATES", PORT_CANDIDATES).split(",")
    for raw in cands:
        raw = (raw or "").strip()
        if not raw:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", int(raw))) == 0:
                return int(raw)
    return None


def find_cloudflared() -> str:
    found = shutil.which("cloudflared")
    if found:
        return found
    # Fall back to the documented install location, but only if it exists.
    default = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if Path(default).exists():
        return default
    raise SystemExit("[!] cloudflared not found on PATH or at the default install path")


def wait_for_node(timeout_s: int) -> int:
    """The node is started by its own scheduled task; both fire at logon, so
    tolerate losing that race instead of failing the whole publish."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        port = find_node_port()
        if port:
            return port
        time.sleep(3)
    raise SystemExit(f"[!] no NGS node listening after {timeout_s}s; not publishing a dead origin")


def _repoint_fleet_worker(origin: str) -> None:
    """Update nougen-fleet-mcp's SHARD_GATEWAY_URL binding to the live tunnel.

    Done through the Cloudflare API rather than `wrangler deploy` because that
    worker's source is not on this machine — only its deployed artifact is. The
    settings PATCH changes bindings without touching code.

    Secrets are re-sent as {"type": "inherit"} so their values survive: the API
    requires the COMPLETE binding list on every PATCH, and anything omitted is
    deleted. Sending secrets as inherit is what keeps FLEET_KEYS, GITHUB_TOKEN
    and the rest from being silently dropped on a routine URL change.
    """
    import json
    import urllib.request
    import uuid

    sys.path.insert(0, str(REPO / "src"))
    from nougen_shards import keymaker

    token = os.environ.get("CLOUDFLARE_API_TOKEN") or keymaker.get_secret("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or keymaker.get_secret("CLOUDFLARE_ACCOUNT_ID")
    script = os.environ.get("NOUGEN_FLEET_WORKER", "nougen-fleet-mcp")
    if not token or not account:
        raise RuntimeError("CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID unavailable")

    base = f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/scripts/{script}/settings"
    req = urllib.request.Request(base)
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as res:
        current = json.loads(res.read())["result"]

    bindings = []
    for b in current.get("bindings", []):
        if b.get("name") == "SHARD_GATEWAY_URL":
            bindings.append({"type": "plain_text", "name": b["name"], "text": origin})
        elif b.get("type") == "secret_text":
            bindings.append({"type": "inherit", "name": b["name"]})
        else:
            bindings.append(b)

    boundary = "----ngs" + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="settings"\r\n'
        f'Content-Type: application/json\r\n\r\n{json.dumps({"bindings": bindings})}\r\n'
        f'--{boundary}--\r\n'
    ).encode()
    patch = urllib.request.Request(base, method="PATCH", data=body)
    patch.add_header("Authorization", f"Bearer {token}")
    patch.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(patch, timeout=60) as res:
        out = json.loads(res.read())
    if not out.get("success"):
        raise RuntimeError(f"settings PATCH rejected: {out.get('errors')}")
    print(f"[*] fleet connector repointed -> {origin}", flush=True)


def main() -> int:
    port = wait_for_node(int(os.environ.get("NOUGEN_NODE_WAIT_S", "180")))
    print(f"[*] node        : 127.0.0.1:{port}", flush=True)

    cloudflared = find_cloudflared()
    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )

    origin = None
    deadline = time.time() + int(os.environ.get("NOUGEN_TUNNEL_WAIT_S", "120"))
    while time.time() < deadline and origin is None:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise SystemExit("[!] cloudflared exited before publishing a hostname")
            continue
        m = URL_RE.search(line)
        if m:
            origin = m.group(0)
    if not origin:
        proc.terminate()
        raise SystemExit("[!] no tunnel hostname seen in time")
    print(f"[*] tunnel      : {origin}", flush=True)

    # encoding/errors are REQUIRED here: wrangler emits ANSI colour bytes that the
    # Windows console default (cp1252) cannot decode, which raises inside
    # subprocess's reader thread and silently costs us the deploy output — and
    # with it the public URL and the verification step below.
    deploy = subprocess.run(
        ["wrangler", "deploy", "--var", f"NODE_ORIGIN:{origin}"],
        cwd=str(GATEWAY_DIR), capture_output=True, text=True, shell=True,
        encoding="utf-8", errors="replace",
    )
    if deploy.returncode != 0:
        proc.terminate()
        raise SystemExit(f"[!] gateway deploy failed:\n{deploy.stdout[-1500:]}\n{deploy.stderr[-1500:]}")
    public = None
    for line in (deploy.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("https://") and "workers.dev" in line:
            public = line
    print(f"[*] gateway     : redeployed -> {public or '(url not parsed)'}", flush=True)

    # Verify through the PUBLIC path, not the local one: the whole point is that
    # the outside world can reach the node, and a green local check has never
    # proven that.
    if public:
        import json
        import urllib.request
        for attempt in range(6):
            try:
                req = urllib.request.Request(public + "/health")
                req.add_header("User-Agent", "NouGenShards-Federation/1.0")
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = json.loads(r.read())
                print(f"[=] VERIFIED    : {public} -> {body.get('total_shards')} shards", flush=True)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 5:
                    print(f"[!] public verify failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                else:
                    time.sleep(5)

    # Repoint the fleet connector too. It cannot go through the gateway Worker:
    # a Worker fetching another Worker's workers.dev hostname returns 404 (measured
    # — /health answers 200 to any outside caller and 404 to nougen-fleet-mcp), so
    # the connector has to hold the tunnel hostname itself. That makes it a second
    # thing the rotation invalidates, and therefore a second thing this loop owns.
    try:
        _repoint_fleet_worker(origin)
    except Exception as exc:  # noqa: BLE001 - never let this kill the tunnel
        print(f"[!] fleet connector NOT repointed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    print("[*] supervising cloudflared; exit restarts the whole loop", flush=True)
    try:
        for line in proc.stdout:
            if "ERR" in line or "error" in line.lower():
                print(line.rstrip(), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
