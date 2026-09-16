#!/usr/bin/env python3
"""
Zombie & Duplicate Process Reaper for NouGen Fleet.
Scans active running processes for duplicate instances of daemons/workers
(e.g., antigravity_wake_daemon.py, relay_watch_node.py, duplicate python daemons)
and safely terminates older/duplicate instances, preserving the newest active worker.
"""
import os
import sys
import time
import signal
import argparse
import subprocess
from typing import Dict, List, Tuple

TARGET_SCRIPTS = [
    "antigravity_wake_daemon.py",
    "relay_watch_node.py",
    "nougenmsg_node.py",
    "kaedra_wake_daemon.py"
]

def get_running_processes() -> List[Tuple[int, float, str]]:
    """Returns list of (pid, start_time_epoch, command_str)."""
    procs = []
    try:
        res = subprocess.run(["ps", "-eo", "pid,etime,command"], capture_output=True, text=True, check=True)
        for line in res.stdout.strip().split("\n")[1:]:
            parts = line.strip().split(None, 2)
            if len(parts) == 3:
                pid = int(parts[0])
                cmd = parts[2]
                procs.append((pid, cmd))
    except Exception as e:
        print(f"Error fetching processes: {e}")
    return procs

def reap_duplicates(dry_run: bool = False) -> Dict[str, List[int]]:
    """Identifies and terminates duplicate running instances of target scripts."""
    procs = get_running_processes()
    grouped: Dict[str, List[int]] = {}

    for pid, cmd in procs:
        for script in TARGET_SCRIPTS:
            if script in cmd and "grep" not in cmd and pid != os.getpid():
                grouped.setdefault(script, []).append(pid)

    reaped: Dict[str, List[int]] = {}
    for script, pids in grouped.items():
        if len(pids) > 1:
            # Sort PIDs: newest PID (highest number) kept, older PIDs terminated
            pids_sorted = sorted(pids)
            keep_pid = pids_sorted[-1]
            to_kill = pids_sorted[:-1]
            reaped[script] = to_kill

            print(f"🎯 Target '{script}': Found {len(pids)} instances. Preserving newest PID {keep_pid}.")
            for pid in to_kill:
                if dry_run:
                    print(f"  [DRY-RUN] Would kill duplicate PID {pid}")
                else:
                    try:
                        print(f"  ⚡ Terminating duplicate PID {pid}...")
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(0.1)
                    except ProcessLookupError:
                        pass
                    except Exception as exc:
                        print(f"  ⚠️ Error killing PID {pid}: {exc}")
        else:
            print(f"✅ Target '{script}': Clean (1 instance, PID {pids[0]})")

    return reaped

def main():
    parser = argparse.ArgumentParser(description="Zombie & Duplicate Process Reaper")
    parser.add_argument("--dry-run", action="store_true", help="Print duplicate PIDs without killing them")
    args = parser.parse_args()

    print("🧟 NouGen Zombie & Duplicate Process Reaper")
    reaped = reap_duplicates(dry_run=args.dry_run)
    total_killed = sum(len(v) for v in reaped.values())
    print(f"\n✨ Operation complete. Terminated {total_killed} duplicate zombie process(es).")

if __name__ == "__main__":
    main()
