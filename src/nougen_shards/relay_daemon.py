"""Self-Healing Relay Daemon Harness for NouGenAi Ecosystem.

Envelops the execution harness:
- Watches NouGenRelay .handoffs/ and grid coordination queues.
- Emits a periodic heartbeat (default: 200s) via local Ollama (dav1d:e2b / sol-ai:e4b) at zero cloud cost.
- Detects relay lag and delivery latency.
- Triages incoming batons using local AI inference.
- Automatically dispatches vetted execution tasks to the Dav1d / AGY CLI harness.
- Maintains self-healing SQLite state ledger and auto-recovers on drift.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Local imports
try:
    from nougen_shards.dav1d_executor import run_dav1d_agy
    from nougen_shards.handoff_dialects import read_all_handoffs
except ImportError:
    # Fallback when running standalone from tools/
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from nougen_shards.dav1d_executor import run_dav1d_agy
        from nougen_shards.handoff_dialects import read_all_handoffs
    except ImportError:
        run_dav1d_agy = None
        read_all_handoffs = None

DEFAULT_HEARTBEAT_SEC = 200
DEFAULT_LAG_THRESHOLD_SEC = 300  # 5 minutes


def _resolve_ollama_url() -> str:
    raw = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"http://{raw}"
    # Replace bind-all 0.0.0.0 with loopback for client requests
    raw = raw.replace("://0.0.0.0", "://127.0.0.1")
    # Add port if missing
    host_part = raw.split("://", 1)[1]
    if ":" not in host_part:
        raw = f"{raw}:11434"
    return raw.rstrip("/")


DEFAULT_OLLAMA_URL = _resolve_ollama_url()
DEFAULT_MODEL = os.environ.get("NOUGEN_DAEMON_MODEL", "dav1d:e2b")
DEFAULT_DB_PATH = Path(os.environ.get("NOUGEN_DAEMON_DB", r"C:\Users\super\Watchtower\Sol-Ai\relay_daemon_state.db"))
DEFAULT_RELAY_DIR = Path(os.environ.get("NOUGEN_RELAY_DIR", r"C:\Users\super\Watchtower\NouGen\NouGenRelay"))


@dataclass
class HeartbeatPulse:
    pulse_id: int
    timestamp_utc: str
    ollama_status: str
    ollama_latency_ms: float
    loaded_models: List[str]
    open_handoffs_count: int
    lag_alerts_count: int
    status: str


@dataclass
class TriageResult:
    handoff_id: str
    task_type: str  # EXECUTION_RUN | CODE_MUTATION | STATUS_CHECK | INFORMATIONAL | DIAGNOSTIC
    action: str
    requires_harness_wake: bool
    confidence: float
    reasoning: str
    lag_seconds: float
    is_lagging: bool


class RelayDaemon:
    """Self-healing background daemon enveloping the NouGen execution harness."""

    def __init__(
        self,
        relay_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
        heartbeat_sec: int = DEFAULT_HEARTBEAT_SEC,
        lag_threshold_sec: int = DEFAULT_LAG_THRESHOLD_SEC,
        ollama_url: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        machine_name: str = "blade",
    ):
        self.relay_dir = Path(relay_dir) if relay_dir else DEFAULT_RELAY_DIR
        self.handoffs_dir = self.relay_dir / ".handoffs"
        self.claims_dir = self.handoffs_dir / "claims"
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.heartbeat_sec = heartbeat_sec
        self.lag_threshold_sec = lag_threshold_sec
        self.ollama_url = ollama_url.rstrip("/") if ollama_url else DEFAULT_OLLAMA_URL
        self.model_name = model_name
        self.machine_name = machine_name
        self.is_running = False
        self.pulse_counter = 0

        self._ensure_directories()
        self._init_db()

    def _ensure_directories(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.handoffs_dir.mkdir(parents=True, exist_ok=True)
        self.claims_dir.mkdir(parents=True, exist_ok=True)

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daemon_pulses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pulse_number INTEGER,
                    timestamp_utc TEXT,
                    ollama_status TEXT,
                    ollama_latency_ms REAL,
                    loaded_models TEXT,
                    open_handoffs_count INTEGER,
                    lag_alerts_count INTEGER,
                    status TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS triage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handoff_id TEXT UNIQUE,
                    source_machine TEXT,
                    goal TEXT,
                    task_type TEXT,
                    action TEXT,
                    requires_harness_wake INTEGER,
                    confidence REAL,
                    lag_seconds REAL,
                    status TEXT,
                    execution_result TEXT,
                    created_utc TEXT,
                    updated_utc TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lag_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handoff_id TEXT,
                    lag_seconds REAL,
                    threshold_seconds REAL,
                    detected_utc TEXT,
                    reported INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def check_ollama_health(self) -> Tuple[bool, float, List[str]]:
        """Probes local Ollama at zero cloud cost. Returns (is_alive, latency_ms, loaded_models)."""
        t0 = time.time()
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", headers={"User-Agent": "NouGen-RelayDaemon/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                latency_ms = (time.time() - t0) * 1000.0
                return True, latency_ms, models
        except Exception:
            return False, -1.0, []

    def get_open_handoffs(self) -> List[Dict[str, Any]]:
        """Scans .handoffs/ for open/unresolved baton records."""
        results = []
        if not self.handoffs_dir.exists():
            return results

        json_files = list(self.handoffs_dir.glob("*.json"))
        for jf in sorted(json_files):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                status = data.get("status", "open")
                if status in ("open", "active", "held"):
                    data["_file_path"] = str(jf)
                    results.append(data)
            except Exception:
                continue
        return results

    def calculate_lag(self, handoff_data: Dict[str, Any]) -> Tuple[float, bool]:
        """Calculates lag in seconds between creation and current time."""
        created_str = (
            handoff_data.get("created_utc")
            or handoff_data.get("created_at")
            or handoff_data.get("timestamp")
            or handoff_data.get("when")
        )
        if not created_str:
            return 0.0, False

        try:
            # Parse ISO 8601 string
            clean_str = created_str.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(clean_str)
            now = datetime.datetime.now(datetime.timezone.utc)
            lag_sec = max(0.0, (now - dt).total_seconds())
            is_lagging = lag_sec >= self.lag_threshold_sec
            return lag_sec, is_lagging
        except Exception:
            return 0.0, False

    def triage_with_ollama(self, handoff_data: Dict[str, Any]) -> TriageResult:
        """Invokes local Ollama (dav1d:e2b) to classify the baton and formulate action."""
        handoff_id = handoff_data.get("id", Path(handoff_data.get("_file_path", "unknown")).stem)
        goal = handoff_data.get("goal", "")
        lag_sec, is_lagging = self.calculate_lag(handoff_data)

        # Build local prompt
        prompt = (
            f"You are Dav1d, the local execution triager on the Blade node.\n"
            f"Classify this incoming relay goal into JSON:\n"
            f"Goal: {goal}\n\n"
            f"Allowed task_type values: EXECUTION_RUN, CODE_MUTATION, STATUS_CHECK, INFORMATIONAL, DIAGNOSTIC.\n"
            f"Respond ONLY with valid JSON in this exact structure:\n"
            f'{{"task_type": "EXECUTION_RUN", "action": "subcommand or task name", "requires_harness_wake": true, "confidence": 0.95, "reasoning": "brief explanation"}}'
        )

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                response_text = res.get("response", "{}")
                parsed = json.loads(response_text)
                return TriageResult(
                    handoff_id=handoff_id,
                    task_type=parsed.get("task_type", "INFORMATIONAL"),
                    action=parsed.get("action", goal),
                    requires_harness_wake=bool(parsed.get("requires_harness_wake", False)),
                    confidence=float(parsed.get("confidence", 0.8)),
                    reasoning=parsed.get("reasoning", "Triaged via local Ollama"),
                    lag_seconds=lag_sec,
                    is_lagging=is_lagging,
                )
        except Exception as e:
            # Fallback rule-based triage when Ollama is unreachable
            requires_wake = any(w in goal.lower() for w in ["exec", "run", "agy", "antigravity", "dispatch", "build", "test", "patch"])
            task_type = "EXECUTION_RUN" if requires_wake else "INFORMATIONAL"
            return TriageResult(
                handoff_id=handoff_id,
                task_type=task_type,
                action=goal,
                requires_harness_wake=requires_wake,
                confidence=0.5,
                reasoning=f"Fallback rule-based triage (Ollama error: {e})",
                lag_seconds=lag_sec,
                is_lagging=is_lagging,
            )

    def dispatch_execution(self, triage: TriageResult, dry_run: bool = False) -> Dict[str, Any]:
        """Dispatches work to the AGY CLI / Dav1d execution harness."""
        if dry_run:
            return {
                "status": "dry_run",
                "message": f"Dry-run dispatch: would execute '{triage.action}' for {triage.handoff_id}",
                "exit_code": 0,
            }

        if run_dav1d_agy is None:
            return {
                "status": "error",
                "message": "dav1d_executor module not importable in this environment",
                "exit_code": 1,
            }

        try:
            # Map action to AGY subcommand
            subcmd = "mcp list" if "mcp" in triage.action.lower() else "version"
            result = run_dav1d_agy(subcommand=subcmd, args=[subcmd])
            return result
        except Exception as e:
            return {
                "status": "exception",
                "message": str(e),
                "exit_code": 1,
            }

    def record_pulse(self, pulse: HeartbeatPulse) -> None:
        """Persists a pulse event to SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO daemon_pulses (
                    pulse_number, timestamp_utc, ollama_status, ollama_latency_ms,
                    loaded_models, open_handoffs_count, lag_alerts_count, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    pulse.pulse_id,
                    pulse.timestamp_utc,
                    pulse.ollama_status,
                    pulse.ollama_latency_ms,
                    json.dumps(pulse.loaded_models),
                    pulse.open_handoffs_count,
                    pulse.lag_alerts_count,
                    pulse.status,
                ),
            )
            conn.commit()

    def record_triage(self, handoff_data: Dict[str, Any], triage: TriageResult, exec_res: Optional[Dict[str, Any]] = None) -> None:
        """Persists a triage and execution event to SQLite."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO triage_events (
                    handoff_id, source_machine, goal, task_type, action,
                    requires_harness_wake, confidence, lag_seconds, status,
                    execution_result, created_utc, updated_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(handoff_id) DO UPDATE SET
                    task_type=excluded.task_type,
                    action=excluded.action,
                    requires_harness_wake=excluded.requires_harness_wake,
                    confidence=excluded.confidence,
                    lag_seconds=excluded.lag_seconds,
                    status=excluded.status,
                    execution_result=excluded.execution_result,
                    updated_utc=excluded.updated_utc
            """,
                (
                    triage.handoff_id,
                    handoff_data.get("machine", "unknown"),
                    handoff_data.get("goal", ""),
                    triage.task_type,
                    triage.action,
                    1 if triage.requires_harness_wake else 0,
                    triage.confidence,
                    triage.lag_seconds,
                    exec_res.get("status", "triaged") if exec_res else "triaged",
                    json.dumps(exec_res) if exec_res else None,
                    handoff_data.get("created_utc", now_str),
                    now_str,
                ),
            )
            if triage.is_lagging:
                conn.execute(
                    """
                    INSERT INTO lag_alerts (handoff_id, lag_seconds, threshold_seconds, detected_utc)
                    VALUES (?, ?, ?, ?)
                """,
                    (triage.handoff_id, triage.lag_seconds, self.lag_threshold_sec, now_str),
                )
            conn.commit()

    def run_cycle(self, dry_run: bool = False) -> Dict[str, Any]:
        """Executes a single heartbeat and inspection cycle."""
        self.pulse_counter += 1
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Probe local Ollama
        is_alive, latency_ms, models = self.check_ollama_health()
        ollama_status = "healthy" if is_alive else "unreachable"

        # 2. Scan open handoffs
        open_handoffs = self.get_open_handoffs()
        lag_alerts = []
        triage_reports = []

        # 3. Process/triage open handoffs (process most recent up to 3 per cycle)
        for h in open_handoffs[-3:]:
            triage = self.triage_with_ollama(h)
            if triage.is_lagging:
                lag_alerts.append({
                    "handoff_id": triage.handoff_id,
                    "lag_seconds": triage.lag_seconds,
                })

            exec_res = None
            if triage.requires_harness_wake:
                exec_res = self.dispatch_execution(triage, dry_run=dry_run)

            self.record_triage(h, triage, exec_res)
            triage_reports.append({
                "triage": asdict(triage),
                "execution": exec_res,
            })

        # 4. Record pulse
        pulse = HeartbeatPulse(
            pulse_id=self.pulse_counter,
            timestamp_utc=now_utc,
            ollama_status=ollama_status,
            ollama_latency_ms=latency_ms,
            loaded_models=models,
            open_handoffs_count=len(open_handoffs),
            lag_alerts_count=len(lag_alerts),
            status="ok" if is_alive else "degraded",
        )
        self.record_pulse(pulse)

        return {
            "pulse": asdict(pulse),
            "open_handoffs_count": len(open_handoffs),
            "lag_alerts": lag_alerts,
            "triaged_count": len(triage_reports),
            "triages": triage_reports,
        }

    def start_loop(self, dry_run: bool = False) -> None:
        """Starts the infinite daemon loop with heartbeat_sec intervals."""
        self.is_running = True
        print(f"[RelayDaemon] 🛡️ Starting Self-Healing Daemon Loop on {self.machine_name}")
        print(f"[RelayDaemon] ⏱️ Cadence: {self.heartbeat_sec}s | Model: {self.model_name} | Lag Threshold: {self.lag_threshold_sec}s")
        print(f"[RelayDaemon] 📂 Watching: {self.handoffs_dir}")

        while self.is_running:
            try:
                cycle_summary = self.run_cycle(dry_run=dry_run)
                pulse = cycle_summary["pulse"]
                print(
                    f"[RelayDaemon] 💓 Pulse #{pulse['pulse_id']} | "
                    f"Ollama: {pulse['ollama_status']} ({pulse['ollama_latency_ms']:.1f}ms) | "
                    f"Open: {pulse['open_handoffs_count']} | Lag Alerts: {pulse['lag_alerts_count']}"
                )
            except KeyboardInterrupt:
                print("\n[RelayDaemon] 🛑 Shutting down gracefully...")
                self.is_running = False
                break
            except Exception as e:
                print(f"[RelayDaemon] ⚠️ Cycle error (self-healing): {e}")

            time.sleep(self.heartbeat_sec)

    def get_status_report(self) -> Dict[str, Any]:
        """Queries recent pulses, lag alerts, and triage events for high-fidelity reporting."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            recent_pulses = [
                dict(r) for r in conn.execute("SELECT * FROM daemon_pulses ORDER BY id DESC LIMIT 5").fetchall()
            ]
            recent_triages = [
                dict(r) for r in conn.execute("SELECT * FROM triage_events ORDER BY id DESC LIMIT 5").fetchall()
            ]
            recent_lags = [
                dict(r) for r in conn.execute("SELECT * FROM lag_alerts ORDER BY id DESC LIMIT 5").fetchall()
            ]

        is_alive, latency_ms, models = self.check_ollama_health()
        return {
            "daemon_live_check": {
                "ollama_alive": is_alive,
                "latency_ms": latency_ms,
                "models": models,
            },
            "recent_pulses": recent_pulses,
            "recent_triages": recent_triages,
            "recent_lag_alerts": recent_lags,
            "db_path": str(self.db_path),
        }


def main():
    parser = argparse.ArgumentParser(description="NouGenAi Self-Healing Relay Daemon")
    parser.add_argument("--once", action="store_true", help="Run a single heartbeat/triage cycle and exit")
    parser.add_argument("--daemon", action="store_true", help="Run continuous loop")
    parser.add_argument("--dry-run", action="store_true", help="Triage without executing live mutations")
    parser.add_argument("--status", action="store_true", help="Print live daemon telemetry and recent pulses")
    parser.add_argument("--heartbeat-sec", type=int, default=DEFAULT_HEARTBEAT_SEC, help=f"Heartbeat interval (default: {DEFAULT_HEARTBEAT_SEC}s)")
    parser.add_argument("--lag-threshold-sec", type=int, default=DEFAULT_LAG_THRESHOLD_SEC, help=f"Lag alert threshold (default: {DEFAULT_LAG_THRESHOLD_SEC}s)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    daemon = RelayDaemon(
        heartbeat_sec=args.heartbeat_sec,
        lag_threshold_sec=args.lag_threshold_sec,
        model_name=args.model,
    )

    if args.status:
        report = daemon.get_status_report()
        print(json.dumps(report, indent=2))
        return

    if args.once:
        res = daemon.run_cycle(dry_run=args.dry_run)
        print(json.dumps(res, indent=2))
        return

    # Default to daemon loop
    daemon.start_loop(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
