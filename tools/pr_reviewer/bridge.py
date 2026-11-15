"""Python side of the aiwithdav3 PR reviewer (called by review.ts over stdin/stdout JSON).

    {"op": "secret", "name": "..."}                        -> {"ok": true, "value": "..."}   (pipe only, never logged)
    {"op": "ask", "lane": "huggingface|openrouter|ollama-cloud", "system": "...", "prompt": "...", "max_tokens": 4096}
                                                            -> {"ok": true, "provider", "model", "content"} | {"ok": false, "error"}

Model calls go through the NouGenOpen FleetWorker restricted to one lane, so review.ts owns the
fallback order and can force a lane to fail. Keys come from the keymaker; nothing is printed.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

HOME = pathlib.Path.home()
os.environ.setdefault("NOUGEN_VAULT_DIR", str(HOME / ".nougen" / "shards"))
os.environ.setdefault("NOUGEN_SECRETS_VAULT_DIR", str(HOME / ".nougen" / "secrets"))
for p in (HOME / "Outpost" / "NouGen" / "src", HOME / "Outpost" / "NouGenOpen" / "src"):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


def op_secret(req):
    from nougen_shards.keymaker import get_secret
    v = get_secret(req["name"])
    return {"ok": bool(v), "value": v or ""}


def op_ask(req):
    from nougen_open.providers import BY_NAME
    from nougen_open.worker import FleetWorker, Lane
    prov = BY_NAME[req["lane"]]
    w = FleetWorker(lanes=[Lane(prov)])
    if not w.lanes:
        return {"ok": False, "error": f"no keys for {req['lane']}"}
    r = w.generate(req["prompt"], system_prompt=req.get("system"), max_tokens=int(req.get("max_tokens", 4096)),
                   timeout=float(req.get("timeout", 120)), attempts_per_lane=int(req.get("attempts", 4)))
    if not r.get("success", True) or not (r.get("content") or "").strip():
        return {"ok": False, "error": (str(r.get("error") or "empty content") + " :: " + " | ".join(map(str, (r.get("details") or [])[:4])))[:700]}
    return {"ok": True, "provider": r.get("provider"), "model": r.get("model"), "content": r["content"]}


def main():
    req = json.loads(sys.stdin.read() or "{}")
    try:
        out = {"secret": op_secret, "ask": op_ask}[req.get("op")](req)
    except Exception as e:  # report, never raise: the caller treats ok=false as a lane failure
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"[:500]}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
