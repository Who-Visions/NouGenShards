import sys, json, uuid
import urllib.request, urllib.error
sys.path.insert(0, r'C:\Users\super\Outpost\NouGen\src')
from nougen_shards import keymaker

token = keymaker.get_secret('CLOUDFLARE_API_TOKEN_NOUGEN_FULL').strip()
acct_id = '0d4ac187acceea4d9692619097927d1e'
script_name = 'nougen-fleet-mcp'
zone_id = '0d43ea57e3b800e4f75123b1e72bc45f'

# 1. Fetch current bindings to preserve them
print("Fetching current bindings for", script_name)
req = urllib.request.Request(
    f'https://api.cloudflare.com/client/v4/accounts/{acct_id}/workers/scripts/{script_name}/bindings',
    headers={'Authorization': f'Bearer {token}'}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    bindings_raw = data.get('result', [])

plain_bindings = []
for b in bindings_raw:
    if b.get('type') == 'plain_text':
        val = b.get('text')
        if b.get('name') == 'SHARD_GATEWAY_URL' and 'shards.nougenai.com' in val:
            val = 'https://blade.nougenai.com'
        plain_bindings.append({
            'type': 'plain_text',
            'name': b.get('name'),
            'text': val
        })

print(f"Preserving {len(plain_bindings)} plain_text bindings and keeping secret_text bindings")

# 2. Build metadata
metadata = {
    'main_module': 'worker.js',
    'compatibility_date': '2026-08-01',
    'bindings': plain_bindings,
    'keep_bindings': ['secret_text']
}

# 3. Read patched worker.js
worker_path = r'C:\Users\super\Outpost\NouGen\tools\nougen-fleet-mcp-patched.js'
with open(worker_path, 'r', encoding='utf-8') as f:
    worker_content = f.read()

# 4. Prepare multipart body
boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
body_parts = []

# Part 1: metadata
body_parts.append(f"--{boundary}\r\n".encode('utf-8'))
body_parts.append(b'Content-Disposition: form-data; name="metadata"\r\n')
body_parts.append(b'Content-Type: application/json\r\n\r\n')
body_parts.append(json.dumps(metadata, indent=2).encode('utf-8'))
body_parts.append(b'\r\n')

# Part 2: worker.js
body_parts.append(f"--{boundary}\r\n".encode('utf-8'))
body_parts.append(b'Content-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n')
body_parts.append(b'Content-Type: application/javascript+module\r\n\r\n')
body_parts.append(worker_content.encode('utf-8'))
body_parts.append(b'\r\n')

# Closing boundary
body_parts.append(f"--{boundary}--\r\n".encode('utf-8'))

body_bytes = b''.join(body_parts)

print(f"Deploying worker script {script_name} ({len(body_bytes)} bytes)...")
put_url = f'https://api.cloudflare.com/client/v4/accounts/{acct_id}/workers/scripts/{script_name}'
put_req = urllib.request.Request(
    put_url,
    data=body_bytes,
    headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    },
    method='PUT'
)

try:
    with urllib.request.urlopen(put_req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print("Worker script upload success:", res.get('success'))
except urllib.error.HTTPError as e:
    print("Upload failed:", e.code, e.read().decode('utf-8'))
    sys.exit(1)

# 5. Ensure worker routes for /sse* exist on zone nougenai.com
print("Checking worker routes on zone nougenai.com...")
routes_req = urllib.request.Request(
    f'https://api.cloudflare.com/client/v4/zones/{zone_id}/workers/routes',
    headers={'Authorization': f'Bearer {token}'}
)
with urllib.request.urlopen(routes_req) as resp:
    existing_routes = json.loads(resp.read().decode('utf-8')).get('result', [])

existing_patterns = {r.get('pattern') for r in existing_routes}

desired_patterns = [
    'shards.nougenai.com/sse*',
    'mcp.nougenai.com/sse*',
    'ngs.nougenai.com/sse*'
]

for pat in desired_patterns:
    if pat not in existing_patterns:
        print(f"Adding route: {pat} -> {script_name}")
        add_req = urllib.request.Request(
            f'https://api.cloudflare.com/client/v4/zones/{zone_id}/workers/routes',
            data=json.dumps({'pattern': pat, 'script': script_name}).encode('utf-8'),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(add_req) as resp:
                add_res = json.loads(resp.read().decode('utf-8'))
                print(f"Route {pat} created:", add_res.get('success'))
        except urllib.error.HTTPError as e:
            print(f"Failed to create route {pat}:", e.code, e.read().decode('utf-8'))
    else:
        print(f"Route {pat} already exists")

print("\nDeployment complete!")
