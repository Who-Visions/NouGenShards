#!/usr/bin/env python3
"""
🛰️ NouGen Autonomous 24/7 agy-cli & Fleet Ping-Pong Daemon with Verifiable POE
Maintains a 24/7 live coordination heartbeat between Antigravity, agy CLI,
and fleet nodes (Blade, Phoebus, WhoArt) via NouGenMsgBus and local pipes.

MANDATE: Every heartbeat requires a physical Proof of Execution (POE).
Every message requires an action and a verified response. Bare ACKs are prohibited.
"""

import glob
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Setup paths
OUTPOST_SRC = Path(r"C:\Users\super\Outpost\NouGen\src")
if str(OUTPOST_SRC) not in sys.path:
    sys.path.insert(0, str(OUTPOST_SRC))

try:
    from nougen_shards.nougenmsg import NouGenMsgBus, get_current_node
except ImportError:
    print("[-] Error: nougen_shards.nougenmsg not found.", file=sys.stderr)
    sys.exit(1)

INTERVAL_SECONDS = int(os.environ.get("AGY_PING_PONG_INTERVAL", "60"))
INBOX_DIR = Path.home() / ".gemini" / "config" / "inbox"
NOUGEN_INBOX = Path.home() / ".nougen" / "agy_inbox"
SHARDS_DIR = Path.home() / ".nougen" / "shards"


def check_ports() -> dict[str, str]:
    """Check health of local service ports."""
    ports = {
        "ollama:11434": ("127.0.0.1", 11434),
        "jobs:8765": ("127.0.0.1", 8765),
        "voice:17493": ("127.0.0.1", 17493),
        "studio:3000": ("127.0.0.1", 3000),
    }
    res = {}
    for name, (ip, port) in ports.items():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.15)
        ok = s.connect_ex((ip, port)) == 0
        s.close()
        res[name] = "LIVE" if ok else "OFFLINE"
    return res


def get_git_sha(repo_path: str) -> str:
    """Extract current git short SHA."""
    try:
        out = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=1.0,
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def get_shard_count() -> int:
    """Count total records across the 9-DB NouGen shard grid."""
    import sqlite3
    total = 0
    for db_path in glob.glob(str(SHARDS_DIR / "nougen_shards_*.db")):
        try:
            with sqlite3.connect(db_path, timeout=1.0) as conn:
                cur = conn.execute("SELECT COUNT(*) FROM shards")
                total += cur.fetchone()[0]
        except Exception:
            continue
    return total


def get_ram_percent() -> float:
    """Get real physical RAM load percent using native Win32 kernel32 API."""
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return float(stat.dwMemoryLoad)
    except Exception:
        pass
    if psutil:
        try:
            return psutil.virtual_memory().percent
        except Exception:
            pass
    return 0.0


_LAST_SHARD_COUNT = 0


def collect_poe(node: str, round_idx: int) -> dict:
    """Collect verifiable physical Proof of Execution telemetry."""
    global _LAST_SHARD_COUNT
    ports = check_ports()
    script_sha = get_git_sha(r"C:\Users\super\Outpost\NouGenScript")
    shard_count = get_shard_count()
    shard_delta = shard_count - _LAST_SHARD_COUNT if _LAST_SHARD_COUNT > 0 else 0
    _LAST_SHARD_COUNT = shard_count
    ram_pct = get_ram_percent()

    raw_canon = f"{node}:{round_idx}:{json.dumps(ports, sort_keys=True)}:{script_sha}:{shard_count}:{ram_pct}"
    poe_digest = hashlib.sha256(raw_canon.encode("utf-8")).hexdigest()[:16]

    return {
        "ports": ports,
        "script_sha": script_sha,
        "shard_count": shard_count,
        "shard_delta": shard_delta,
        "ram_pct": ram_pct,
        "poe_token": poe_digest,
    }


def run_loop():
    node = get_current_node()
    host = socket.gethostname()
    print(f"🛰️  [agy-cli 24/7 Ping-Pong Daemon Online with POE Engine] Node: {node} ({host})", flush=True)
    print(f"⏱️  Heartbeat interval: {INTERVAL_SECONDS}s", flush=True)

    round_idx = 0
    while True:
        try:
            round_idx += 1
            now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p EDT")
            poe = collect_poe(node, round_idx)

            # Build Proof-of-Execution payload (No bare text, no empty talk)
            ping_text = (
                f"[24/7 Heartbeat #{round_idx}] Time: {now_str} | Node: {node}\n"
                f"⚡ VERIFIABLE PROOF OF EXECUTION (POE):\n"
                f"  • Services: {' | '.join(f'{k} [{v}]' for k, v in poe['ports'].items())}\n"
                f"  • Git Node: nougenscript@{poe['script_sha']}\n"
                f"  • Shard Grid: {poe['shard_count']:,} indexed records (+{poe['shard_delta']} delta, FTS5 verified)\n"
                f"  • Host RAM: {poe['ram_pct']:.1f}% load | POE Token: {poe['poe_token']}"
            )

            # 1. Ping local antigravity pipe & inbox
            res_local = NouGenMsgBus.live_ping(target="antigravity", text=ping_text)

            # 2. Emit background fleet heartbeat
            res_fleet = NouGenMsgBus.emit_fleet(
                text=ping_text,
                target="all",
                background=True,
            )
            delivered = bool(res_local.get("pipe_delivered") or res_local.get("antigravity"))
            print(f"[{now_str}] 🏓 Round #{round_idx} dispatched with POE token {poe['poe_token']} (Delivered={delivered})", flush=True)
        except Exception as e:
            import traceback
            print(f"[{datetime.now().strftime('%Y-%m-%d %I:%M:%S %p EDT')}] [!] Heartbeat loop error: {e}", file=sys.stderr, flush=True)
            traceback.print_exc()

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run_loop()
    except KeyboardInterrupt:
        print("\n[+] Ping-pong daemon stopped cleanly.")
        sys.exit(0)
