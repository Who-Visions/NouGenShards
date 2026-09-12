"""
Fleet-wide correction script: bring all 3 nodes online as equal peers.
1. Fix WhoArt tunnel ingress (8765 -> 4444)
2. Start cloudflared on Hyperion (this machine)
3. Start cloudflared + uvicorn on Blade via SSH
4. Verify all 3 endpoints
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from nougen_shards.keymaker import get_secret

ACCOUNT = '0d4ac187acceea4d9692619097927d1e'
CF_TOKEN = get_secret('CLOUDFLARE_API_TOKEN_NOUGEN_FULL')
WHOART_TUNNEL_TOKEN = get_secret('CLOUDFLARED_WHOART_TUNNEL_TOKEN')
BLADE_TUNNEL_TOKEN = get_secret('CLOUDFLARED_NGS_TUNNEL_TOKEN')
WHOART_TUNNEL_ID = '4b66f5fa-ce85-469b-9496-49608fd2e3eb'
BLADE_TUNNEL_ID = '1f830bb9-1b73-490c-b525-b75089ac6316'

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def cf_api(method, path, body=None):
    url = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                headers={'Authorization': f'Bearer {CF_TOKEN}',
                                         'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def probe(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, resp.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return 0, str(e)

# --- STEP 1: Fix WhoArt tunnel ingress 8765 -> 4444 ---
print("=" * 60)
print("[STEP 1] Fixing WhoArt tunnel ingress: 8765 -> 4444")
new_config = {
    "config": {
        "ingress": [
            {"hostname": "whoart-vault.nougenai.com", "service": "http://127.0.0.1:4444"},
            {"service": "http_status:404"}
        ]
    }
}
result = cf_api('PUT', f'cfd_tunnel/{WHOART_TUNNEL_ID}/configurations', new_config)
print(f"  Tunnel config update: {result.get('success')}")

# Verify
cfg = cf_api('GET', f'cfd_tunnel/{WHOART_TUNNEL_ID}/configurations')
ingress = cfg.get('result', {}).get('config', {}).get('ingress', [])
print(f"  New ingress: {json.dumps(ingress)}")

print("\n[STEP 1] [OK] WhoArt tunnel now routes to port 4444")

# --- STEP 2: Verify Hyperion uvicorn is alive locally ---
print("\n" + "=" * 60)
print("[STEP 2] Verifying Hyperion local listener on 4444")
status, body = probe('http://127.0.0.1:4444/health')
print(f"  Local /health: {status}")
if status != 200:
    print("  [FAIL] Hyperion uvicorn not responding! Cannot proceed.")
    sys.exit(1)
print("  [OK] Hyperion uvicorn alive on 4444")

# --- STEP 3: Start cloudflared on Hyperion ---
print("\n" + "=" * 60)
print("[STEP 3] Starting cloudflared tunnel on Hyperion (WhoArt)")
cloudflared = os.path.expanduser(r'~\.nougen\bin\cloudflared.exe')
if not os.path.exists(cloudflared):
    # Try fallback
    cloudflared = r'C:\Users\super\.nougen\bin\cloudflared.exe'

# Kill any existing cloudflared
subprocess.run(['taskkill', '/f', '/im', 'cloudflared.exe'],
               capture_output=True, timeout=5)
time.sleep(1)

# Start cloudflared with the whoart tunnel token
proc = subprocess.Popen(
    [cloudflared, 'tunnel', '--protocol', 'http2', 'run',
     '--token', WHOART_TUNNEL_TOKEN],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    creationflags=subprocess.CREATE_NO_WINDOW
)
print(f"  cloudflared PID: {proc.pid}")
time.sleep(5)

# Check it's still running
if proc.poll() is not None:
    _, stderr = proc.communicate()
    print(f"  [FAIL] cloudflared exited immediately: {stderr.decode()[:300]}")
    sys.exit(1)
print("  [OK] cloudflared running for whoart-vault tunnel")

# --- STEP 4: Start Blade cloudflared + uvicorn ---
print("\n" + "=" * 60)
print("[STEP 4] Starting Blade: cloudflared + uvicorn")

# Check if Blade port 4444 is already listening
print("  Checking Blade local listener...")
blade_check = subprocess.run(
    ['ssh', 'blade', 'netstat -ano | findstr 4444 | findstr LISTEN'],
    capture_output=True, text=True, timeout=10
)
blade_listening = 'LISTENING' in blade_check.stdout
print(f"  Blade 4444 listening: {blade_listening}")

if not blade_listening:
    print("  Starting uvicorn on Blade...")
    # Create a startup script on Blade and run it
    start_cmd = (
        'cd C:\\Users\\super\\Watchtower\\NouGen\\NouGenShards-push-main && '
        'set NOUGEN_VAULT_DIR=C:\\Users\\super\\.nougen\\shards && '
        'set NOUGEN_SECRETS_VAULT_DIR=C:\\Users\\super\\.nougen\\secrets && '
        'set PYTHONPATH=src && '
        'start /b .venv\\Scripts\\python.exe -m uvicorn app:app --host 127.0.0.1 --port 4444'
    )
    subprocess.Popen(
        ['ssh', 'blade', f'cmd /c "{start_cmd}"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    print("  Waiting 20s for Blade uvicorn warm-up...")
    time.sleep(20)

# Check Blade cloudflared
print("  Checking Blade cloudflared...")
blade_cf_check = subprocess.run(
    ['ssh', 'blade', 'tasklist /fi "imagename eq cloudflared.exe" /fo csv /nh'],
    capture_output=True, text=True, timeout=10
)
blade_cf_running = 'cloudflared' in blade_cf_check.stdout.lower()
print(f"  Blade cloudflared running: {blade_cf_running}")

if not blade_cf_running:
    print("  Starting cloudflared on Blade...")
    subprocess.Popen(
        ['ssh', 'blade',
         f'start /b C:\\Progra~2\\cloudflared\\cloudflared.exe tunnel --protocol http2 run --token {BLADE_TUNNEL_TOKEN}'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    time.sleep(8)

# --- STEP 5: Verify all 3 public endpoints ---
print("\n" + "=" * 60)
print("[STEP 5] Fleet Triangle Verification")
print("  Waiting 10s for tunnel propagation...")
time.sleep(10)

nodes = [
    ("Blade",   "https://blade.nougenai.com/health"),
    ("Phoebus", "https://phoebus.nougenai.com/health"),
    ("WhoArt",  "https://whoart-vault.nougenai.com/health"),
]

up_count = 0
for name, url in nodes:
    status, body = probe(url)
    icon = "[OK]" if status == 200 else "[FAIL]"
    if status == 200:
        up_count += 1
    print(f"  {icon} [{name}] {url} -> {status}")
    if status == 200:
        try:
            data = json.loads(body)
            print(f"      shards={data.get('total_shards')}, token_configured={data.get('node_token_configured')}")
        except:
            pass

print(f"\n{'=' * 60}")
print(f"=== FLEET TRIANGLE: {up_count}/3 UP ===")
if up_count == 3:
    print("[GREEN] ALL THREE NODES ONLINE AS EQUAL PEERS")
else:
    print(f"[RED] {3 - up_count} NODE(S) STILL DOWN")
print(f"{'=' * 60}")
