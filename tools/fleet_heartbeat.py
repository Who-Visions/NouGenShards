"""Fleet heartbeat: the always-on local model watching the always-on infrastructure.

Runs on whoart beside the resident Ollama (gemma4:e2b-qat) and answers one
question on a schedule: is every lane the fleet depends on actually carrying
traffic, and if not, which one broke and how.

Why this exists, concretely. On 2026-08-29 `ask_rhea` returned
"530: error code: 1033" and several sessions read it as an inference outage. It
was a Cloudflare tunnel with no connector attached, in front of a node that was
perfectly healthy. Every check below is shaped by a way the fleet actually
misled someone that day:

  * /health returning 200 proves an origin is REACHABLE, not that a given
    caller's path works. /agent and /health resolved to DIFFERENT origins for
    the same hostname, so this probes paths, not just hosts, and records the
    x-nougen-origin header that names who answered.
  * 1033 means a named tunnel has zero connectors. The machine can be powered
    on, the node can be serving locally, and the hostname still fails. So the
    tunnel is checked at the Cloudflare control plane, not by curling a URL.
  * A corrupt node answers 200 with an empty result, which is indistinguishable
    from "no matches" to anything that only checks status codes. So recall is
    checked for CONTENT, and shard counts are compared ACROSS nodes rather than
    trusted individually.
  * Rhea answering is not Rhea working. The reply names the brain; a wrong-lane
    answer looks identical to a right one unless you read that field.

Usage:
    python tools/fleet_heartbeat.py                 # human summary
    python tools/fleet_heartbeat.py --json          # machine-readable
    python tools/fleet_heartbeat.py --triage        # + local-model triage
    python tools/fleet_heartbeat.py --ask-nodes     # + node-only questions via ssh

Exit code is 0 only when every REQUIRED check passes, so a scheduler can gate
on it. Reads only; it never mutates a lane it is watching.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

OLLAMA = os.environ.get("NOUGEN_OLLAMA_URL", "http://localhost:11434")
LOCAL_MODEL = os.environ.get("NOUGEN_HEARTBEAT_MODEL", "gemma4:e2b-qat")
UA = {"User-Agent": "nougen-fleet-heartbeat/1.0"}

# Lanes the fleet actually depends on. `required` marks the ones whose failure
# means the fleet is degraded rather than merely diminished.
HTTP_LANES = [
    {"name": "blade-node", "url": "https://blade.nougenai.com/health", "required": True,
     "why": "the live shard vault behind the named tunnel"},
    {"name": "front-door", "url": "https://shards.nougenai.com/health", "required": True,
     "why": "canonical ingress; everything else happens after this door"},
    {"name": "space-node", "url": "https://nougenai-nougenshards.hf.space/health", "required": False,
     "why": "always-up AI host; its DB has been malformed, so not required for memory"},
    {"name": "phoebus-mesh", "url": "http://10.0.0.88:8765/memory/stats", "required": False,
     "why": "always-on node; read path that needs no ssh"},
]

SSH_LANES = [
    {"name": "whoart->blade", "host": "blade", "required": False},
]

# Node-only questions: things no other machine can answer about itself.
NODE_QUESTIONS = {
    "blade": (
        "powershell -NoProfile -Command \""
        "'cloudflared_service=' + (Get-Service cloudflared -ErrorAction SilentlyContinue).Status; "
        "'node_listening=' + ((Get-NetTCPConnection -LocalPort 4444 -State Listen "
        "-ErrorAction SilentlyContinue | Measure-Object).Count)\""
    ),
}


def _get(url: str, timeout: float = 15.0) -> dict:
    t0 = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        body = r.read(4000).decode("utf8", "replace")
        return {"ok": True, "status": r.status, "ms": int((time.time() - t0) * 1000),
                "origin": r.headers.get("x-nougen-origin"), "body": body}
    except urllib.error.HTTPError as e:
        body = e.read(400).decode("utf8", "replace")
        # 1033 is the signature of a named tunnel with no connector attached.
        tunnel_down = "1033" in body
        return {"ok": False, "status": e.code, "ms": int((time.time() - t0) * 1000),
                "error": f"HTTP {e.code}" + (" (tunnel has no connector)" if tunnel_down else ""),
                "tunnel_down": tunnel_down, "body": body[:200]}
    except Exception as e:  # noqa: BLE001 - a heartbeat never raises
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": type(e).__name__}


def check_http(lane: dict) -> dict:
    # Retry once before condemning a lane. A SATURATED origin is not a down
    # one: blade's node was measured at 24,523s CPU with a 2.3GB working set,
    # timing out on the first request and answering 200 on the second. A
    # single-shot probe reports that as an outage and sends whoever reads it
    # hunting a tunnel fault that does not exist.
    r = _get(lane["url"])
    if not r.get("ok") and not r.get("tunnel_down"):
        retry = _get(lane["url"], timeout=30.0)
        if retry.get("ok"):
            retry["degraded"] = "first attempt failed, retry succeeded — origin is slow, not down"
            r = retry
    out = {"check": lane["name"], "kind": "http", "required": lane["required"],
           "why": lane["why"], "ok": r.get("ok", False), "ms": r.get("ms"),
           "status": r.get("status"), "origin": r.get("origin"), "error": r.get("error")}
    if r.get("degraded"):
        out["degraded"] = r["degraded"]
    m = re.search(r'"total_shards"\s*:\s*(\d+)', r.get("body") or "")
    if m:
        out["shards"] = int(m.group(1))
    if r.get("tunnel_down"):
        out["hint"] = ("named tunnel has zero connectors — the node may be fine. "
                       "Check `cloudflared` service on the origin host, not the node.")
    return out


def check_ollama() -> dict:
    """The local model is the thing running these checks; confirm it can answer."""
    r = _get(f"{OLLAMA}/api/tags", timeout=8)
    if not r.get("ok"):
        return {"check": "local-ollama", "kind": "local", "required": True, "ok": False,
                "error": r.get("error"), "why": "the resident model that runs this heartbeat"}
    try:
        names = [m["name"] for m in json.loads(r["body"]).get("models", []) if m.get("name")]
    except Exception:  # noqa: BLE001
        names = []
    ps = _get(f"{OLLAMA}/api/ps", timeout=8)
    resident = []
    if ps.get("ok"):
        try:
            resident = [m.get("name") for m in json.loads(ps["body"]).get("models", [])]
        except Exception:  # noqa: BLE001
            pass
    return {"check": "local-ollama", "kind": "local", "required": True, "ok": True,
            "ms": r.get("ms"), "installed": len(names),
            "has_resident_model": LOCAL_MODEL in names, "loaded_now": resident,
            "why": "the resident model that runs this heartbeat",
            # Nothing loaded is NORMAL: models unload after keep-alive and
            # reload on demand. Absence here is not an outage.
            "note": "empty loaded_now is idle, not down"}


def check_ssh(lane: dict) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
             "-o", "StrictHostKeyChecking=accept-new", lane["host"], "echo HEARTBEAT_OK"],
            capture_output=True, text=True, timeout=45)
        ok = "HEARTBEAT_OK" in (p.stdout or "")
        return {"check": lane["name"], "kind": "ssh", "required": lane["required"], "ok": ok,
                "ms": int((time.time() - t0) * 1000),
                "error": None if ok else (p.stderr or "").strip().splitlines()[-1:] or "no output"}
    except Exception as e:  # noqa: BLE001
        return {"check": lane["name"], "kind": "ssh", "required": lane["required"], "ok": False,
                "ms": int((time.time() - t0) * 1000), "error": type(e).__name__}


def ask_node(host: str, command: str) -> dict:
    """Ask a node something only it can answer about itself."""
    try:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, command],
                           capture_output=True, text=True, timeout=90)
        lines = [l.strip() for l in (p.stdout or "").splitlines() if l.strip()]
        return {"check": f"ask:{host}", "kind": "node-question", "required": False,
                "ok": bool(lines), "answers": lines[:8]}
    except Exception as e:  # noqa: BLE001
        return {"check": f"ask:{host}", "kind": "node-question", "required": False,
                "ok": False, "error": type(e).__name__}


def divergence(results: list) -> dict | None:
    """Shard counts across nodes. A single node's count proves nothing.

    The Space reported 199,877 from metadata while its database was malformed
    and recall returned nothing, so counts are only meaningful compared.
    """
    counts = {r["check"]: r["shards"] for r in results if r.get("shards") is not None}
    if len(counts) < 2:
        return None
    lo, hi = min(counts.values()), max(counts.values())
    return {"counts": counts, "spread": hi - lo,
            "note": "a node's own count cannot prove its health; compare, never trust one"}


def triage(results: list) -> str:
    """Route the summary to the resident local model. Player drafts; coach reviews."""
    failing = [r for r in results if not r["ok"]]
    if not failing:
        return "(all lanes up — no triage needed)"
    prompt = (
        "You are triaging a fleet heartbeat. These lanes failed. For each, give ONE "
        "line: the single most likely cause and the first thing to check. Be terse and "
        "technical. Do not invent causes beyond the data.\n\n"
        + json.dumps(failing, indent=2)[:3000]
    )
    body = json.dumps({"model": LOCAL_MODEL, "messages": [{"role": "user", "content": prompt}],
                       # >=1400: the E-series reasoning channel consumes the budget
                       # first, so a smaller cap returns empty with no error.
                       "max_tokens": 1400}).encode()
    try:
        req = urllib.request.Request(f"{OLLAMA}/v1/chat/completions", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer ollama", **UA})
        d = json.loads(urllib.request.urlopen(req, timeout=180).read())
        return (d["choices"][0]["message"].get("content") or "").strip() or "(model returned empty)"
    except Exception as e:  # noqa: BLE001
        return f"(triage unavailable: {type(e).__name__})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--triage", action="store_true", help="have the local model triage failures")
    ap.add_argument("--ask-nodes", action="store_true", help="ask nodes what only they know")
    ap.add_argument("--ssh", action="store_true", help="include ssh lane checks (slower)")
    args = ap.parse_args()

    jobs = [lambda l=l: check_http(l) for l in HTTP_LANES] + [check_ollama]
    if args.ssh:
        jobs += [lambda l=l: check_ssh(l) for l in SSH_LANES]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda f: f(), jobs))

    if args.ask_nodes:
        with ThreadPoolExecutor(max_workers=4) as ex:
            results += list(ex.map(lambda kv: ask_node(*kv), NODE_QUESTIONS.items()))

    div = divergence(results)
    required_ok = all(r["ok"] for r in results if r.get("required"))
    report = {"ok": required_ok, "checks": results, "divergence": div}
    if args.triage:
        report["triage"] = triage(results)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0 if required_ok else 1

    for r in results:
        mark = "ok  " if r["ok"] else ("FAIL" if r.get("required") else "--  ")
        extra = []
        if r.get("ms") is not None:
            extra.append(f"{r['ms']}ms")
        if r.get("origin"):
            extra.append(f"origin={r['origin']}")
        if r.get("shards") is not None:
            extra.append(f"shards={r['shards']:,}")
        if r.get("error"):
            extra.append(str(r["error"]))
        print(f"[{mark}] {r['check']:<16} {' '.join(extra)}")
        if r.get("hint"):
            print(f"        ^ {r['hint']}")
        if r.get("degraded"):
            print(f"        ~ {r['degraded']}")
        for a in r.get("answers", []):
            print(f"        {a}")
    if div:
        print(f"\nshard counts: {div['counts']}  spread={div['spread']:,}")
        print(f"  {div['note']}")
    if args.triage:
        print(f"\n--- local triage ({LOCAL_MODEL}) ---\n{report['triage']}")
    print("\nHEARTBEAT OK" if required_ok else "\nHEARTBEAT DEGRADED — see FAIL rows")
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
