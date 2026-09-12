"""Full fleet triangle detail: shard counts, token status, MCP endpoints."""
import urllib.request, json

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
NGS_TOKEN = "296b2d2802b9803fe73f8795b4873489e4b33cf293cc7ab942f660e89f39e90b"

def probe(url, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return 0, str(e)

nodes = [
    ("Blade",   "https://blade.nougenai.com"),
    ("Phoebus", "https://phoebus.nougenai.com"),
    ("WhoArt",  "https://whoart-vault.nougenai.com"),
]

print("=" * 60)
print("FLEET TRIANGLE 3-VAULT STATUS")
print("=" * 60)

all_up = True
for name, base in nodes:
    s, body = probe(base + "/health")
    if s == 200:
        try:
            d = json.loads(body)
            shards = d.get("total_shards", "?")
            token = d.get("node_token_configured", "?")
            storage = d.get("storage", "?")
            print(f"  [OK] {name:8s} | {base} | shards={shards} | token={token} | storage={storage}")
        except Exception:
            print(f"  [OK] {name:8s} | {base} | 200 (parse error)")
    else:
        all_up = False
        print(f"  [FAIL] {name:8s} | {base} | status={s}")

print()

# MCP endpoint check (token-gated)
print("MCP ENDPOINT CHECK:")
for name, base in nodes:
    mcp_url = base + "/mcp/"
    s, body = probe(mcp_url, {"x-ngs-token": NGS_TOKEN, "Accept": "application/json"})
    tag = "[OK]" if s in (200, 405) else "[FAIL]"
    print(f"  {tag} {name:8s} /mcp/ -> {s}")

print()
if all_up:
    print("RESULT: ALL THREE NODES ONLINE AS EQUAL PEERS")
else:
    print("RESULT: NOT ALL NODES UP")
