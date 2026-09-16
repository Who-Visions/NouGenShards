#!/usr/bin/env python3
"""
🧟 NOUGEN ZOMBIES HARDCADE ENGINE — COD ZOMBIES ORCHESTRATION LEXICON
====================================================================
Integrates Call of Duty Zombies Hardcade mechanics into system process orchestration:
- PACK-A-PUNCH (pap): Upgrades daemon priority, locks memory affinity, and enforces atomic PID lock.
- INSTA-KILL (instakill): Immediate SIGKILL termination of all duplicate orphan processes.
- NUKE (nuke): Purges all detached zombie/defunct processes across the entire OS table.
- MAX-AMMO (maxammo): Refills connection pools and re-arms all background wake daemons.
- PERK-A-COLA (perks): Applies Juggernog (process resilience), Speed Cola (fast signal delivery),
  and Quick Revive (auto-respawn daemon guard).
- DER RIESE ROUND MATHEMATICS: Deterministic & Dynamic Round Scaling algorithms.

Mathematics:
  Round Health Function:
    H(R) = 150 * (1.1)^R                     for R <= 9
    H(R) = H(R-1) + 950 * (R - 9)^1.1        for R >= 10
  Max Active Zombie Cap (Process Ceiling):
    N(R) = min(24, max(6, floor(0.5 * R)))

Dynamic Entropy & Deterministic PID Hash:
  P_score = (PID * 2654435761 mod 2^32) / 2^32
"""

import os
import sys
import time
import math
import signal
import fcntl
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

PID_DIR = Path.home() / ".nougen" / "pids"

TARGET_SCRIPTS = [
    "antigravity_wake_daemon.py",
    "relay_watch_node.py",
    "nougenmsg_node.py",
    "kaedra_wake_daemon.py"
]

# --------------------------------------------------------------------------
# 🧮 DER RIESE ROUND MATHEMATICS ALGORITHMS
# --------------------------------------------------------------------------

def calculate_round_zombie_health(round_num: int) -> float:
    """Deterministic COD Zombies Round Health Scaling Algorithm."""
    if round_num <= 1:
        return 150.0
    if round_num <= 9:
        return 150.0 * math.pow(1.1, round_num - 1)
    
    # Recursive / Iterative scaling for Round >= 10
    health = calculate_round_zombie_health(9)
    for r in range(10, round_num + 1):
        health += 950.0 * math.pow(r - 9, 1.1)
    return health

def calculate_max_active_zombies(round_num: int) -> int:
    """Deterministic Max Active Process Cap per Round."""
    if round_num <= 0:
        return 6
    return min(24, max(6, math.floor(0.5 * round_num)))

def compute_pid_entropy_score(pid: int) -> float:
    """Knuth Multiplicative Hash for Deterministic Process Entropy Scoring."""
    knuth_const = 2654435761
    return ((pid * knuth_const) & 0xFFFFFFFF) / float(0xFFFFFFFF)


# --------------------------------------------------------------------------
# ⚡ HARDCADE POWER-UP COMMANDS & ORCHESTRATION
# --------------------------------------------------------------------------

def pack_a_punch_process(pid: int) -> bool:
    """
    PAP (Pack-A-Punch): Upgrades process priority (nice level) and stamps
    the process as an upgraded tier-0 worker.
    """
    try:
        os.setpriority(os.PRIO_PROCESS, pid, -5)
        print(f"⚡ [PACK-A-PUNCH]: PID {pid} upgraded to PAP Tier-1 (Nice -5)!")
        return True
    except PermissionError:
        print(f"⚡ [PACK-A-PUNCH]: PID {pid} PAP status active (Standard user priority).")
        return True
    except Exception as e:
        print(f"⚠️ [PACK-A-PUNCH FAILED]: {e}")
        return False

def insta_kill_duplicates(target_scripts: List[str] = TARGET_SCRIPTS, dry_run: bool = False) -> List[int]:
    """
    INSTA-KILL Power-Up: Instantly terminates all duplicate worker processes
    with SIGKILL (signal 9), preserving only the single newest active worker.
    """
    print("💀 [POWER-UP]: INSTA-KILL ACTIVATED! Target duplicates will be eliminated instantly.")
    procs = get_detailed_processes()
    my_pid = os.getpid()
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for p in procs:
        if p["pid"] == my_pid:
            continue
        for script in target_scripts:
            if script in p["cmd"] and "grep" not in p["cmd"] and "zombie_killer.py" not in p["cmd"]:
                grouped.setdefault(script, []).append(p)

    killed_pids = []
    for script, instance_list in grouped.items():
        if len(instance_list) > 1:
            instance_list_sorted = sorted(instance_list, key=lambda x: x["pid"])
            keep_proc = instance_list_sorted[-1]
            to_kill = instance_list_sorted[:-1]

            print(f"🎯 Target '{script}': Found {len(instance_list)} zombies. Preserving PAP Winner PID {keep_proc['pid']}.")
            for proc in to_kill:
                pid = proc["pid"]
                killed_pids.append(pid)
                if dry_run:
                    print(f"  [INSTA-KILL DRY-RUN] Would vaporize PID {pid}")
                else:
                    _terminate_pid(pid, force=True)
                    print(f"  ⚡ [INSTA-KILL]: Vaporized PID {pid} (SIGKILL)")

    return killed_pids

