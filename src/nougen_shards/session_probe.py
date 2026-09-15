"""Native hi/bye/hijack session probes — the cross-platform, node-agnostic
successor to Yuki-Ai's Windows-only hi_probe.py / bye_probe.py / yuki_hijack.py.

Where those scripts hardcode C:\\Users\\super\\Outpost paths and a private
antigravity_memory.db, these probes read NOUGEN_HOME / repo discovery and
reuse this package's own handoff, machine, and relay plumbing — so the same
`nougen hi` / `nougen bye` works unmodified on phoebus, blade, or whoart.

hi   — session open: identity, fleet pulse, open handoffs, shard counts.
bye  — session close: dirty-repo sweep, handoff write, next-session primer.
hijack — force a foreign/legacy handoff or shard record to point at this
         node's canonical paths, for migrating an import from another agent.
"""
from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import handoff, machine

# Repos this probe sweeps for dirty state. Override with NOUGEN_PROBE_REPOS
# (":"-separated absolute paths). Falls back to this repo plus any sibling
# checkouts one level up that look like git repos.
_ENV_REPOS = os.environ.get("NOUGEN_PROBE_REPOS")

# Ports a leftover dev/mesh process is likely bound to. Node-agnostic — no
# assumption about which ones this machine actually runs.
DEV_SERVER_PORTS = [
    (3000, "Node/React dev"),
    (5173, "Vite dev"),
    (8000, "Python HTTP/dev"),
    (8080, "Generic dev"),
    (8765, "Mesh service"),
    (4444, "NGS node (primary)"),
    (4445, "NGS node (secondary)"),
    (11434, "Ollama"),
]


def _discover_repos() -> List[Path]:
    if _ENV_REPOS:
        return [Path(p) for p in _ENV_REPOS.split(":") if p.strip()]
    repos = [handoff.PROJECT_ROOT]
    parent = handoff.PROJECT_ROOT.parent
    try:
        for child in parent.iterdir():
            if child.is_dir() and (child / ".git").exists() and child != handoff.PROJECT_ROOT:
                repos.append(child)
    except OSError:
        pass
    return repos


def _repo_git_status(repo: Path) -> Dict:
    def run(args):
        try:
            r = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                                text=True, timeout=8, check=False)
            return r.stdout.strip() if r.returncode == 0 else ""
        except OSError:
            return ""

    porcelain = run(["status", "--porcelain"])
    changes = [l for l in porcelain.splitlines() if l.strip()]
    unpushed_raw = run(["rev-list", "--count", "@{u}..HEAD"])
    return {
        "repo": repo.name,
        "path": str(repo),
        "branch": run(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown",
        "last_commit": run(["log", "-1", "--oneline"]),
        "dirty": len(changes),
        "changes": changes[:10],
        "unpushed": int(unpushed_raw) if unpushed_raw.isdigit() else 0,
    }


def _check_port(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.75)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def _fleet_pulse() -> Dict[str, bool]:
    """Best-effort reachability of sibling nodes, via SSH config aliases
    already used fleet-wide (blade1tb, whoart) rather than a private
    fleet_topology.json. Never raises — a missing ssh config just means the
    node reports unknown."""
    pulse: Dict[str, bool] = {}
    for host in ("blade1tb", "whoart"):
        try:
            r = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=4", "-o", "BatchMode=yes", host, "hostname"],
                capture_output=True, text=True, timeout=6, check=False,
            )
            pulse[host] = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            pulse[host] = False
    return pulse


@dataclass
class HiReport:
    identity: Dict[str, str]
    open_handoffs: int = 0
    latest_goal: Optional[str] = None
    fleet_pulse: Dict[str, bool] = field(default_factory=dict)
    orphan_ports: List[tuple] = field(default_factory=list)


@dataclass
class ByeReport:
    repos: List[Dict] = field(default_factory=list)
    total_dirty: int = 0
    total_unpushed: int = 0
    handoff_path: Optional[str] = None
    orphan_ports: List[tuple] = field(default_factory=list)
    primer: str = ""


def run_hi(fleet: bool = True) -> HiReport:
    """Session-open probe. Read-only — never writes a handoff."""
    identity = machine.machine_identity()
    feed = handoff.handoff_feed(limit=25)
    open_count = sum(1 for h in feed if h.get("live_status") not in ("complete", "acknowledged"))
    latest_goal = feed[0].get("goal") if feed else None
    orphan = [(p, label) for p, label in DEV_SERVER_PORTS if _check_port(p)]
    pulse = _fleet_pulse() if fleet else {}
    return HiReport(
        identity=identity,
        open_handoffs=open_count,
        latest_goal=latest_goal,
        fleet_pulse=pulse,
        orphan_ports=orphan,
    )


def run_bye(
    agent: Optional[str] = None,
    goal: Optional[str] = None,
    summary: str = "",
    dry_run: bool = False,
) -> ByeReport:
    """Session-close probe: sweep dirty repos, write a handoff, hand back a
    3-line primer for whoever picks this up next."""
    repos = [_repo_git_status(r) for r in _discover_repos() if r.exists()]
    total_dirty = sum(r["dirty"] for r in repos)
    total_unpushed = sum(r["unpushed"] for r in repos)
    orphan = [(p, label) for p, label in DEV_SERVER_PORTS if _check_port(p)]

    handoff_path = None
    if not dry_run:
        msg = summary or (
            f"Session closed with {total_dirty} dirty file(s) across "
            f"{sum(1 for r in repos if r['dirty'])} repo(s)."
        )
        path = handoff.create_handoff(message=msg, agent=agent, goal=goal)
        handoff_path = str(path) if path else None

    dirty_repos = [r["repo"] for r in repos if r["dirty"]]
    primer_bits = []
    if dirty_repos:
        primer_bits.append(f"Dirty: {', '.join(dirty_repos)}")
    if orphan:
        primer_bits.append(f"Ports still up: {', '.join(str(p) for p, _ in orphan)}")
    primer = " | ".join(primer_bits) or "Clean handoff — nothing pending."

    return ByeReport(
        repos=repos,
        total_dirty=total_dirty,
        total_unpushed=total_unpushed,
        handoff_path=handoff_path,
        orphan_ports=orphan,
        primer=primer,
    )


def run_hijack(handoff_id: str, agent: Optional[str] = None) -> Dict:
    """Repoint a handoff record written on/for a foreign node onto this
    node's canonical identity — for adopting an import from another agent's
    probe (e.g. a migrated Yuki-Ai bye_probe record) into native handoffs."""
    path, data = handoff._find_handoff(handoff_id=handoff_id)
    if data is None or path is None:
        return {"ok": False, "error": f"handoff {handoff_id} not found"}
    identity = machine.machine_identity()
    data["hijacked_by"] = identity
    data["hijacked_agent"] = agent or handoff.detect_current_agent()
    handoff._atomic_write_json(path, data)
    return {"ok": True, "id": handoff_id, "identity": identity, "path": str(path)}
