import urllib.request, json

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def probe(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()[:400]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return 0, str(e)

nodes = [
    ("Blade",   "https://blade.nougenai.com/health"),
    ("Phoebus", "https://phoebus.nougenai.com/health"),
    ("WhoArt",  "https://whoart-vault.nougenai.com/health"),
]

up = 0
for name, url in nodes:
    s, body = probe(url)
    tag = "[OK]" if s == 200 else "[FAIL]"
    if s == 200:
        up += 1
    print(f"  {tag} [{name}] {url} -> {s}")
    if s == 200:
        try:
            d = json.loads(body)
            ts = d.get("total_shards", "?")
            tc = d.get("node_token_configured", "?")
            print(f"      shards={ts}, token_configured={tc}")
        except Exception:
            pass

print(f"=== FLEET TRIANGLE: {up}/3 UP ===")
if up == 3:
    print("[GREEN] ALL THREE NODES ONLINE AS EQUAL PEERS")
else:
    print(f"[RED] {3 - up} NODE(S) STILL DOWN")
