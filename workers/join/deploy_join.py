"""Deploy nougen-join and mint one setup link per tenant.

    python workers/join/deploy_join.py deploy
    python workers/join/deploy_join.py link <email> [--days 14]

Token comes from the keymaker (never printed). The worker is isolated: its own
script name and its own hostname join.<zone>; it only reads the TENANTS KV.
"""
import json
import pathlib
import secrets
import sys
import urllib.request
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from nougen_shards import tenant_onboard as t  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = "nougen-join"
ZONE_NAME = "nougenai.com"
HOST = "join." + ZONE_NAME


def cf():
    return t.Cloudflare(token=t._resolve_cf_token()) if hasattr(t, "Cloudflare") else _client()


def _client():
    import inspect
    cls = [c for _, c in inspect.getmembers(t, inspect.isclass)
           if "__init__" in c.__dict__ and "account_id" in inspect.signature(c.__init__).parameters][0]
    return cls(token=t._resolve_cf_token())


def deploy():
    c = _client()
    acct = c.account_id
    ns = t._find_namespace(c)
    meta = {"main_module": "worker.js", "compatibility_date": "2026-08-01",
            "bindings": [{"type": "kv_namespace", "name": "TENANTS", "namespace_id": ns}]}
    b = uuid.uuid4().hex
    parts = []
    for name, ctype, data in (("metadata", "application/json", json.dumps(meta).encode()),
                              ("worker.js", "application/javascript+module", (HERE / "worker.js").read_bytes())):
        fn = f'; filename="{name}"' if name != "metadata" else ""
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{name}"{fn}\r\nContent-Type: {ctype}\r\n\r\n'.encode() + data + b"\r\n")
    body = b"".join(parts) + f"--{b}--\r\n".encode()
    req = urllib.request.Request(f"{t.CF_API}/accounts/{acct}/workers/scripts/{SCRIPT}", data=body, method="PUT",
                                 headers={"Authorization": "Bearer " + t._resolve_cf_token(),
                                          "Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        print("script:", json.loads(r.read())["success"])
    zone = t._zone_for(c, HOST)
    c.call("PUT", f"/accounts/{acct}/workers/domains",
           body={"hostname": HOST, "service": SCRIPT, "zone_id": zone, "environment": "production"})
    print("domain:", HOST)


def link(email, days=14):
    c = _client()
    ns = t._find_namespace(c)
    if not t._kv_json(c, ns, f"tunnel:{email}"):
        raise SystemExit(f"{email} is not onboarded yet; run tenant onboard first")
    code = secrets.token_urlsafe(24)
    c.call("PUT", f"/accounts/{c.account_id}/storage/kv/namespaces/{ns}/values/enroll:{code}",
           body=email, query={"expiration_ttl": str(days * 86400)}, raw=True)
    print(f"https://{HOST}/j/{code}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["deploy"]:
        deploy()
    elif a[:1] == ["link"] and len(a) >= 2:
        link(a[1], int(a[a.index("--days") + 1]) if "--days" in a else 14)
    else:
        raise SystemExit(__doc__)
