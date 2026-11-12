"""Deploy the universal nougen-join worker to join.<zone>.

    python workers/join/deploy.py

Reads from the keymaker (never printed): the join service's scoped Cloudflare token
(newest CLOUDFLARE_JOIN_TOKEN_*), NOUGEN_JOIN_GOOGLE_CLIENT_ID/_SECRET, and the
operator's full token only to upload the script and bind the custom domain.
"""
import json
import os
import pathlib
import sqlite3
import sys
import urllib.request
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from nougen_shards import keymaker  # noqa: E402
from nougen_shards import tenant_onboard as t  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = "nougen-join"
ZONE = os.environ.get("NOUGEN_JOIN_ZONE", "nougenai.com")


DEFAULT_JOIN_TOKEN_NAME = "CLOUDFLARE_JOIN_TOKEN_20261111_1657"


def newest(prefix, fallback=DEFAULT_JOIN_TOKEN_NAME):
    names = {k for k in os.environ if k.startswith(prefix) and os.environ.get(k)}
    try:
        names |= {str(k) for k in keymaker.list_providers() if str(k).startswith(prefix)}
    except Exception:
        pass
    store_paths = [keymaker.db_path()]
    try:
        res = keymaker.resolve_secrets_store()
        store_paths.append(res.get("active"))
        store_paths.extend(item["path"] for item in res.get("live", ()))
    except Exception:
        pass
    seen = set()
    for p in store_paths:
        if not p or str(p) in seen:
            continue
        seen.add(str(p))
        con = None
        try:
            con = sqlite3.connect(str(p))
            for (tbl,) in con.execute("select name from sqlite_master where type='table'"):
                cols = [c[1] for c in con.execute(f"pragma table_info({tbl})")]
                col = next((c for c in cols if c in ("secret_key", "key", "name", "title")), None)
                if col:
                    names |= {n for (n,) in con.execute(f"select {col} from {tbl}") if str(n).startswith(prefix)}
        except sqlite3.Error:
            pass
        finally:
            if con is not None:
                con.close()
    for candidate in sorted(names, reverse=True):
        val = keymaker.get_secret(candidate)
        if val:
            return val
    if fallback:
        val = keymaker.get_secret(fallback)
        if val:
            return val
    raise SystemExit(f"no keymaker secret starting {prefix}; run tools/join_mint_token.py")


def client():
    import inspect
    cls = [k for _, k in inspect.getmembers(t, inspect.isclass)
           if "__init__" in k.__dict__ and "account_id" in inspect.signature(k.__init__).parameters][0]
    return cls(token=t._resolve_cf_token())


def main():
    c = client()
    acct = c.account_id
    zone = t._zone_for(c, "join." + ZONE)
    join_token_name = os.environ.get("NOUGEN_JOIN_CF_TOKEN_NAME", "").strip()
    join_cf_token = keymaker.get_secret(join_token_name) if join_token_name else newest("CLOUDFLARE_JOIN_TOKEN_")
    bindings = [
        {"type": "ratelimit", "name": "JOIN_RL", "namespace_id": "1001", "simple": {"limit": 3, "period": 60}},
        {"type": "durable_object_namespace", "name": "COORD", "class_name": "JoinCoordinator"},
        {"type": "kv_namespace", "name": "TENANTS", "namespace_id": t._find_namespace(c)},
        {"type": "secret_text", "name": "CF_API_TOKEN", "text": join_cf_token},
        {"type": "secret_text", "name": "GOOGLE_CLIENT_SECRET", "text": keymaker.get_secret("NOUGEN_JOIN_GOOGLE_CLIENT_SECRET")},
        {"type": "plain_text", "name": "GOOGLE_CLIENT_ID", "text": keymaker.get_secret("NOUGEN_JOIN_GOOGLE_CLIENT_ID")},
        {"type": "plain_text", "name": "CF_ACCOUNT_ID", "text": acct},
        {"type": "plain_text", "name": "CF_ZONE_ID", "text": zone},
        {"type": "plain_text", "name": "ZONE_NAME", "text": ZONE},
        {"type": "plain_text", "name": "NODE_PORT", "text": "4444"},
        {"type": "plain_text", "name": "JOIN_MAX_PER_IP_DAY", "text": "5"},
        {"type": "plain_text", "name": "LINK_TTL_DAYS", "text": "14"},
    ]
    if any(b.get("text") in (None, "") for b in bindings if b["type"] in ("secret_text", "plain_text")):
        raise SystemExit("a keymaker value is missing; nothing deployed")
    meta = {"main_module": "worker.js", "compatibility_date": "2026-11-11", "bindings": bindings,
            "observability": {"enabled": True}}
    # First deploy with the coordinator creates its SQLite-backed class (migration v1);
    # later deploys must not repeat the migration.
    try:
        tag = (c.call("GET", f"/accounts/{acct}/workers/scripts/{SCRIPT}/settings") or {}).get("migration_tag")
    except Exception:  # noqa: BLE001 - first deploy of the script
        tag = None
    if tag != "v1":
        meta["migrations"] = {"new_tag": "v1", "new_sqlite_classes": ["JoinCoordinator"]}
    b = uuid.uuid4().hex
    body = b""
    for name, ctype, data in (("metadata", "application/json", json.dumps(meta).encode()),
                              ("worker.js", "application/javascript+module", (HERE / "worker.js").read_bytes())):
        fn = f'; filename="{name}"' if name != "metadata" else ""
        body += f'--{b}\r\nContent-Disposition: form-data; name="{name}"{fn}\r\nContent-Type: {ctype}\r\n\r\n'.encode() + data + b"\r\n"
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(f"{t.CF_API}/accounts/{acct}/workers/scripts/{SCRIPT}", data=body, method="PUT",
                                 headers={"Authorization": "Bearer " + t._resolve_cf_token(),
                                          "Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        print("script uploaded:", json.loads(r.read())["success"])
    c.call("PUT", f"/accounts/{acct}/workers/domains",
           body={"hostname": "join." + ZONE, "service": SCRIPT, "zone_id": zone, "environment": "production"})
    print("live at https://join." + ZONE)


if __name__ == "__main__":
    main()
