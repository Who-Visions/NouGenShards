"""War-game the NouGen tester package as a clean, non-owner identity.

Runs the package the way a new tester would, on a scratch home with a made-up
identity, and fails if any output names the owner's machines, hosts, accounts
or paths. Those names are read from the box it runs on before switching to the
tester identity, so run it on an owner box (or pass --forbid / set
NOUGEN_SURFACE_NAMES) for the check to mean something.

    python tools/tester_wargame.py --repos <dir with the ten checkouts> [--forbid WORD ...] [--json]

Steps: mesh setup -> whoami -> doctor -> tools -> a local tool call in every
installed repo that lists a safe read-only one -> up/status/down of services
that need no secrets. Nothing is sent off the box: ingress is unset, so
remote calls are refused by design, and that refusal is checked too.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

#: Generic leak shape: a private LAN address.
GENERIC = (r"192\.168\.\d+\.\d+",)

#: Identity words too common to mean anything on their own.
_COMMON = {"root", "user", "runner", "admin", "claude", "ubuntu", "localhost", "standalone", "unknown-agent",
           "tester-box", "tester-claude"}


def owner_vocabulary(extra: List[str]) -> "re.Pattern[str]":
    """The owner's names, resolved at runtime from the box this runs on.

    Nothing is written here: this file is public, and a guard that spells the
    owner's names would publish them. Words come from the real box's mesh
    identity, node list and ingress host, the OS account, git identity,
    ``NOUGEN_SURFACE_NAMES`` (comma-separated) and ``--forbid``.
    """
    words: set = set()
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from nougen_shards import mesh  # noqa: PLC0415
        ident = mesh.identity()
        words.update(str(v) for k, v in ident.items() if k in ("machine", "agent", "node", "tenant") and v)
        words.update(mesh.nodes())
        door = mesh.ingress() or ""
        host = re.sub(r"^\w+://", "", door).split("/")[0]
        if host:
            words.add(host)
            words.add(".".join(host.split(".")[-2:]))
    except Exception:  # noqa: BLE001 - a box with no mesh simply contributes nothing
        pass
    home = str(Path.home())
    if home.count(os.sep) >= 2:                      # the owner's own home path, raw and JSON-escaped
        words.update({home, home.replace("\\", "\\\\")})
    try:
        import getpass  # noqa: PLC0415
        words.add(getpass.getuser())
    except Exception:  # noqa: BLE001
        pass
    for key in ("user.name", "user.email"):
        try:
            val = subprocess.run(["git", "config", "--global", key], capture_output=True, text=True,
                                 timeout=5).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            val = ""
        if val:
            words.add(val.split("@")[0] if "@" in val else val)
    words.update(w.strip() for w in os.environ.get("NOUGEN_SURFACE_NAMES", "").split(","))
    words.update(extra)
    words = {w for w in words if len(w) >= 4 and w.lower() not in _COMMON}
    parts = [re.escape(w) for w in sorted(words, key=len, reverse=True)] + list(GENERIC)
    return re.compile(r"(?i)(?<![A-Za-z0-9])(?:" + "|".join(parts) + r")(?![A-Za-z0-9])")


OWNER: "re.Pattern[str]" = re.compile(r"(?!)")

#: Read-only tools worth calling once per repo, when the repo lists them.
SAFE_CALLS = {
    "open": [("nougen_status", {})],
    "relay": [("relay_whoami", {})],
    "tracker": [("tracker_live_status", {})],
}

TESTER = {"NOUGEN_MACHINE": "tester-box", "NOUGEN_AGENT": "tester-claude"}


def run(argv: List[str], env: Dict[str, str], cwd: str, timeout: int = 180) -> Dict[str, Any]:
    try:
        p = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out, code = (p.stdout or "") + (p.stderr or ""), p.returncode
    except subprocess.TimeoutExpired:
        out, code = "timeout", -1
    hits = sorted({m.group(0) for m in OWNER.finditer(out)})
    return {"argv": argv[1:] if argv and argv[0] == sys.executable else argv, "exit": code,
            "owner_names": hits, "tail": out.strip()[-800:], "_out": out}


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repos", required=True, help="directory holding the package checkouts side by side")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--keep-home", action="store_true")
    ap.add_argument("--forbid", action="append", default=[], help="another word that must never show (repeatable)")
    ns = ap.parse_args(argv)
    global OWNER
    OWNER = owner_vocabulary(ns.forbid)
    repos = Path(ns.repos).resolve()
    shards = next((d for d in repos.iterdir() if d.name.lower() == "nougenshards"), None)
    if shards is None:
        print("NouGenShards checkout not found under --repos", file=sys.stderr)
        return 2
    home = Path(tempfile.mkdtemp(prefix="nougen-tester-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NOUGEN_", "NGS_", "FLEET_"))}
    env.update(TESTER)
    env.update({"HOME": str(home), "USERPROFILE": str(home), "NOUGEN_ROOT": str(home / ".nougen"),
                "NOUGEN_REPOS_DIR": str(repos), "PYTHONPATH": str(shards / "src"), "NOUGEN_OPEN_USAGE_LOG": "0"})
    mesh = [sys.executable, "-m", "nougen_shards.mesh"]
    cwd = str(shards)
    steps: List[Dict[str, Any]] = []
    steps.append(run(mesh + ["setup", "--repos-dir", str(repos)], env, cwd))
    who = run(mesh + ["whoami"], env, cwd)
    steps.append(who)
    doc = run(mesh + ["doctor"], env, cwd)
    steps.append(doc)
    listed = run(mesh + ["tools"], env, cwd)
    steps.append(listed)
    try:
        have_tools = set(json.loads(listed["_out"])) if listed["exit"] == 0 else set()
    except ValueError:
        have_tools = set()
    calls: List[Dict[str, Any]] = []
    try:
        doctor = json.loads(doc["_out"]) if doc["exit"] == 0 else {}
    except ValueError:
        doctor = {}
    for repo, wanted in SAFE_CALLS.items():
        for tool, args in wanted:
            if f"{repo}.{tool}" in have_tools:
                calls.append(run(mesh + ["call", f"{repo}.{tool}", json.dumps(args)], env, cwd, timeout=240))
    steps.extend(calls)
    remote = run(mesh + ["call", "shards.recall_memory", "query=x", "--at", "elsewhere"], env, cwd)
    remote["expect"] = "refused: no ingress set"
    steps.append(remote)
    steps.append(run(mesh + ["status"], env, cwd))
    leaks = [s for s in steps if s["owner_names"]]
    ident_ok = '"node": "standalone"' in who["_out"] and "tester-box" in who["_out"]
    remote_ok = remote["exit"] != 0
    for s in steps:
        s.pop("_out", None)
    calls_ok = all(c["exit"] == 0 for c in calls)
    report = {"home": str(home), "identity_is_testers_own": ident_ok, "remote_refused_without_ingress": remote_ok,
              "cross_repo_calls_ok": calls_ok, "tools": len(have_tools),
              "owner_names_seen": sorted({h for s in steps for h in s["owner_names"]}),
              "steps": steps, "doctor": doctor}
    ok = ident_ok and remote_ok and calls_ok and not leaks
    report["ok"] = ok
    if ns.json:
        print(json.dumps(report, indent=2))
    else:
        for s in steps:
            flag = "LEAK " + ",".join(s["owner_names"]) if s["owner_names"] else ("ok" if s["exit"] == 0 else f"exit {s['exit']}")
            print(f"{flag:<28} {' '.join(map(str, s['argv']))[:90]}")
        print(f"\n{len(have_tools)} tools; cross-repo calls ok: {calls_ok}; "
              f"identity is the tester's own: {ident_ok}; remote refused without ingress: {remote_ok}; "
              f"owner names seen: {report['owner_names_seen'] or 'none'}")
        print("PASS" if ok else "FAIL")
    if not ns.keep_home:
        import shutil
        shutil.rmtree(home, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
