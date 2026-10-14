"""Operator: issue a one-time invite for a tenant's node.

  python tools/tenant_invite.py fabian.v@gmail.com
Prints the invite code to hand to the tenant. Code is single-use and expires.
Writes KV "invite:<code>" in the TENANTS namespace (needs wrangler auth loaded).
"""
import json, secrets, subprocess, sys, time, tempfile, os
from pathlib import Path

email = sys.argv[1].strip().lower()
code = secrets.token_urlsafe(24)
record = {"eml": email, "exp": int(time.time()) + 72 * 3600}
fd, tmp = tempfile.mkstemp(suffix=".json")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump([{"key": "invite:" + code, "value": json.dumps(record)}], fh)
try:
    subprocess.run(["npx", "--no-install", "wrangler", "kv", "bulk", "put", tmp,
                    "--binding", "TENANTS", "--remote"], cwd=Path(os.environ.get("TENANT_WORKER_DIR", Path(__file__).resolve().parent.parent.parent / "nougen-fleet-mcp")),
                   check=True, shell=os.name == "nt", encoding="utf-8", errors="replace")
finally:
    Path(tmp).unlink(missing_ok=True)
print("invite code:", code)
print("expires in 72h, single use")
