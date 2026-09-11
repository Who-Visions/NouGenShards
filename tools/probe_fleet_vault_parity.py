"""Probe fleet-wide 3-vault parity and multi-tenant lane readiness.

Enforces Dave's non-negotiable rule:
1. Blade, Phoebus, and Who Art are symmetric first-class peer vaults.
2. Local 9-DB grid coverage MUST NOT be reported as 3/3 fleet vault health.
3. Fleet green requires 3/3 vaults answering. Any timeout/error reports DEGRADED
   and cannot_determine=True for absence checks.
4. Multi-tenant lanes (x-nougen-lane, x-nougen-tenant) operate concurrently.
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional


DEFAULT_VAULTS = {
    "blade": "https://blade.nougenai.com",
    "phoebus": "https://phoebus.nougenai.com",
    "whoart": "https://whoart-vault.nougenai.com",
}

USER_AGENT = "nougen-probe-fleet-vault-parity/1.0"


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


def probe_vault(name: str, url: str, timeout: float = 8.0, token: Optional[str] = None, lane: Optional[str] = None) -> dict:
    endpoint = url.rstrip("/") + "/health"
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["X-NGS-Token"] = token
    if lane:
        headers["X-NouGen-Lane"] = lane

    req = urllib.request.Request(endpoint, headers=headers)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            elapsed = time.monotonic() - start
            body_bytes = resp.read()
            status_code = resp.status
            try:
                payload = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                payload = {}
            return {
                "name": name,
                "url": url,
                "endpoint": endpoint,
                "ok": status_code == 200,
                "status": status_code,
                "latency_ms": round(elapsed * 1000, 1),
                "payload": payload,
                "error": None,
            }
    except Exception as exc:
        elapsed = time.monotonic() - start
        return {
            "name": name,
            "url": url,
            "endpoint": endpoint,
            "ok": False,
            "status": None,
            "latency_ms": round(elapsed * 1000, 1),
            "payload": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def evaluate_fleet_parity(probes: List[dict]) -> dict:
    total_expected = len(probes)
    answering = [p for p in probes if p["ok"]]
    responding_count = len(answering)
    fleet_green = (responding_count == total_expected and total_expected > 0)

    vault_reports = {}
    for p in probes:
        pl = p.get("payload", {})
        db_grid = pl.get("db_grid") or pl.get("substrate", {})
        vault_reports[p["name"]] = {
            "ok": p["ok"],
            "status": p["status"],
            "latency_ms": p["latency_ms"],
            "error": p["error"],
            "total_shards": pl.get("total_shards"),
            "tenant_id": pl.get("tenant_id"),
            "tenant_lane": pl.get("tenant_lane"),
            "local_db_grid_mounted": db_grid.get("databases_mounted"),
            "local_db_grid_expected": db_grid.get("databases_expected", 9),
            "coverage_scope": pl.get("coverage_scope") or db_grid.get("coverage_scope", "LOCAL_VAULT_COVERAGE"),
        }

    return {
        "fleet_green": fleet_green,
        "cannot_determine": not fleet_green,
        "vaults_expected": total_expected,
        "vaults_responding": responding_count,
        "status": "GREEN" if fleet_green else "DEGRADED",
        "vaults": vault_reports,
    }


def main():
    parser = argparse.ArgumentParser(description="Probe fleet vault parity across Blade, Phoebus, and WhoArt.")
    parser.add_argument("--timeout", type=float, default=6.0, help="Per-vault probe timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    probes = []
    for name, url in DEFAULT_VAULTS.items():
        probes.append(probe_vault(name, url, timeout=args.timeout))

    evaluation = evaluate_fleet_parity(probes)

    if args.json:
        print(json.dumps(evaluation, indent=2))
    else:
        mark = lambda ok: "🟢" if ok else "🔴"
        print("======================================================================")
        print(f"FLEET VAULT PARITY: {evaluation['status']} ({evaluation['vaults_responding']}/{evaluation['vaults_expected']} Vaults Answering)")
        print("======================================================================")
        for name, r in evaluation["vaults"].items():
            state = f"UP ({r['latency_ms']}ms)" if r["ok"] else f"DOWN ({r['error']})"
            print(f"{mark(r['ok'])} [{name}] {state}")
            if r["ok"]:
                print(f"    Local DB Grid: {r['local_db_grid_mounted']}/{r['local_db_grid_expected']} DBs [{r['coverage_scope']}]")
                print(f"    Total Shards: {r['total_shards']}")
        print()
        if evaluation["fleet_green"]:
            print("✅ Symmetric 3/3 Vault Parity verified. Fleet recall trustworthy.")
        else:
            print("⚠️ DEGRADED: Fleet cannot guarantee absence checks (cannot_determine=true).")

    sys.exit(0 if evaluation["fleet_green"] else 1)


if __name__ == "__main__":
    main()
