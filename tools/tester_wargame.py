"""War-game the NouGen tester package as a clean, non-owner identity.

Runs the package the way a new tester would, on a scratch home with a made-up
identity, and fails if any output names the owner's machines, hosts, accounts
or paths.

    python tools/tester_wargame.py --repos <dir with the ten checkouts> [--json]

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

#: Words that must never reach a tester's screen. This is the test's own
#: vocabulary of the owner's fleet, which is why it is allowed to name it.
OWNER = re.compile(
    r"(?i)\b(blade1tb|blade|phoebus|whoart|kaedra|apollo|hyperion|kushboy\w*|aiwithdav3|g-whoentertains|"
    r"whoentertains|superdave\w*)\b|nougenai\.com|The Observatory|Watchtower|C:\\\\Users\\\\super|/Users/kushboygroup|"
    r"192\.168\.1\.\d+")

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
    ns = ap.parse_args(argv)
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
