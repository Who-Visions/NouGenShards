import urllib.request, json
from nougen_shards.keymaker import get_secret

cf = get_secret('CLOUDFLARE_API_TOKEN_NOUGEN_FULL')
acct = '0d4ac187acceea4d9692619097927d1e'
blade_id = '1f830bb9-1b73-490c-b525-b75089ac6316'

req = urllib.request.Request(
    "https://api.cloudflare.com/client/v4/accounts/{}/cfd_tunnel/{}".format(acct, blade_id),
    headers={"Authorization": "Bearer " + cf}
)
with urllib.request.urlopen(req) as resp:
    t = json.loads(resp.read())["result"]
    print("Name:", t["name"])
    print("Status:", t["status"])
    conns = t.get("connections", [])
    for c in conns:
        print("  conn:", c.get("colo_name", "?"), "opened=", c.get("opened_at", "?"))
    if not conns:
        print("  NO ACTIVE CONNECTIONS")

# Also check DNS
import socket
try:
    ip = socket.gethostbyname("blade.nougenai.com")
    print("DNS blade.nougenai.com ->", ip)
except Exception as e:
    print("DNS error:", e)
