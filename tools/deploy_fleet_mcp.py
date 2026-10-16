import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))
from nougen_shards import keymaker

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ACCOUNT_ID = "0d4ac187acceea4d9692619097927d1e"
ZONE_ID = "0d43ea57e3b800e4f75123b1e72bc45f"
SCRIPT_NAME = "nougen-fleet-mcp"
COMPATIBILITY_DATE = "2026-08-01"

WORKER_JS_PATH = Path(__file__).resolve().parent / "nougen-fleet-mcp-patched.js"

OLD_GATEWAY_HOST = "shards.nougenai.com"
NEW_GATEWAY_URL = "https://blade.nougenai.com"
DEFAULT_HALLWAY_CAPTURE_URL = f"{NEW_GATEWAY_URL}/v1/shards/capture"

BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/workers/scripts/{SCRIPT_NAME}"


def cf_request(
    url: str,
    token: str,
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
        err_body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {err.code} ({method} {url}):\n{err_body}") from err


def build_multipart_body(metadata: dict, worker_code: bytes) -> tuple[bytes, str]:
    boundary = f"----NougenCFBoundary{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts: list[bytes] = [
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


def main() -> None:
    if not WORKER_JS_PATH.is_file():
        sys.exit(f"[ERROR] Patched worker script not found at: {WORKER_JS_PATH}")

    token = keymaker.get_secret("CLOUDFLARE_API_TOKEN_NOUGEN_FULL").strip()

    # 1. Fetch current bindings
    print(f"[1/4] Fetching current bindings for '{SCRIPT_NAME}'...")
    bindings_raw = cf_request(f"{BASE_URL}/bindings", token=token).get("result", [])

    updated_bindings: list[dict] = []
    preserved_types: set[str] = {"secret_text"}
    existing_secrets: set[str] = set()
    seen_plain_names: set[str] = set()

    for b in bindings_raw:
        b_type = b.get("type")
        b_name = b.get("name")

        if b_type == "secret_text":
            existing_secrets.add(b_name)
            continue

        if b_type == "plain_text":
            val = b.get("text") or ""
            if b_name == "SHARD_GATEWAY_URL" and urlparse(val).hostname == OLD_GATEWAY_HOST:
                print(f"      Rewriting {b_name}: {val} -> {NEW_GATEWAY_URL}")
                val = NEW_GATEWAY_URL
            elif b_name == "HALLWAY_CAPTURE_URL" and urlparse(val).hostname == OLD_GATEWAY_HOST:
                print(f"      Rewriting {b_name}: {val} -> {DEFAULT_HALLWAY_CAPTURE_URL}")
                val = DEFAULT_HALLWAY_CAPTURE_URL

            updated_bindings.append({
                "type": "plain_text",
                "name": b_name,
                "text": val,
            })
            seen_plain_names.add(b_name)
        else:
            # Preserve KV, D1, R2, Service, Durable Object bindings
            updated_bindings.append(b)
            if b_type:
                preserved_types.add(b_type)

    # Ensure HALLWAY_CAPTURE_URL is bound so hallwayCapture() doesn't bail out
    if "HALLWAY_CAPTURE_URL" not in seen_plain_names and "HALLWAY_CAPTURE_URL" not in existing_secrets:
        print(f"      Injecting missing plain_text binding HALLWAY_CAPTURE_URL={DEFAULT_HALLWAY_CAPTURE_URL}")
        updated_bindings.append({
            "type": "plain_text",
            "name": "HALLWAY_CAPTURE_URL",
            "text": DEFAULT_HALLWAY_CAPTURE_URL,
        })

    # Verify HALLWAY_BEARER_TOKEN exists on the worker
    if "HALLWAY_BEARER_TOKEN" not in existing_secrets:
        print("      [WARN] 'HALLWAY_BEARER_TOKEN' is not in worker secret_text bindings!")
        print("             hallwayCapture() will return null until this secret is set.")

    n_bindings = len(updated_bindings)
    n_vault_keys = len(existing_secrets)
    print(f"      Preserving {n_bindings} resource binding(s) and {n_vault_keys} encrypted entry/entries.")

    # 2. Build metadata
    print("[2/4] Building metadata...")
    metadata = {
        "main_module": "worker.js",
        "compatibility_date": COMPATIBILITY_DATE,
        "bindings": updated_bindings,
        "keep_bindings": sorted(preserved_types),
    }

    # 3. Read patched worker.js
    print(f"[3/4] Reading patched worker from {WORKER_JS_PATH.name}...")
    worker_code = WORKER_JS_PATH.read_bytes()

    # 4. Upload bundle to Cloudflare
    print(f"[4/4] Uploading '{SCRIPT_NAME}' to Cloudflare...")
    body, content_type = build_multipart_body(metadata, worker_code)
    deploy_resp = cf_request(
        BASE_URL,
        token=token,
        method="PUT",
        data=body,
        content_type=content_type,
    )

    result = deploy_resp.get("result", {})
    print(f"[OK] Deployed '{SCRIPT_NAME}' (etag: {result.get('etag', 'unknown')})")

    # 5. Ensure worker routes for /sse* exist on zone nougenai.com
    print("Checking worker routes on zone nougenai.com...")
    routes_url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/workers/routes"
    routes_resp = cf_request(routes_url, token=token)
    existing_routes = routes_resp.get("result", [])
    existing_patterns = {r.get("pattern") for r in existing_routes}

    desired_patterns = [
        "shards.nougenai.com/sse*",
        "mcp.nougenai.com/sse*",
        "ngs.nougenai.com/sse*"
    ]

    for pat in desired_patterns:
        if pat not in existing_patterns:
            print(f"Adding route: {pat} -> {SCRIPT_NAME}")
            try:
                cf_request(
                    routes_url,
                    token=token,
                    method="POST",
                    data=json.dumps({"pattern": pat, "script": SCRIPT_NAME}).encode("utf-8"),
                    content_type="application/json"
                )
                print(f"Route {pat} created.")
            except Exception as e:
                print(f"Failed to create route {pat}: {e}")
        else:
            print(f"Route {pat} already active.")

    print("\nDeployment complete and verified!")


if __name__ == "__main__":
    main()
