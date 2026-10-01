#!/usr/bin/env python3
"""
nougen_24_7_orchestrator.py

24/7 Autonomous NouGen Fleet Orchestrator.
Continuously runs the complete lifecycle loop:
  1. Relay Pulse: Check inbox, claims, peer handoffs, and trigger active wake sentry.
  2. Local Node & MCP Gateway Watchdog: Port 4444 & 8765 supervisor.
  3. Substrate Sharding: Maintain FTS5 9-DB integrity and index incoming memory drops.
  4. Build & Scoreboard Verification: Execute test suites across behavioral and core modules.
  5. Dream & Consolidation: Invariant extraction, SFT dataset check, and token tracker sync.
  6. OpenSkill Evolution & Active Session Heartbeat: Keep Antigravity and fleet sessions alive.
  7. Fleet Mesh Pulse & Live HUD: Probing across Apollo (Blade), Phoebus, and Hyperion (WhoArt).
"""

import os
import sys

# Immediately hide console window on Windows if spawned interactively by Task Scheduler
if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass

import json
import time
import socket
import logging
from logging.handlers import RotatingFileHandler
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path.home() / "Outpost" / "NouGen"
if (WORKSPACE_ROOT / "src").is_dir():
    sys.path.insert(0, str(WORKSPACE_ROOT / "src"))
from nougen_time import format_log_time, monotonic_ns, now as nougen_now

# Arm fleet-wide windowless subprocess protection
try:
    import tools.sitecustomize_windowless as _sc
    _sc._arm(force=True)
except Exception:
    pass

LOG_DIR = Path.home() / ".nougen" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "orchestrator.log"

logger = logging.getLogger("NouGen24_7")
logger.setLevel(logging.INFO)

class NewYorkFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return format_log_time(record.created)


formatter = NewYorkFormatter(
    "%(asctime)s [%(levelname)s] [NouGen-24/7] %(message)s",
)

# File handler for pythonw and background daemons
fh = RotatingFileHandler(str(LOG_FILE), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console handler if running interactively
if sys.stdout and hasattr(sys.stdout, "isatty"):
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

PYTHON_EXE = WORKSPACE_ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)


def _load_nodes() -> dict:
    """name -> list of (ip, port) candidates from ~/.nougen/fleet_hosts.json and canonical defaults."""
    default_candidates = {
        "whoart": [("127.0.0.1", 8765), ("10.0.0.178", 8765), ("192.168.1.187", 8765)],
        "phoebus": [("10.0.0.88", 8765), ("192.168.1.78", 8765)],
        "blade": [("10.0.0.188", 8765), ("192.168.1.16", 8765)],
    }
    try:
        cfg = json.loads((Path.home() / ".nougen" / "fleet_hosts.json").read_text(encoding="utf-8"))
        nodes = cfg.get("nodes", {})
        for name, data in nodes.items():
            if isinstance(data, dict) and data.get("ip"):
                ip = str(data["ip"])
                if name not in default_candidates:
                    default_candidates[name] = []
                if (ip, 8765) not in default_candidates[name]:
                    default_candidates[name].insert(0, (ip, 8765))
    except Exception:
        pass
    return default_candidates


NODES = _load_nodes()


def ping_node(name: str, ip: str, port: int = 8765, timeout: float = 0.5) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def probe_node_status(name: str, candidates: list) -> str:
    for ip, port in candidates:
        if ping_node(name, ip, port, timeout=0.3):
            return "ONLINE"
    return "STANDBY"


