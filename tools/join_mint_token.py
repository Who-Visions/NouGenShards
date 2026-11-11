"""Mint the join service's own narrowly scoped Cloudflare token and store it in the keymaker.

Scope: Cloudflare Tunnel Write, Workers KV Storage Write, Email Sending Write (this
account only) + DNS Write on the one zone. It cannot touch Workers scripts, routes,
other zones, billing or tokens. Stored under a NEW dated keymaker name (never
overwrites). Prints only the name and a fingerprint.

    python tools/join_mint_token.py [--zone nougenai.com]
"""
import datetime as dt
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nougen_shards import keymaker  # noqa: E402
from nougen_shards import tenant_onboard as t  # noqa: E402

PERMS_ACCOUNT = {"Cloudflare Tunnel Write", "Workers KV Storage Write", "Email Sending Write"}
PERMS_ZONE = {"DNS Write"}


def main():
    zone_name = sys.argv[sys.argv.index("--zone") + 1] if "--zone" in sys.argv else "nougenai.com"
    c = t.CloudflareClient(t._resolve_cf_token()) if hasattr(t, "CloudflareClient") else _client()
    acct = c.account_id
    groups = {g["name"]: g["id"] for g in c.call("GET", f"/accounts/{acct}/tokens/permission_groups")}
    zone = t._zone_for(c, "x." + zone_name)
    body = {
        "name": f"nougen-join-provisioner-{dt.date.today():%Y%m%d}",
        "policies": [
            {"effect": "allow", "resources": {f"com.cloudflare.api.account.{acct}": "*"},
             "permission_groups": [{"id": groups[n]} for n in sorted(PERMS_ACCOUNT)]},
            {"effect": "allow", "resources": {f"com.cloudflare.api.account.zone.{zone}": "*"},
             "permission_groups": [{"id": groups[n]} for n in sorted(PERMS_ZONE)]},
        ],
    }
    res = c.call("POST", f"/accounts/{acct}/tokens", body=body)
    value = res["value"]
    name = f"CLOUDFLARE_JOIN_TOKEN_{dt.datetime.now():%Y%m%d_%H%M}"
    keymaker.ingest_secret(name, value)
    assert keymaker.get_secret(name) == value, "keymaker write did not read back"
    print(name, "fp", hashlib.sha256(value.encode()).hexdigest()[:12])


def _client():
    import inspect
    cls = [k for _, k in inspect.getmembers(t, inspect.isclass)
           if "__init__" in k.__dict__ and "account_id" in inspect.signature(k.__init__).parameters][0]
    return cls(token=t._resolve_cf_token())


if __name__ == "__main__":
    main()
