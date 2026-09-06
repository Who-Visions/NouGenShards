"""Live reachability matrix for every NouGen surface (Elevation Matrix, Move 6).

A label is not a measurement. `shards_status` said green while blade was down
(the failover Worker's first hop answered); a shard stamped source_node "blade"
lived in the fleet store, not on blade's disk; blade.nougenai.com answered 000
from blade itself. Each of those cost a lane hours because the surface that
answered was not the surface the name promised. This tool prints, per surface:

    STATE  name  status  latency_ms  answering_node  vantage

and names WHICH node answered by reading the /health fields (storage,
persistent_storage, deploy_sha) against `node_signatures` in the manifest,
never by trusting the hostname. Four states, so nothing has to be inferred:

    GREEN     reachable, status in expect.status, answering node as expected
    AMBER     reachable but the answering node is not the expected one
              (the false-green signature), or status unexpected
    RED       no answer: DNS, TCP, TLS, timeout
    SKIPPED   this vantage cannot run the probe (no token, vantage_only)

The manifest (tools/reach_surfaces.json, override NOUGEN_SURFACES_FILE) must
carry at least one `control` row pointing at a dead host; the run refuses to
report GREEN for anything if the control row is not RED, per the
adversarial-control doctrine (six wrong fleet conclusions in one morning were
all empty-read-as-evidence).

Run from every node: the same manifest from three vantages is the matrix.
    python tools/reach_matrix.py            table to stdout, JSON to state dir
    python tools/reach_matrix.py --json     JSON only
    python tools/reach_matrix.py --capture  also capture the run as a shard
Exit 0 when the control row is RED and no surface is RED/AMBER, 1 otherwise,
2 when the control row itself failed to be RED (the probe cannot be trusted).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
UA = os.environ.get("NOUGEN_PROBE_UA", "nougen-reach-matrix/1.0")  # bare Python UA draws a Cloudflare 1010/403
TIMEOUT_S = float(os.environ.get("NOUGEN_REACH_TIMEOUT_S", "20"))
STATE_DIR = os.environ.get("NOUGEN_STATE_DIR", os.path.join(os.path.expanduser("~"), ".nougen", "state"))
MANIFEST = os.environ.get("NOUGEN_SURFACES_FILE", os.path.join(HERE, "reach_surfaces.json"))
GATEWAY = os.environ.get("NGS_GATEWAY_ORIGIN_FLEET", "https://shards.nougenai.com")
_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def vantage() -> str:
    host = platform.node().lower()
    if "proart" in host or "whoart" in host:
        return "whoart"
    if os.name != "nt":
        return "phoebus"
    return "blade"


def expand(target: str) -> str:
    """${VAR:-default} in manifest targets resolves from the environment (Rule 0.2)."""
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), target)


def load_manifest(path: str = MANIFEST) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ssl_context():
    try:
        import certifi  # type: ignore
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def node_token() -> str | None:
    """Rule 0.3: Keymaker first, env second. Never printed; fingerprint only."""
    tok = os.environ.get("NGS_NODE_TOKEN") or os.environ.get("SHARD_GATEWAY_TOKEN")
    if tok:
        return tok
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
        from nougen_shards import keymaker  # type: ignore
        return keymaker.get_secret("NGS_NODE_TOKEN")
    except Exception:
        return None


def fingerprint(tok: str | None) -> str | None:
    return hashlib.sha256(tok.encode()).hexdigest()[:12] if tok else None


def http(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None):
    """Return (status, text, error). status is None when nothing answered."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("user-agent", UA)
    if data is not None:
        req.add_header("content-type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    ctx = _ssl_context()
    handlers = [urllib.request.HTTPSHandler(context=ctx)] if ctx else []
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(req, timeout=TIMEOUT_S) as r:
            return r.status, r.read(4096).decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return e.code, e.read(4096).decode("utf-8", "replace"), None
    except Exception as e:  # URLError, socket.timeout, ssl errors: nothing answered
        return None, "", f"{type(e).__name__}: {str(e)[:120]}"


def answering_node(text: str, signatures: list[dict]) -> str:
    """Name the node from /health fields; 'unknown' when the fields are absent, never a guess."""
    try:
        h = json.loads(text)
    except Exception:
        return "unknown"
    if not isinstance(h, dict) or "storage" not in h:
        return "unknown"
    storage = str(h.get("storage") or "")
    persistent = h.get("persistent_storage")
    for sig in signatures:
        if "persistent_storage" in sig and sig["persistent_storage"] != persistent:
            continue
        if "storage" in sig and sig["storage"] != storage:
            continue
        if "storage_endswith" in sig and not storage.rstrip("\\/").endswith(sig["storage_endswith"]):
            continue
        return sig["node"]
    return f"unmatched({storage[:24]},persistent={persistent})"


def classify(surface: dict, status, text: str, err, signatures: list[dict]) -> tuple[str, str, str]:
    """Return (state, answering_node, note)."""
    expect = surface.get("expect", {})
    if status is None:
        return "RED", "-", err or "no answer"
    node = answering_node(text, signatures) if surface["kind"] in ("http", "control") else "-"
    if status not in expect.get("status", [200]):
        return "AMBER", node, f"status {status} not in {expect.get('status')}"
    want = expect.get("node")
    if want and node != want:
        return "AMBER", node, f"answering node {node} != expected {want} (false-green signature)"
    return "GREEN", node, ""


def probe(surface: dict, signatures: list[dict], token: str | None, here: str) -> dict:
    row = {"name": surface["name"], "kind": surface["kind"], "target": expand(surface["target"]), "vantage": here}
    only = surface.get("vantage_only")
    if only and here not in only:
        row.update(state="SKIPPED", status=None, ms=None, node="-", note=f"vantage_only {only}")
        return row
    t0 = time.perf_counter()
    if surface["kind"] == "tcp":
        host, port = row["target"].rsplit(":", 1)
        try:
            with socket.create_connection((host, int(port)), timeout=TIMEOUT_S):
                status, text, err = 0, "", None
        except Exception as e:
            status, text, err = None, "", f"{type(e).__name__}: {str(e)[:120]}"
        surface = dict(surface, expect={"status": [0]})
    elif surface["kind"] == "search":
        if not token:
            row.update(state="SKIPPED", status=None, ms=None, node="-", note="no NGS_NODE_TOKEN on this vantage")
            return row
        status, text, err = http(row["target"], "POST", {"query": "reach matrix control", "limit": 1},
                                 {"X-NGS-Token": token})
    else:
        status, text, err = http(row["target"])
    ms = round((time.perf_counter() - t0) * 1000)
    state, node, note = classify(surface, status, text, err, signatures)
    row.update(state=state, status=status, ms=ms, node=node, note=note)
    return row


def run(manifest: dict, token: str | None, here: str | None = None) -> dict:
    here = here or vantage()
    sigs = manifest.get("node_signatures", [])
    rows = [probe(s, sigs, token, here) for s in manifest["surfaces"]]
    controls = [r for r in rows if r["kind"] == "control"]
    control_ok = bool(controls) and all(r["state"] == "RED" for r in controls)
    if not control_ok:
        # A GREEN next to a control that is not RED is not evidence of anything.
        for r in rows:
            if r["kind"] != "control" and r["state"] == "GREEN":
                r["state"], r["note"] = "UNTRUSTED", "control row was not RED; probe cannot be trusted"
    bad = [r for r in rows if r["kind"] != "control" and r["state"] in ("RED", "AMBER", "UNTRUSTED")]
    return {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "vantage": here,
            "manifest": MANIFEST, "token_fp": fingerprint(token), "control_ok": control_ok,
            "summary": {"green": sum(r["state"] == "GREEN" for r in rows), "amber": sum(r["state"] == "AMBER" for r in rows),
                        "red": sum(r["state"] == "RED" for r in rows if r["kind"] != "control"),
                        "skipped": sum(r["state"] == "SKIPPED" for r in rows)},
            "rows": rows, "exit": 2 if not control_ok else (1 if bad else 0)}


def table(result: dict) -> str:
    w = max(len(r["name"]) for r in result["rows"]) + 2
    out = [f"reach matrix  vantage={result['vantage']}  {result['utc']}  control_ok={result['control_ok']}  token_fp={result['token_fp']}"]
    for r in result["rows"]:
        st = "-" if r["status"] is None else str(r["status"])
        ms = "-" if r["ms"] is None else f"{r['ms']}ms"
        out.append(f"{r['state']:<9} {r['name']:<{w}} {st:>4} {ms:>8}  {r['node']:<14} {r['note']}")
    s = result["summary"]
    out.append(f"green={s['green']} amber={s['amber']} red={s['red']} skipped={s['skipped']} exit={result['exit']}")
    return "\n".join(out)


def capture(result: dict, token: str | None) -> str:
    """One shard per run so the matrix history lives in the vault, not in a terminal."""
    if not token:
        return "capture skipped: no token"
    s = result["summary"]
    title = (f"REACH MATRIX {result['utc']} from {result['vantage']}: green={s['green']} amber={s['amber']} "
             f"red={s['red']} skipped={s['skipped']} control_ok={result['control_ok']}")
    body = table(result) + "\n\nAMBER = reachable but answered by a node other than the expected one (false-green signature). " \
           "RED = nothing answered. Names are hostnames; nodes are read from /health fields."
    status, text, err = http(GATEWAY + "/capture", "POST",
                             {"title": title, "content": body, "event_type": "OBSERVATION",
                              "tags": ["reach-matrix", "move-6", "fleet", "reachability", result["vantage"]]},
                             {"X-NGS-Token": token})
    return f"capture -> {status} {text[:80]}" if status else f"capture failed: {err}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print JSON instead of the table")
    ap.add_argument("--capture", action="store_true", help="capture the run as a shard via the fleet gateway")
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--vantage", default=None, help="override the detected vantage label")
    a = ap.parse_args(argv)
    manifest = load_manifest(a.manifest)
    token = node_token()
    result = run(manifest, token, a.vantage)
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "reach_matrix.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
    except OSError as e:
        print(f"[reach] state not written: {e}", file=sys.stderr)
    print(json.dumps(result, indent=1) if a.json else table(result))
    if a.capture:
        print(capture(result, token))
    return result["exit"]


if __name__ == "__main__":
    sys.exit(main())