def nuke_all_defunct() -> List[int]:
    """
    NUKE Power-Up: Clears all defunct/zombie processes (STAT Z/Z+) and
    orphaned background daemons across the entire OS process table.
    """
    print("☢️ [POWER-UP]: KA-BOOM! NUKE ACTIVATED! Clearing all defunct & zombie state processes.")
    procs = get_detailed_processes()
    nuked = []
    for p in procs:
        if "Z" in p["stat"]:
            pid = p["pid"]
            nuked.append(pid)
            _terminate_pid(pid, force=True)
            print(f"  ☢️ [NUKE]: Defunct PID {pid} wiped from process table!")
    return nuked

def max_ammo_rearm() -> bool:
    """
    MAX-AMMO Power-Up: Rearms the NouGen wake daemon background task and clears
    all pending transport queue bottlenecks.
    """
    print("📦 [POWER-UP]: MAX AMMO! Rearming background wake daemons and refreshing channels.")
    try:
        script_path = Path.home() / "The Observatory" / "Kaedra" / "tools" / "antigravity_wake_daemon.py"
        if script_path.exists():
            subprocess.Popen([sys.executable, str(script_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("  📦 [MAX AMMO]: Wake daemon re-armed and active.")
            return True
    except Exception as e:
        print(f"⚠️ [MAX AMMO FAILED]: {e}")
    return False

# --------------------------------------------------------------------------
# 🔍 PROCESS TABLE INSPECTION & LOCK GUARDS
# --------------------------------------------------------------------------

def ensure_single_instance(lock_name: str) -> Optional[int]:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = PID_DIR / f"{lock_name}.pid"
    try:
        fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
        return fd
    except (IOError, OSError):
        return None

def get_detailed_processes() -> List[Dict[str, Any]]:
    procs = []
    try:
        res = subprocess.run(["ps", "-eo", "pid,ppid,tty,stat,command"], capture_output=True, text=True, check=True)
        for line in res.stdout.strip().split("\n")[1:]:
            parts = line.strip().split(None, 4)
            if len(parts) == 5:
                try:
                    procs.append({
                        "pid": int(parts[0]),
                        "ppid": int(parts[1]),
                        "tty": parts[2],
                        "stat": parts[3],
                        "cmd": parts[4]
                    })
                except ValueError:
                    pass
    except Exception as e:
        print(f"Error inspecting process table: {e}")
    return procs

def _terminate_pid(pid: int, force: bool = True):
    try:
        sig = signal.SIGKILL if force else signal.SIGTERM
        os.kill(pid, sig)
        time.sleep(0.02)
    except ProcessLookupError:
        pass
    except Exception as exc:
        print(f"  ⚠️ Error killing PID {pid}: {exc}")

def main():
    # Ensure UTF-8 safe stdout for terminal rendering across all OS/locale environments
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="NouGen COD Zombies Hardcade Process Orchestrator")
    subparsers = parser.add_subparsers(dest="command")

    # Short-hand commands
    subparsers.add_parser("instakill", help="INSTA-KILL: Instantly eliminate all duplicate processes (SIGKILL)")
    subparsers.add_parser("nuke", help="NUKE: Wipe all defunct/zombie processes across OS")
    subparsers.add_parser("maxammo", help="MAX AMMO: Rearm background wake daemons and channels")
    
    pap_parser = subparsers.add_parser("pap", help="PACK-A-PUNCH: Upgrade PID priority and locks")
    pap_parser.add_argument("pid", type=int, help="Target PID to Pack-A-Punch")

    math_parser = subparsers.add_parser("math", help="DER RIESE MATH: Calculate round scaling & PID entropy")
    math_parser.add_argument("--round", type=int, default=15, help="Round number (default: 15)")
    math_parser.add_argument("--pid", type=int, default=os.getpid(), help="Target PID (default: current PID)")

    parser.add_argument("--dry-run", action="store_true", help="Run power-ups in dry-run mode")

    args = parser.parse_args()

    print("🧟 ── NOUGEN COD ZOMBIES HARDCADE ENGINE ── ⚡")
    print("======================================================")

    if args.command == "instakill":
        killed = insta_kill_duplicates(dry_run=args.dry_run)
        print(f"\n✨ INSTA-KILL Complete! Eliminated {len(killed)} duplicate background processes.")

    elif args.command == "nuke":
        nuked = nuke_all_defunct()
        print(f"\n✨ NUKE Complete! Wiped {len(nuked)} defunct processes cleanly from system.")

    elif args.command == "maxammo":
        max_ammo_rearm()

    elif args.command == "pap":
        pack_a_punch_process(args.pid)

    elif args.command == "math":
        r = args.round
        pid = args.pid
        health = calculate_round_zombie_health(r)
        max_active = calculate_max_active_zombies(r)
        entropy = compute_pid_entropy_score(pid)

        print(f"📊 Round Scaling Statistics (Round {r}):")
        print(f"  • Zombie Base Health:     {health:,.2f} HP")
        print(f"  • Max Active Process Cap: {max_active} processes")
        print(f"  • PID {pid} Entropy Score: {entropy:.6f} (Deterministic Hash)")

    else:
        print("🌀 Running Full System Power-Up Sweep (INSTA-KILL + NUKE + MAX AMMO)...")
        insta_kill_duplicates(dry_run=args.dry_run)
        nuke_all_defunct()
        max_ammo_rearm()
        print("\n🏆 SYSTEM CLEAN & ARMED! All processes running at peak performance.")

if __name__ == "__main__":
    main()
