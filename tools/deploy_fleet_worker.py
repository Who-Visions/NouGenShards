"""Upload .fleet_worker.js (or --file) to the nougen-fleet-mcp Cloudflare Worker.

Pure deployer: no in-flight patching (unlike patch_and_deploy_worker.py).
keep_bindings preserves every existing var/secret/namespace, so code deploys
never touch identity or credentials. Rollback = rerun with --file pointing at
a dated backup in nougen-worker-backups/.
"""
import argparse
import json
import os
import ssl
import sys
import urllib.request

sys.path.insert(0, "src")
from nougen_shards import keymaker  # noqa: E402

DEFAULT_SCRIPT = os.environ.get("NOUGEN_FLEET_WORKER_SCRIPT", "nougen-fleet-mcp")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=".fleet_worker.js")
    ap.add_argument("--script", default=DEFAULT_SCRIPT)
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        js = f.read()

    token = keymaker.get_secret("CLOUDFLARE_API_TOKEN_NOUGEN_FULL") or keymaker.get_secret(
        "CLOUDFLARE_API_TOKEN")
    account_id = keymaker.get_secret("CLOUDFLARE_ACCOUNT_ID") or os.environ.get(
        "CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not account_id:
        print("missing CLOUDFLARE_API_TOKEN*/CLOUDFLARE_ACCOUNT_ID in keymaker/env")
        return 2

    metadata = {
        "main_module": "worker.js",
        "keep_bindings": ["plain_text", "secret_text", "kv_namespace", "service",
                          "r2_bucket", "d1"],
    }
    boundary = "----NouGenDeploy" + os.urandom(8).hex()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="metadata"\r\n'
        f"Content-Type: application/json\r\n\r\n{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
        f"Content-Type: application/javascript+module\r\n\r\n{js}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    url = (f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
           f"/workers/scripts/{args.script}")
    req = urllib.request.Request(url, data=body, method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    with urllib.request.urlopen(req, context=ssl.create_default_context(),
                                timeout=60) as r:
        res = json.loads(r.read())
    print("success:", res.get("success"), "errors:", res.get("errors", []))
    return 0 if res.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
