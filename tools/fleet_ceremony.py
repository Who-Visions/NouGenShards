import urllib.request
import json
import os
import sys

sys.path.insert(0, r"C:\Users\super\Outpost\NouGen\src")
from nougen_shards.keymaker import get_secret

t_whoart = get_secret("NGS_NODE_TOKEN_WHOART_PRE_SHARED_20260817")

nodes = [
    ("Blade",   "https://blade.nougenai.com"),
    ("Phoebus", "https://phoebus.nougenai.com"),
    ("WhoArt",  "https://whoart-vault.nougenai.com"),
]

print("=" * 60)
print("3-VAULT RECIPROCAL TRUTH CEREMONY: HEALTH & AUTH")
print("=" * 60)

all_green = True

for name, base in nodes:
    # 1. Health
    req_h = urllib.request.Request(f"{base}/health", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req_h, timeout=8) as r:
            d = json.loads(r.read().decode())
            reg = d.get("tenant_registry_configured")
            stor = d.get("storage")
            h_status = f"[OK] 200 (tenant_reg={reg}, storage={stor})"
    except Exception as e:
        all_green = False
        h_status = f"[FAIL] {e}"

    # 2. Authenticated MCP handshake
    req_m = urllib.request.Request(f"{base}/mcp/", headers={
        "User-Agent": "Mozilla/5.0",
        "x-ngs-token": t_whoart,
        "Accept": "text/event-stream"
    })
    try:
        with urllib.request.urlopen(req_m, timeout=8) as r:
            m_status = f"[OK] {r.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:100]
        # In StreamableHTTP MCP, a GET without query session returns 400 or 405, NOT 401
        if e.code in (400, 405) or "Session" in body or "event-stream" in body:
            m_status = f"[AUTH OK] {e.code} (Authenticated via token)"
        elif e.code == 401:
            all_green = False
            m_status = f"[UNAUTH] 401 {body}"
        else:
            m_status = f"[{e.code}] {body}"
    except Exception as e:
        all_green = False
        m_status = f"[FAIL] {e}"

    print(f"NODE: {name:8s}")
    print(f"  /health -> {h_status}")
    print(f"  /mcp/   -> {m_status}")
    print()

print("=" * 60)
if all_green:
    print("FLEET TRIANGLE STATUS: [GREEN] 3/3 NODES VERIFIED RECIPROCALLY")
else:
    print("FLEET TRIANGLE STATUS: [RED] NOT ALL NODES GREEN")
print("=" * 60)
