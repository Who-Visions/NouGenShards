"""
NouGen Dynamic Process Supervisor & Zombie Killer.
Identifies and surgically terminates real orphan processes (whose parent process has died)
while strictly protecting active IDE workers, system daemons, and attached child tasks.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

# Target executables that commonly become orphaned in agentic developer environments
TARGET_EXECUTABLES = {
    "node.exe",
    "python.exe",
    "pythonw.exe",
    "cloudflared.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "tauri.exe",
    "cargo.exe",
    "rustc.exe",
    "esbuild.exe",
    "ngrok.exe",
    "uvicorn.exe",
}

# Processes that must NEVER be touched under any circumstances
CRITICAL_WHITELIST_NAMES = {
    "system",
    "secure system",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "dwm.exe",
    "explorer.exe",
    "spoolsv.exe",
    "antigravity.exe",
    "code.exe",
    "cursor.exe",
    "ollama.exe",
    "ollama_llama_server.exe",
    "claude.exe",
    "powertoys.awake.exe",
}

# Substrings in command lines that indicate protected persistent infrastructure
PROTECTED_COMMAND_PATTERNS = [
    "antigravity",
    "ollama",
    "language_server",
    "mcp_server",
    "vscode",
    "powertoys",
    "node_main.cmd",  # Scheduled task runner
]


@dataclass
class ZombieProcess:
    pid: int
    name: str
    ppid: int
    parent_alive: bool
    parent_name: Optional[str]
    mem_mb: float
    command_line: str
    is_orphan: bool
    risk_level: str  # "SAFE_TO_KILL", "SUSPICIOUS", "PROTECTED"
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "ppid": self.ppid,
            "parent_alive": self.parent_alive,
            "parent_name": self.parent_name,
            "mem_mb": self.mem_mb,
            "command_line": self.command_line,
            "is_orphan": self.is_orphan,
            "risk_level": self.risk_level,
            "reason": self.reason,
        }


class ZombieHunter:
    """Intelligent process tree supervisor and zombie killer."""

    def __init__(self):
        self.my_pid = os.getpid()
        self.ancestor_pids: Set[int] = {self.my_pid}
        self.registered_pids = self._get_registered_pid_files()

    def _get_registered_pid_files(self) -> Set[int]:
        """Collects PIDs stored in .nougen log and state pidfiles to protect intentional daemons."""
        pids = set()
        home = Path.home()
        for cand_dir in [home / ".nougen" / "logs", home / ".nougen" / "state", home / ".nougen" / "bin"]:
            if cand_dir.is_dir():
                for pf in cand_dir.glob("*.pid"):
                    try:
                        val = pf.read_text(encoding="utf-8").strip()
                        if val.isdigit():
                            pids.add(int(val))
                    except Exception:
                        pass
        return pids

    def _compute_ancestor_pids(self, all_pids: Dict[int, Dict[str, Any]]) -> Set[int]:
        """Walks up process tree in-memory from current process to protect caller and ancestors."""
        ancestors = {self.my_pid}
        cur = self.my_pid
        for _ in range(20):
            p = all_pids.get(cur)
            if not p:
                break
            ppid = p.get("ParentProcessId", 0)
            if ppid <= 4 or ppid in ancestors:
                break
            ancestors.add(ppid)
            cur = ppid
        return ancestors

    def get_process_table(self) -> List[Dict[str, Any]]:
        """Queries the live Windows process table via WMI/CIM in a single batch (<600ms)."""
        ps_query = (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId, ParentProcessId, Name, CommandLine, WorkingSetSize | "
            "ConvertTo-Json -Compress"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_query],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        if res.returncode != 0 or not res.stdout.strip():
            logger.error("Failed to query Win32_Process: %s", res.stderr)
            return []

        try:
            data = json.loads(res.stdout.strip())
            if isinstance(data, dict):
                return [data]
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error("JSON decode error querying process table: %s", e)
            return []

    def scan(self) -> List[ZombieProcess]:
        """Scans process tree, tests parent liveness, and identifies real orphaned zombies."""
        raw_procs = self.get_process_table()
        all_pids: Dict[int, Dict[str, Any]] = {p.get("ProcessId", 0): p for p in raw_procs}
        self.ancestor_pids = self._compute_ancestor_pids(all_pids)

        results: List[ZombieProcess] = []

        for p in raw_procs:
            pid = p.get("ProcessId", 0)
            ppid = p.get("ParentProcessId", 0)
            name = (p.get("Name") or "").strip()
            name_lower = name.lower()
            cmd = (p.get("CommandLine") or "").strip()
            cmd_lower = cmd.lower()
            ws_bytes = p.get("WorkingSetSize") or 0
            mem_mb = round(ws_bytes / (1024 * 1024), 1)

            # Check parent existence
            parent_proc = all_pids.get(ppid)
            parent_alive = parent_proc is not None
            parent_name = parent_proc.get("Name") if parent_proc else None

            # Base classification
            is_target = name_lower in TARGET_EXECUTABLES
            is_critical = (
                pid <= 4 or
                name_lower in CRITICAL_WHITELIST_NAMES or
                pid in self.ancestor_pids
            )
            has_protected_cmd = any(pat in cmd_lower for pat in PROTECTED_COMMAND_PATTERNS)

            # Determine risk level and reason
            if is_critical or has_protected_cmd:
                risk = "PROTECTED"
                is_orphan = False
                reason = "Whitelisted critical infrastructure / active IDE stack"
            elif pid in self.registered_pids:
                risk = "PROTECTED"
                is_orphan = False
                reason = "Registered background service daemon (active pidfile in .nougen)"
            elif parent_alive:
                risk = "PROTECTED"
                is_orphan = False
                reason = f"Active child of live process [{parent_name}] (PID {ppid})"
            elif is_target:
                # Real zombie: target developer executable whose parent PID is completely dead
                risk = "SAFE_TO_KILL"
                is_orphan = True
                reason = f"Orphaned: Parent PID {ppid} is dead/gone from system table"
            else:
                # Other process whose parent died (e.g. system utility, browser helper)
                risk = "SUSPICIOUS"
                is_orphan = True
                reason = f"Parent PID {ppid} dead, but executable [{name}] not in dev target set"

            results.append(ZombieProcess(
                pid=pid,
                name=name,
                ppid=ppid,
                parent_alive=parent_alive,
                parent_name=parent_name,
                mem_mb=mem_mb,
                command_line=cmd,
                is_orphan=is_orphan,
                risk_level=risk,
                reason=reason,
            ))

        return results

    def sweep(self, kill: bool = False, force: bool = False) -> Dict[str, Any]:
        """Performs dynamic process inspection and optional surgical termination of confirmed zombies."""
        procs = self.scan()
        zombies = [p for p in procs if p.is_orphan and p.risk_level == "SAFE_TO_KILL"]
        suspicious = [p for p in procs if p.is_orphan and p.risk_level == "SUSPICIOUS"]
        total_reclaimable_mb = round(sum(z.mem_mb for z in zombies), 1)

        killed = []
        failed = []

        if kill and zombies:
            for z in zombies:
                try:
                    res = subprocess.run(
                        ["taskkill", "/F", "/PID", str(z.pid)],
                        capture_output=True, text=True, timeout=5
                    )
                    if res.returncode == 0:
                        killed.append({
                            "pid": z.pid,
                            "name": z.name,
                            "mem_mb": z.mem_mb,
                            "cmd": z.command_line[:80]
                        })
                    else:
                        failed.append({
                            "pid": z.pid,
                            "name": z.name,
                            "error": res.stderr.strip()
                        })
                except Exception as e:
                    failed.append({"pid": z.pid, "name": z.name, "error": str(e)})

        reclaimed_mb = round(sum(k["mem_mb"] for k in killed), 1)

        return {
            "mode": "KILL" if kill else "INSPECT",
            "zombies_found": len(zombies),
            "zombies": [z.to_dict() for z in zombies],
            "suspicious_found": len(suspicious),
            "total_reclaimable_mb": total_reclaimable_mb,
            "killed_count": len(killed),
            "killed": killed,
            "failed": failed,
            "reclaimed_mb": reclaimed_mb,
        }

    @staticmethod
    def render_report(sweep_data: Dict[str, Any], verbose: bool = False) -> str:
        """Renders a sleek, high-visibility terminal report with ANSI styling."""
        lines = []
        is_kill = sweep_data["mode"] == "KILL"

        lines.append("\n" + "=" * 66)
        lines.append("       🧟 NOUGEN DYNAMIC PROCESS SUPERVISOR & ZOMBIE HUNTER       ")
        lines.append("=" * 66)

        zombies = sweep_data["zombies"]
        reclaimable = sweep_data["total_reclaimable_mb"]

        if not zombies and not sweep_data.get("killed"):
            lines.append("  🟢 All developer processes are healthy! Zero dead-parent zombies.")
            lines.append("     All running node/python/worker processes are attached to live parents.")
            lines.append("-" * 66)
            return "\n".join(lines)

        if is_kill:
            lines.append(f"  ⚡ KILLED {sweep_data['killed_count']} ORPHANED ZOMBIES | RECLAIMED: {sweep_data['reclaimed_mb']} MB RAM")
            lines.append("-" * 66)
            lines.append(f"  {'PID':<7} | {'EXECUTABLE':<16} | {'PARENT':<14} | {'RAM (MB)':<10} | {'COMMAND'}")
            lines.append("  " + "-" * 62)
            for k in sweep_data["killed"]:
                cmd_trunc = k["cmd"][:35] + ("..." if len(k["cmd"]) > 35 else "")
                lines.append(f"  {k['pid']:<7} | {k['name']:<16} | 💀 [DEAD]      | {k['mem_mb']:>7.1f} MB | {cmd_trunc}")
        else:
            lines.append(f"  ⚠️  DETECTED {len(zombies)} ORPHANED ZOMBIE(S) | RECLAIMABLE: {reclaimable} MB RAM")
            lines.append("     These processes have completely DEAD parents and are abandoned.")
            lines.append("-" * 66)
            lines.append(f"  {'PID':<7} | {'EXECUTABLE':<16} | {'PARENT':<14} | {'RAM (MB)':<10} | {'COMMAND'}")
            lines.append("  " + "-" * 62)
            for z in zombies:
                cmd_trunc = z["command_line"][:35] + ("..." if len(z["command_line"]) > 35 else "")
                lines.append(f"  {z['pid']:<7} | {z['name']:<16} | 💀 PID {z['ppid']:<6} | {z['mem_mb']:>7.1f} MB | {cmd_trunc}")
            lines.append("-" * 66)
            lines.append("  💡 To surgically kill these confirmed zombies and reclaim RAM:")
            lines.append("     Run: nougen sweep --kill   (or global shortcut: 'sweep --kill')")

        lines.append("=" * 66 + "\n")
        return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NouGen Dynamic Process Supervisor & Zombie Killer")
    parser.add_argument("--kill", "-k", action="store_true", help="Surgically terminate confirmed dead-parent zombies")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show suspicious non-dev orphans")
    args = parser.parse_args()

    hunter = ZombieHunter()
    res = hunter.sweep(kill=args.kill)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(ZombieHunter.render_report(res, verbose=args.verbose))


if __name__ == "__main__":
    main()
