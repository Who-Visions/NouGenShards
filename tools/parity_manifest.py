#!/usr/bin/env python3
"""Deterministic NouGen core manifest for sibling-node parity reconciliation.

Every node runs this same script and gets the same component keys, so two
manifests diff mechanically instead of by "the prose sounds similar". Emits
sha256[:16] of artifact bytes and git SHAs; secrets appear ONLY as
sha256[:12] fingerprints of their value (never the value), so two vaults can
be compared for "same secret or not" without either side emitting it.

Parity rule (agreed 2026-09-03): match CONTRACTS byte-for-byte, never
internals. The `contract:*` rows below are the ones that must be identical
on every node; everything else is classified per node as EXACT MATCH /
INTENTIONAL MACHINE DIFFERENCE / STALE / MISSING / CONFLICTING / UNKNOWN.

Configuration, env first, documented fallback:
  NOUGEN_SHARDS_REPO      nougenshards checkout (default: this file's repo root)
  NOUGEN_RELAY_DIR        NouGenRelay clone (default ~/NouGenRelay, else skipped)
  NOUGEN_BUS_DIR          where the fleet-bus daemons run from
                          (default ~/.nougen/bin, then <repo>/tools)
  NOUGEN_HOOKS_DIR        agent hooks dir (default ~/.claude/hooks)
  NOUGEN_CC_SESSIONS      live-session registry (default ~/.nougen/cc_sessions.json)
  NOUGEN_MANIFEST_SECRETS comma list of vault key names to fingerprint
                          (default: the fleet-bus set)

Usage: python3 tools/parity_manifest.py [--json]
Stdlib only. Never writes anything. Safe to run on any node.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
HOME = Path.home()
DEFAULT_SECRETS = "NOUGEN_AGY_MSG_TOKEN,NOUGEN_USER_ORIGIN_TOKEN,KAEDRA_GATEWAY_TOKEN,NGS_NODE_TOKEN"
# Shared worked example for the owner-origin signing form. Its hash is a
# contract row: if two nodes disagree here they are not interoperable.
WORKED_EXAMPLE_FIELDS = ("restart relay", "n1", "1788433000", "do the thing")


def _env_path(key: str, default: "Path | None") -> "Path | None":
    raw = os.environ.get(key, "").strip()
    return Path(raw) if raw else default


def sha16(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return "MISSING"


def git(repo: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else "ERR"
    except (OSError, subprocess.SubprocessError):
        return "ERR"


def secret_fingerprint(repo: Path, key: str) -> str:
    """sha256[:12] of the vault value via the repo's keymaker, never the value."""
    py = repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        return "NO-VENV"
    code = ("import sys,hashlib; sys.path.insert(0,{src!r});"
            "from nougen_shards import keymaker; v=keymaker.get_secret({key!r});"
            "print(hashlib.sha256(v.encode()).hexdigest()[:12] if v else 'UNSET')").format(src=str(repo / "src"), key=key)
    try:
        r = subprocess.run([str(py), "-c", code], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or "ERR"
    except (OSError, subprocess.SubprocessError):
        return "ERR"


def listening(port: int) -> str:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        return "LISTENING"
    except OSError:
        return "closed"
    finally:
        s.close()


def contract_rows(bus_dir: Path) -> list:
    """Hash of the canonical signing bytes and the limits, from the running gate module."""
    rows = []
    sys.path.insert(0, str(bus_dir))
    try:
        import importlib
        sys.modules.pop("_agy_live_delivery", None)
        gate = importlib.import_module("_agy_live_delivery")
        b = gate.canonical_signing_input(*WORKED_EXAMPLE_FIELDS)
        rows.append(("contract:origin_signing_bytes", "sha256[:16] of worked example", hashlib.sha256(b).hexdigest()[:16], ""))
        rows.append(("contract:origin_limits", "-", "max_age {} skew {}".format(gate.SIGNATURE_MAX_AGE_S, gate.SIGNATURE_FUTURE_SKEW_S), "header X-NGS-Token"))
        rows.append(("contract:gate_policy", "-", getattr(gate, "POLICY_VERSION", "?"), ""))
    except Exception as exc:  # noqa: BLE001 - a node without the gate module still gets a manifest
        rows.append(("contract:origin_signing_bytes", "-", "MISSING", "gate module not importable: {}".format(type(exc).__name__)))
    finally:
        try:
            sys.path.remove(str(bus_dir))
        except ValueError:
            pass
    return rows


def build() -> dict:
    repo = _env_path("NOUGEN_SHARDS_REPO", HERE.parents[1])
    relay = _env_path("NOUGEN_RELAY_DIR", HOME / "NouGenRelay")
    bus = _env_path("NOUGEN_BUS_DIR", None) or ((HOME / ".nougen" / "bin") if (HOME / ".nougen" / "bin").is_dir() else repo / "tools")
    hooks = _env_path("NOUGEN_HOOKS_DIR", HOME / ".claude" / "hooks")
    registry = _env_path("NOUGEN_CC_SESSIONS", HOME / ".nougen" / "cc_sessions.json")
    secrets = [s for s in os.environ.get("NOUGEN_MANIFEST_SECRETS", DEFAULT_SECRETS).split(",") if s.strip()]

    rows = []  # (component, path, hash/version, notes)
    rows.append(("repo:nougenshards", str(repo), "{}@{}".format(git(repo, "branch", "--show-current"), git(repo, "rev-parse", "--short=12", "HEAD")),
                 "dirty:" + (git(repo, "status", "--porcelain").replace("\n", ";")[:160] or "clean")))
    if relay and (relay / ".handoffs").is_dir():
        rows.append(("repo:NouGenRelay", str(relay), "{}@{}".format(git(relay, "branch", "--show-current"), git(relay, "rev-parse", "--short=12", "HEAD")), ""))
    for f in ("nougenmsg_node.py", "relay_watch_node.py", "_agy_live_delivery.py", "sig_eval.py", "gate_eval.py"):
        rows.append(("bus:" + f, str(bus / f), sha16(bus / f), ""))
        canon = repo / "tools" / f
        if canon.exists() and bus != repo / "tools":
            rows.append(("canonical:tools/" + f, str(canon), sha16(canon),
                         "SAME as running" if sha16(canon) == sha16(bus / f) else "DRIFTED from running"))
    for f in sorted(p.name for p in hooks.glob("*.py")) if hooks.is_dir() else []:
        rows.append(("hook:" + f, str(hooks / f), sha16(hooks / f), ""))
    rows.extend(contract_rows(bus))
    for key in secrets:
        rows.append(("secret-fp:" + key, "vault", secret_fingerprint(repo, key), "sha256[:12] of value; value never emitted"))
    try:
        n = len(json.loads(registry.read_text())) if registry.exists() else 0
    except (OSError, ValueError):
        n = "ERR"
    rows.append(("state:cc_sessions", str(registry), "-", "entries={}".format(n)))
    rows.append(("service:bus_port", "127.0.0.1:{}".format(os.environ.get("NOUGEN_AGY_MSG_PORT", "8766")), "-", listening(int(os.environ.get("NOUGEN_AGY_MSG_PORT", "8766")))))
    rows.append(("runtime:python", sys.executable, "-", sys.version.split()[0]))
    return {
        "node": os.environ.get("NOUGEN_NODE_NAME", "").strip() or socket.gethostname().split(".")[0].lower(),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "components": [{"component": c, "path": p, "hash_or_version": h, "notes": n} for c, p, h, n in rows],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()
    m = build()
    if args.json:
        print(json.dumps(m, indent=2))
        return 0
    print("node={} generated={}".format(m["node"], m["generated_utc"]))
    for c in m["components"]:
        print("{:<40} {:<18} {}".format(c["component"], c["hash_or_version"], c["notes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
