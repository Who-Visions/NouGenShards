#!/usr/bin/env python3
"""
NouGen Fleet Cloudflare Manager (Wrangler Fleet).
Automates Cloudflare Workers, KV, D1, R2, Secrets, and Workers AI via Keymaker DPAPI credentials.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from nougen_shards import keymaker
except ImportError:
    keymaker = None

TOKEN_KEY = "CLOUDFLARE_API_TOKEN_NOUGEN_FULL"
CF_API = "https://api.cloudflare.com/client/v4"

def get_auth_token():
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token and keymaker:
        token = keymaker.get_secret(TOKEN_KEY)
    return token

def cf_request(endpoint: str, method: str = "GET", data: dict = None, token: str = None) -> dict:
    if not token:
        token = get_auth_token()
    if not token:
        raise RuntimeError("No Cloudflare API token found in environment or Keymaker.")
    
    url = f"{CF_API}{endpoint}" if endpoint.startswith("/") else endpoint
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "NouGen-Fleet-Wrangler/1.0"
    }
    
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(err_content)
        except Exception:
            return {"success": False, "error": f"HTTP {e.code}: {err_content}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def resolve_account(token: str):
    res = cf_request("/accounts", token=token)
    if res.get("success") and res.get("result"):
        acc = res["result"][0]
        return acc["id"], acc.get("name", "unnamed")
    raise RuntimeError(f"Could not resolve Cloudflare account: {res.get('errors')}")

def list_workers(account_id: str, token: str):
    res = cf_request(f"/accounts/{account_id}/workers/scripts", token=token)
    if not res.get("success"):
        print(f"Error listing workers: {res.get('errors')}")
        return
    scripts = res.get("result", [])
    print(f"⚡ Cloudflare Workers ({len(scripts)} active on account):")
    for s in scripts:
        modified = (s.get("modified_on") or "")[:19].replace("T", " ")
        usage_model = s.get("usage_model", "bundled")
        print(f"  • {s.get('id'):<25} | modified: {modified} | usage: {usage_model}")

def list_secrets(account_id: str, script_name: str, token: str):
    res = cf_request(f"/accounts/{account_id}/workers/scripts/{script_name}/secrets", token=token)
    if not res.get("success"):
        print(f"Error listing secrets for {script_name}: {res.get('errors')}")
        return
    secrets = res.get("result", [])
    print(f"🔐 Secrets for Worker [{script_name}] ({len(secrets)} found):")
    for s in secrets:
        print(f"  • {s.get('name')} (type: {s.get('type')})")

def put_secret(account_id: str, script_name: str, secret_name: str, secret_val: str, token: str):
    payload = {"name": secret_name, "text": secret_val, "type": "secret_text"}
    res = cf_request(f"/accounts/{account_id}/workers/scripts/{script_name}/secrets", method="PUT", data=payload, token=token)
    if res.get("success"):
        print(f"✅ Secret [{secret_name}] successfully written to [{script_name}].")
    else:
        print(f"❌ Failed to write secret: {res.get('errors')}")

def list_d1(account_id: str, token: str):
    res = cf_request(f"/accounts/{account_id}/d1/database", token=token)
    if not res.get("success"):
        print(f"Error listing D1 databases: {res.get('errors')}")
        return
    dbs = res.get("result", [])
    print(f"🗄️ Cloudflare D1 Serverless SQL Databases ({len(dbs)} found):")
    for d in dbs:
        print(f"  • {d.get('name'):<20} | uuid: {d.get('uuid')} | ver: {d.get('version')}")

def list_kv(account_id: str, token: str):
    res = cf_request(f"/accounts/{account_id}/storage/kv/namespaces", token=token)
    if not res.get("success"):
        print(f"Error listing KV namespaces: {res.get('errors')}")
        return
    kvs = res.get("result", [])
    print(f"📦 Cloudflare KV Namespaces ({len(kvs)} found):")
    for k in kvs:
        print(f"  • {k.get('title'):<25} | id: {k.get('id')}")

def list_r2(account_id: str, token: str):
    res = cf_request(f"/accounts/{account_id}/r2/buckets", token=token)
    if not res.get("success"):
        print(f"Error listing R2 buckets: {res.get('errors')}")
        return
    buckets = res.get("result", {}).get("buckets", [])
    print(f"🪣 Cloudflare R2 Buckets ({len(buckets)} found):")
    for b in buckets:
        print(f"  • {b.get('name'):<25} | created: {b.get('creation_date', '')[:10]}")

def run_ai(account_id: str, prompt: str, model: str = "@cf/meta/llama-3.1-8b-instruct", token: str = None):
    print(f"🤖 Invoking Workers AI Edge Model [{model}]...")
    payload = {"prompt": prompt}
    res = cf_request(f"/accounts/{account_id}/ai/run/{model}", method="POST", data=payload, token=token)
    if res.get("success"):
        resp_text = res.get("result", {}).get("response", "")
        print(f"\n--- Edge Inference Response ---\n{resp_text}\n------------------------------")
    else:
        print(f"❌ Workers AI Inference Error: {res.get('errors')}")

def deploy_worker(account_id: str, script_name: str, script_path: Path, token: str):
    print(f"🚀 Deploying [{script_name}] from {script_path.name}...")
    code = script_path.read_bytes()
    boundary = "----WebKitFormBoundaryFleetDeploy"
    metadata = json.dumps({"main_module": "worker.js"}).encode("utf-8")

    body = bytearray()
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n".encode())
    body.extend(metadata)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"worker.js\"; filename=\"worker.js\"\r\nContent-Type: application/javascript+module\r\n\r\n".encode())
    body.extend(code)
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    url = f"{CF_API}/accounts/{account_id}/workers/scripts/{script_name}/content"
    req_put = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="PUT",
    )

    try:
        with urllib.request.urlopen(req_put, timeout=60) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("success"):
                etag = res.get("result", {}).get("etag", "unknown")
                print(f"✅ Deployment SUCCESS! ETag: {etag}")
            else:
                print(f"❌ Deploy FAILED: {res.get('errors')}")
    except Exception as e:
        print(f"❌ HTTP Deployment Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="NouGen Fleet Cloudflare Wrangler CLI Suite")
    parser.add_argument("--status", action="store_true", help="Display Cloudflare account & token status")
    parser.add_argument("--list", action="store_true", help="List all deployed Workers")
    parser.add_argument("--d1", action="store_true", help="List Cloudflare D1 databases")
    parser.add_argument("--kv", action="store_true", help="List Cloudflare KV namespaces")
    parser.add_argument("--r2", action="store_true", help="List Cloudflare R2 buckets")
    parser.add_argument("--secrets", type=str, metavar="WORKER", help="List secrets on a Worker")
    parser.add_argument("--secret-put", nargs=3, metavar=("WORKER", "NAME", "VAL"), help="Put a secret on a Worker")
    parser.add_argument("--deploy", nargs=2, metavar=("WORKER", "PATH"), help="Deploy a worker from local path")
    parser.add_argument("--ai", type=str, metavar="PROMPT", help="Run prompt on Workers AI Edge (Llama 3.1 8B)")

    args = parser.parse_args()

    token = get_auth_token()
    if not token:
        print("Error: CLOUDFLARE_API_TOKEN_NOUGEN_FULL missing from Keymaker.")
        sys.exit(1)

    account_id, account_name = resolve_account(token)

    if args.status:
        print("=== Cloudflare Fleet Status ===")
        print(f"Account: {account_name} ({account_id})")
        print("Token:   Valid (Keymaker DPAPI Vault)")
        return

    if args.list:
        list_workers(account_id, token)
        return

    if args.d1:
        list_d1(account_id, token)
        return

    if args.kv:
        list_kv(account_id, token)
        return

    if args.r2:
        list_r2(account_id, token)
        return

    if args.secrets:
        list_secrets(account_id, args.secrets, token)
        return

    if args.secret_put:
        w_name, s_name, s_val = args.secret_put
        put_secret(account_id, w_name, s_name, s_val, token)
        return

    if args.deploy:
        w_name, w_path = args.deploy
        deploy_worker(account_id, w_name, Path(w_path), token)
        return

    if args.ai:
        run_ai(account_id, args.ai, token=token)
        return

    parser.print_help()

if __name__ == "__main__":
    main()
