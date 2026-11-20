"""Deploy nougen-tube-mcp Worker and bind custom domain from environment/endpoints."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

NOUGEN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NOUGEN_ROOT / "src"))
from nougen_shards import endpoints, keymaker  # noqa: E402

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "0d4ac187acceea4d9692619097927d1e")
ZONE_ID = os.environ.get("CLOUDFLARE_ZONE_ID", "0d43ea57e3b800e4f75123b1e72bc45f")
SCRIPT_NAME = "nougen-tube-mcp"
COMPATIBILITY_DATE = "2026-09-01"
WORKER_JS = Path(__file__).resolve().parent / "src" / "worker.js"


def _resolve_domain_root() -> str:
    gw = endpoints.fleet_gateway_url() or ""
    if "://" in gw:
        host = gw.split("://", 1)[1].split("/", 1)[0]
        parts = host.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
    return os.environ.get("NOUGEN_DOMAIN_ROOT", "")


def cf_request(
    url: str,
    token: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    content_type: str | None = None,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if not payload.get("success", False):
                raise RuntimeError(f"Cloudflare API error: {payload.get('errors')}")
            return payload
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {err.code} ({method} {url}):\n{body}") from err


def build_multipart_body(metadata: dict, worker_code: bytes) -> tuple[bytes, str]:
    boundary = f"----NougenTubeBoundary{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts = [
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="metadata"; filename="metadata.json"',
        b"Content-Type: application/json",
        b"",
        json.dumps(metadata).encode("utf-8"),
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="worker.js"; filename="worker.js"',
        b"Content-Type: application/javascript+module",
        b"",
        worker_code,
        f"--{boundary}--".encode(),
        b"",
    ]
    return crlf.join(parts), f"multipart/form-data; boundary={boundary}"


def _fetch_upstream_bindings(token: str) -> dict[str, str]:
    """Read plain_text bindings from nougen-fleet-mcp so no operator hosts are hardcoded."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/workers/scripts/nougen-fleet-mcp/bindings"
    out: dict[str, str] = {}
    try:
        res = cf_request(url, token).get("result", [])
        for b in res:
            if b.get("type") == "plain_text" and b.get("name") and b.get("text"):
                out[b["name"]] = b["text"]
    except Exception:
        pass
    return out


def main() -> None:
    token = keymaker.get_secret("CLOUDFLARE_API_TOKEN_NOUGEN_FULL").strip()
    fleet_key = (keymaker.get_secret("FLEET_KEY") or "").strip()
    ngs_node_token = (keymaker.get_secret("NGS_NODE_TOKEN") or "").strip()
    nvidia_key = (
        keymaker.get_secret("NVIDIA_API_KEY") or keymaker.get_secret("NVIDIA_API_KEY_20261110") or ""
    ).strip()

    upstream_vars = _fetch_upstream_bindings(token)
    zone_name = upstream_vars.get("PROVISION_ZONE_NAME") or _resolve_domain_root()
    hostname = os.environ.get("NOUGEN_TUBE_HOSTNAME") or (f"tube.{zone_name}" if zone_name else "")
    whoart_origin = upstream_vars.get("WHOART_ORIGIN") or os.environ.get("WHOART_ORIGIN", "")
    oauth_upstream = upstream_vars.get("GOOGLE_REDIRECT_ORIGIN") or os.environ.get("OAUTH_UPSTREAM", "")
    allowed_emails = upstream_vars.get("GOOGLE_ALLOWED_EMAILS") or os.environ.get("GOOGLE_ALLOWED_EMAILS", "")

    worker_code = WORKER_JS.read_bytes()

    bindings = [
        {"type": "plain_text", "name": "SHARD_GATEWAY_URL", "text": whoart_origin},
        {"type": "plain_text", "name": "WHOART_ORIGIN", "text": whoart_origin},
        {"type": "plain_text", "name": "REQUIRE_AUTH", "text": "true"},
        {"type": "plain_text", "name": "OAUTH_UPSTREAM", "text": oauth_upstream},
        {"type": "plain_text", "name": "GOOGLE_ALLOWED_EMAILS", "text": allowed_emails},
        {
            "type": "plain_text",
            "name": "NVIDIA_BASE_URL",
            "text": "https://integrate.api.nvidia.com/v1/chat/completions",
        },
    ]
    if fleet_key:
        bindings.append({"type": "secret_text", "name": "NOUGEN_TUBE_TOKEN", "text": fleet_key})
    if ngs_node_token:
        bindings.append({"type": "secret_text", "name": "SHARD_GATEWAY_TOKEN", "text": ngs_node_token})
    if nvidia_key:
        bindings.append({"type": "secret_text", "name": "NVIDIA_API_KEY", "text": nvidia_key})

    metadata = {
        "main_module": "worker.js",
        "compatibility_date": COMPATIBILITY_DATE,
        "bindings": bindings,
    }
    body, content_type = build_multipart_body(metadata, worker_code)
    script_url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/workers/scripts/{SCRIPT_NAME}"
    res = cf_request(script_url, token, method="PUT", data=body, content_type=content_type)
    print(f"[1/2] Uploaded Worker '{SCRIPT_NAME}': id={res.get('result', {}).get('id')}")

    if hostname:
        domain_url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/workers/domains/records"
        domain_payload = json.dumps(
            {
                "zone_id": ZONE_ID,
                "hostname": hostname,
                "service": SCRIPT_NAME,
                "environment": "production",
            }
        ).encode("utf-8")
        dom_res = cf_request(domain_url, token, method="PUT", data=domain_payload, content_type="application/json")
        print(f"[2/2] Bound Custom Domain '{hostname}' -> '{SCRIPT_NAME}': {dom_res.get('result', {}).get('hostname')}")


if __name__ == "__main__":
    main()
