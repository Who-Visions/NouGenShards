import sys
sys.path.insert(0, 'src')
import urllib.request, json, ssl, os
from nougen_shards import keymaker

def main():
    with open(r'.fleet_worker.js', 'r', encoding='utf-8') as f:
        js = f.read()

    token = keymaker.get_secret('CLOUDFLARE_API_TOKEN_NOUGEN_FULL') or keymaker.get_secret('CLOUDFLARE_API_TOKEN')
    account_id = '0d4ac187acceea4d9692619097927d1e'
    ctx = ssl.create_default_context()

    # In Cloudflare API, keep_bindings takes binding types
    metadata = {
        "main_module": "worker.js",
        "keep_bindings": ["plain_text", "secret_text", "kv_namespace", "service", "r2_bucket", "d1"]
    }

    boundary = "----WebKitFormBoundaryNouGenDeploy" + os.urandom(8).hex()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="metadata"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
        f"Content-Type: application/javascript+module\r\n\r\n"
        f"{js}\r\n"
        f"--{boundary}--\r\n"
    ).encode('utf-8')

    url_put = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/nougen-fleet-mcp'
    req_put = urllib.request.Request(
        url_put,
        data=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': f'multipart/form-data; boundary={boundary}'
        },
        method='PUT'
    )

    print("Uploading updated worker to Cloudflare...")
    try:
        with urllib.request.urlopen(req_put, context=ctx, timeout=30) as r:
            res = json.loads(r.read())
            print("Upload Result:", res.get("success"), res.get("errors", []))
            if res.get("success"):
                print("Successfully deployed nougen-fleet-mcp to Cloudflare!")
                return 0
            else:
                print("Deploy failed:", res)
                return 1
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        err_body = e.read().decode('utf-8', errors='replace')
        print("Response Body:", err_body)
        return 1

if __name__ == '__main__':
    sys.exit(main())