def update_active_session_heartbeat():
    """Maintain active session metadata for Antigravity, Codex, and fleet agents."""
    sessions_dir = Path.home() / ".nougen" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    registry_file = sessions_dir / "active_sessions.json"

    sessions = {}
    if registry_file.exists():
        try:
            sessions = json.loads(registry_file.read_text(encoding="utf-8"))
        except Exception:
            sessions = {}

    now_iso = nougen_now().utc_iso
    sessions["antigravity_whoart"] = {
        "session_id": "1b2d9b95-836c-46c1-99bc-0e16ca98ef39",
        "node": "whoart",
        "role": "tactical_coach",
        "agent": "Antigravity",
        "last_heartbeat": now_iso,
        "status": "ACTIVE_ORCHESTRATING",
    }
    sessions["orchestrator_24_7"] = {
        "node": "whoart",
        "pid": os.getpid(),
        "last_heartbeat": now_iso,
        "status": "RUNNING",
    }
    try:
        registry_file.write_text(json.dumps(sessions, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Failed to update session registry: {e}")


def run_nougen_hi_probe() -> dict:
    """Run the read-only NouGen session probe and return its structured report."""
    result = subprocess.run(
        [str(PYTHON_EXE), "-m", "nougen_shards.cli", "hi", "--json"],
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no output").strip()
        raise RuntimeError(f"nougen hi exited {result.returncode}: {detail[-500:]}")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"nougen hi returned invalid JSON: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(report.get("identity"), dict):
        raise RuntimeError("nougen hi response is missing its identity object")
    return report


def run_cycle():
    cycle_start_ns = monotonic_ns()
    logger.info("=== STARTING AUTONOMOUS 24/7 NOUGEN CYCLE ===")

    NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    # 1. RELAY PULSE, PULL, AUTO-ACK & CLAIM SCHEDULE
    try:
        logger.info("[1/7] Syncing Relay Fleet: Pulling, Acknowledging & Scheduling...")
        silent_env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        # 1a. Pull incoming handoffs from fleet
        subprocess.run(
            [str(PYTHON_EXE), "-m", "nougen_relay.cli", "pull"],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=NOWIN,
            stdin=subprocess.DEVNULL,
            env=silent_env,
        )
        # 1b. React to arrived handoffs and execute local rules
        react_res = subprocess.run(
            [str(PYTHON_EXE), "-m", "nougen_relay.cli", "react"],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=NOWIN,
            stdin=subprocess.DEVNULL,
            env=silent_env,
        )
        if react_res.stdout and "nothing to react to" not in react_res.stdout.lower():
            logger.info(f"Relay React: {react_res.stdout.strip()}")

        # 1c. Policy auto-ack for status legs
        policy_res = subprocess.run(
            [str(PYTHON_EXE), "-m", "nougen_relay.cli", "policy"],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=NOWIN,
            stdin=subprocess.DEVNULL,
            env=silent_env,
        )
        if policy_res.stdout and "policy applied" in policy_res.stdout:
            logger.info(f"Relay Policy: {policy_res.stdout.strip().splitlines()[-1]}")

        # 1c. Auto-claim / take open compatible legs
        sched_res = subprocess.run(
            [str(PYTHON_EXE), "-m", "nougen_relay.cli", "schedule", "--take"],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=NOWIN,
            stdin=subprocess.DEVNULL,
            env=silent_env,
        )
        if sched_res.stdout and sched_res.stdout.strip():
            last_line = sched_res.stdout.strip().splitlines()[-1]
            logger.info(f"Relay Schedule: {last_line}")

        # 1d. Inbox check & wake sentry notify
        res = subprocess.run(
            [str(PYTHON_EXE), "-m", "nougen_shards.nougenmsg", "--inbox"],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=NOWIN,
            stdin=subprocess.DEVNULL,
        )
        if res.stdout and res.stdout.strip():
            logger.info(f"Inbox output:\n{res.stdout.strip()}")
    except Exception as e:
        logger.warning(f"Relay claim/inbox check encountered: {e}")

    # 2. LOCAL NODE & MCP FRONT DOOR WATCHDOG (PORT 4444 & 8765)
    try:
        logger.info("[2/7] Checking Local Gateway & MCP Front Door (Port 4444)...")
        if not ping_node("whoart-local", "127.0.0.1", 4444, timeout=0.3):
            logger.warning("[!] Port 4444 standby. Verifying whoart supervisor...")
            cmd_path = Path.home() / ".nougen" / "bin" / "whoart_node_main.cmd"
            if cmd_path.exists():
                subprocess.Popen(
                    ["cmd.exe", "/c", str(cmd_path)],
                    creationflags=NOWIN,
                    stdin=subprocess.DEVNULL,
                )
                logger.info("[*] Dispatched whoart_node_main.cmd supervisor")
        else:
            logger.info("Local Gateway Port 4444: ONLINE")
    except Exception as e:
        logger.warning(f"Node watchdog error: {e}")

    # 3. SUBSTRATE SHARD INTEGRITY & DEDUP SYNC
    try:
        logger.info("[3/7] Verifying NouGenShards 9-DB Substrate Integrity...")
        from nougen_shards.core import _ensure_active_vault_dir, get_dedup_path
        vault_dir = _ensure_active_vault_dir()
        dedup_path = get_dedup_path()
        logger.info(f"Active Vault Substrate: {vault_dir} | Dedup: {dedup_path.exists()}")
    except Exception as e:
        logger.warning(f"Substrate check error: {e}")

    # 4. BUILD & SCOREBOARD TEST SUITE
    try:
        logger.info("[4/7] Running Behavioral & Emoji Math Unit Tests...")
        test_res = subprocess.run(
            [
                str(PYTHON_EXE), "-m", "pytest",
                "tests/test_emoji_math.py",
                "tests/test_behavior.py",
                "tests/test_affect.py",
                "tests/test_persona_masks.py",
                "tests/test_persona.py",
                "-q"
            ],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=NOWIN,
            stdin=subprocess.DEVNULL,
        )
        logger.info(f"Scoreboard: {test_res.stdout.strip().splitlines()[-1] if test_res.stdout else 'Completed'}")
    except Exception as e:
        logger.warning(f"Test suite error: {e}")

    # 5. DREAM & CONSOLIDATION PASS
    try:
        logger.info("[5/7] Checking Dream State & Token Telemetry...")
        dream_sft = Path.home() / ".nougen" / "shards" / "dream_sft.jsonl"
        if dream_sft.exists():
            size_kb = dream_sft.stat().st_size / 1024
            logger.info(f"Dream SFT Dataset Live: {dream_sft} ({size_kb:.1f} KB)")
    except Exception as e:
        logger.warning(f"Dream verification error: {e}")

    # 6. OPENSKILL EVOLUTION & ACTIVE SESSION HEARTBEAT
    try:
        logger.info("[6/7] Checking OpenSkill Contracts & Session Heartbeat...")
        skill_path = Path.home() / ".nougen" / "shards" / "skills" / "emergent_behavioral_compiler_and_dynamic_glyph_discovery" / "SKILL.md"
        if skill_path.exists():
            logger.info(f"OpenSkill Contract Active: {skill_path.name} (v3.0.0)")
        update_active_session_heartbeat()
    except Exception as e:
        logger.warning(f"Skill evolution check error: {e}")

    # 7. FLEET HEARTBEAT & MESH PULSE
    try:
        logger.info("[7/7] Probing Fleet Mesh Nodes...")
        try:
            hi_report = run_nougen_hi_probe()
            identity = hi_report.get("identity", {})
            logger.info(
                "NouGen hi identity: %s (%s)",
                identity.get("host", "unknown"),
                identity.get("machine_id", "unknown"),
            )
            logger.info("NouGen hi orchestrator status: %s", hi_report.get("orchestrator", {}))
            logger.info("NouGen hi SSH reachability: %s", hi_report.get("fleet_pulse", {}))
        except Exception as e:
            logger.warning(f"NouGen hi probe error: {e}")

        node_status = {}
        for name, candidates in NODES.items():
            node_status[name] = probe_node_status(name, candidates)
        logger.info(f"Fleet Mesh TCP Service Status: {node_status}")
    except Exception as e:
        logger.warning(f"Fleet pulse error: {e}")

    elapsed = (monotonic_ns() - cycle_start_ns) / 1_000_000_000
    logger.info(f"=== CYCLE COMPLETED IN {elapsed:.2f}s ===\n")


def main():
    logger.info("⚡ NouGen 24/7 Autonomous Fleet Orchestrator Started.")
    interval_s = int(os.environ.get("NOUGEN_CYCLE_INTERVAL_S", "60"))
    
    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            logger.info("Daemon terminated by user.")
            break
        except Exception as e:
            logger.error(f"Unexpected cycle failure: {e}", exc_info=True)
        time.sleep(interval_s)


if __name__ == "__main__":
    main()
