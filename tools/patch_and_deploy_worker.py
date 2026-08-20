import sys
sys.path.insert(0, 'src')
import urllib.request, json, ssl, re, os
from nougen_shards import keymaker

def main():
    with open(r'.fleet_worker.js', 'r', encoding='utf-8') as f:
        js = f.read()

    # 1. Patch function text(t, structured) to strictly return { content: [{ type: "text", text: String(t) }] }
    old_text_fn = """function text(t, structured) {
  return {
    content: [{ type: "text", text: t }],
    ...structured !== void 0 ? { structuredContent: structured } : {}
  };
}"""

    new_text_fn = """function text(t, structured) {
  return {
    content: [{ type: "text", text: String(t) }]
  };
}"""

    if old_text_fn in js:
        js = js.replace(old_text_fn, new_text_fn)
        print("Patched text() function to remove non-standard structuredContent!")
    else:
        print("Note: old_text_fn not found or already patched")

    # 2. Patch handleRpc reply to guarantee id is always preserved properly
    old_handle_rpc_start = """async function handleRpc(msg, env, keyId) {
  const { id, method, params } = msg;
  const reply = /* @__PURE__ */ __name((result) => ({ jsonrpc: "2.0", id, result }), "reply");
  const fail = /* @__PURE__ */ __name((code, message) => ({ jsonrpc: "2.0", id, error: { code, message } }), "fail");"""

    new_handle_rpc_start = """async function handleRpc(msg, env, keyId) {
  const { id, method, params } = msg;
  const reqId = id !== undefined ? id : null;
  const reply = /* @__PURE__ */ __name((result) => ({ jsonrpc: "2.0", id: reqId, result }), "reply");
  const fail = /* @__PURE__ */ __name((code, message) => ({ jsonrpc: "2.0", id: reqId, error: { code, message } }), "fail");"""

    if old_handle_rpc_start in js:
        js = js.replace(old_handle_rpc_start, new_handle_rpc_start)
        print("Patched handleRpc id handling!")

    with open(r'.fleet_worker.js', 'w', encoding='utf-8') as f:
        f.write(js)

    # 3. Deploy to Cloudflare
    token = keymaker.get_secret('CLOUDFLARE_API_TOKEN_NOUGEN_FULL') or keymaker.get_secret('CLOUDFLARE_API_TOKEN')
    account_id = '0d4ac187acceea4d9692619097927d1e'
    ctx = ssl.create_default_context()

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

    print("Uploading hardened worker to Cloudflare...")
    with urllib.request.urlopen(req_put, context=ctx, timeout=30) as r:
        res = json.loads(r.read())
        print("Upload Result:", res.get("success"), res.get("errors", []))
        if res.get("success"):
            print("Successfully deployed hardened nougen-fleet-mcp to Cloudflare!")
            return 0
        else:
            return 1

if __name__ == '__main__':
    sys.exit(main())
