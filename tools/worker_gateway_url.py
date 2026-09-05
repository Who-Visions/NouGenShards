"""Read or set the live SHARD_GATEWAY_URL var on the nougen-fleet-mcp Worker.

gateway_supervisor.ps1's Sync-Worker used to "re-point the worker" by regex
rewriting "SHARD_GATEWAY_URL" inside wrangler.jsonc and running `wrangler
deploy`. That file deliberately carries NO vars block (keep_vars: true; the 23
plain vars and 7 secrets live in the dashboard, and three of them render
truncated so they cannot be copied safely), so the regex matched nothing and
the rewrite was a no-op. The supervisor then logged "updating worker" and
changed nothing -- the same shape of dead self-heal as the three defects fixed
on 2026-08-29, just one layer further out.

This talks to the API instead, which is where the var actually lives.

--set is deliberately conservative. Cloudflare's settings PATCH replaces the
whole bindings array, and secret_text bindings come back from the API with no
value, so echoing them verbatim would blank all seven secrets. Every binding
this script does not own is therefore re-sent as {"type": "inherit"}, which is
the documented way to say "keep what is deployed". Anything unexpected aborts
before the write rather than guessing.

Credentials resolve from the keymaker vault; nothing is echoed. Names are
env-overridable so a host that labels them differently needs no code change.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

API = os.environ.get("CLOUDFLARE_API_BASE", "https://api.cloudflare.com/client/v4")
SCRIPT = os.environ.get("NGS_WORKER_NAME", "nougen-fleet-mcp")
VAR = os.environ.get("NGS_WORKER_URL_VAR", "SHARD_GATEWAY_URL")
ACCT_KEY = os.environ.get("NGS_CF_ACCOUNT_KEY", "CLOUDFLARE_ACCOUNT_ID")
TOKEN_KEY = os.environ.get("NGS_CF_TOKEN_KEY", "CLOUDFLARE_API_TOKEN")
# What shape the target var holds. "url" keeps the https-only guard that made
# sense when this script only ever wrote SHARD_GATEWAY_URL; "int" and "text"
# exist because the same settings PATCH (and the same inherit-everything-else
# safety) is what any other plain var on any other worker needs. Default is
# unchanged, so existing callers keep the strict guard.
KIND = os.environ.get("NGS_WORKER_VAR_KIND", "url").strip().lower()


def creds():
    from nougen_shards import keymaker
    acct = keymaker.get_secret(ACCT_KEY)
    token = keymaker.get_secret(TOKEN_KEY)
    missing = [k for k, v in ((ACCT_KEY, acct), (TOKEN_KEY, token)) if not v]
    if missing:
        sys.exit(f"FATAL: {', '.join(missing)} absent from the keymaker vault on this host")
    return acct, token


CRLF = chr(13) + chr(10)


def call(method, url, token, payload=None):
    # The script-settings PATCH is multipart/form-data with a JSON "settings"
    # part. Sending application/json returns a bare 415 with no body, which is
    # why the --set path had never actually written anything.
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if payload is not None:
        boundary = "----nougen" + os.urandom(8).hex()
        data = CRLF.join([
            "--" + boundary,
            'Content-Disposition: form-data; name="settings"',
            "Content-Type: application/json",
            "",
            json.dumps(payload["settings"]),
            "--" + boundary + "--",
            "",
        ]).encode()
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=int(os.environ.get("NGS_CF_TIMEOUT_S", "45"))) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"FATAL: {method} {url.split('/accounts/')[-1]} -> HTTP {e.code} {e.read(400).decode('utf8', 'replace')}")


def settings_url(acct):
    return f"{API}/accounts/{acct}/workers/scripts/{SCRIPT}/settings"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--get", action="store_true", help=f"print the live {VAR}")
    g.add_argument("--set", metavar="VALUE",
                   help=f"set {VAR} (kind={KIND}; url = https origin only, no path)")
    a = ap.parse_args()

    acct, token = creds()
    cur = call("GET", settings_url(acct), token)
    bindings = cur["result"]["bindings"]
    entry = next((b for b in bindings if b.get("name") == VAR), None)
    live = entry.get("text") if entry else None

    if a.get:
        if entry is not None and live is None:
            # A plain config value filed as secret_text reads back with no text.
            # Printing "" here is what made an already-set var look unset.
            print(f"<{entry.get('type')}: value not readable via API>")
        else:
            print(live if live else "")
        return 0

    target = a.set.strip()
    if KIND == "url":
        target = target.rstrip("/")
        if not target.startswith("https://"):
            sys.exit(f"FATAL: refusing to set {VAR} to a non-https origin: {target}")
    elif KIND == "int":
        if not re.fullmatch(r"-?\d+", target):
            sys.exit(f"FATAL: refusing to set {VAR} to a non-integer value: {target!r}")
    elif KIND != "text":
        sys.exit(f"FATAL: unknown NGS_WORKER_VAR_KIND {KIND!r} (expected url, int or text)")
    if live == target and entry and entry.get("type") == "plain_text":
        print(f"{VAR} already {target} - no write")
        return 0

    # Re-send every binding we do not own as inherit; abort on any type we have
    # not reasoned about rather than risk blanking it.
    known = {"plain_text", "secret_text"}
    unknown = sorted({b["type"] for b in bindings} - known)
    if unknown:
        sys.exit(f"FATAL: unhandled binding type(s) {unknown} - not writing, "
                 "extend this script before touching the worker")
    out = []
    for b in bindings:
        if b["name"] == VAR:
            out.append({"type": "plain_text", "name": VAR, "text": target})
        else:
            out.append({"type": "inherit", "name": b["name"]})
    if entry is None:
        # The var has never been set on this worker, so the code default is what
        # is live. Append it rather than silently PATCHing a no-op set.
        out.append({"type": "plain_text", "name": VAR, "text": target})
    call("PATCH", settings_url(acct), token, {"settings": {"bindings": out}})
    after = call("GET", settings_url(acct), token)["result"]["bindings"]
    now = next((b.get("text") for b in after if b.get("name") == VAR), None)
    if now != target:
        sys.exit(f"FATAL: write did not stick - {VAR} is {now!r}")
    print(f"{VAR}: {live} -> {now}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
