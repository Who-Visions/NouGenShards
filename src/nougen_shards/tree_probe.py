"""Process provenance & import resolution probe.

Kills the 'worktree vs running process' and 'network share vs local tree' illusion.
Allows any node or CLI operator to discover:
1. What PID is running a command
2. Its actual working directory (cwd)
3. Its effective PYTHONPATH
4. The exact resolved path of an imported module in production RAM
5. Remote node HTTP health inspection (patterns, fingerprint, journal_mode, deploy_sha)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
    except OSError:
        return ""


def find_pids(pattern: str) -> list[tuple[int, str]]:
    """Return (pid, cmdline) matching pattern."""
    out, found = _run(["ps", "-axo", "pid=,command="]), []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid, _, cmd = line.partition(" ")
        if pattern in cmd and "tree_probe" not in cmd and pid.isdigit():
            found.append((int(pid), cmd.strip()))
    return found


def cwd_of(pid: int) -> str | None:
    """Working directory of a live process. Unix only; None if unavailable."""
    for line in _run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def pythonpath_of(pid: int) -> str | None:
    """PYTHONPATH from the process's OWN environment."""
    for token in _run(["ps", "eww", str(pid)]).split():
        if token.startswith("PYTHONPATH="):
            return token[len("PYTHONPATH="):]
    return None


def resolve_module_roots(module: str, roots: list[str]) -> list[str]:
    """Every file satisfying module under roots in search order. First is winning."""
    rel = os.path.join(*module.split(".")) + ".py"
    hits = []
    for root in roots:
        if not root:
            continue
        for candidate in (os.path.join(root, rel), os.path.join(root, "src", rel)):
            if os.path.isfile(candidate) and candidate not in hits:
                hits.append(candidate)
    return hits


def count_marker(path: str, marker: str) -> int:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return len(re.findall(marker, handle.read()))
    except OSError:
        return -1


def inspect_node_health(url: str, timeout: float = 10.0) -> dict[str, Any]:
    """Query a node's /health endpoint and return verified operational parameters."""
    target_url = url.rstrip("/")
    if not target_url.endswith("/health"):
        target_url += "/health"

    req = urllib.request.Request(
        target_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "nougen-tree-probe/1.0"
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def probe_local_tree(module: str = "nougen_shards.brain_scan.redaction",
                     marker: str = r"re\.compile",
                     expect: Optional[int] = 29,
                     proc_pattern: str = "app.py") -> dict[str, Any]:
    """Run full local tree and PID provenance audit."""
    procs = find_pids(proc_pattern)
    results = []
    all_ok = True

    if not procs:
        return {
            "status": "error",
            "message": f"No process matched pattern: {proc_pattern!r}",
            "processes": []
        }

    for pid, cmd in procs:
        cwd = cwd_of(pid)
        ppath = pythonpath_of(pid)
        roots = (ppath.split(os.pathsep) if ppath else []) + ([cwd] if cwd else [])
        hits = resolve_module_roots(module, roots)

        resolved_file = hits[0] if hits else None
        marker_count = count_marker(resolved_file, marker) if resolved_file else -1
        is_expected = (expect is None) or (marker_count == expect)

        if not is_expected or not resolved_file:
            all_ok = False

        results.append({
            "pid": pid,
            "command": cmd,
            "cwd": cwd,
            "pythonpath": ppath,
            "resolved_file": resolved_file,
            "shadow_files": hits[1:],
            "marker_count": marker_count,
            "is_expected": is_expected
        })

    return {
        "status": "ok" if all_ok else "mismatch",
        "processes": results
    }
