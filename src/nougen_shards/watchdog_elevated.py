"""
NouGen Autonomous Watchdog: Process Supervision and Self-Healing Engine.

Ensures critical fleet background services (NouGen MsgNode port 8766 and Ollama port 11434)
remain healthy, automatically diagnosing and resurrecting them upon crash or unresponsive socket.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import time
from typing import Any, Dict, Optional
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class ServiceProbeResult:
    def __init__(self, name: str, port: int, alive: bool, response_time_ms: float, error: Optional[str] = None):
        self.name = name
        self.port = port
        self.alive = alive
        self.response_time_ms = response_time_ms
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "port": self.port,
            "alive": self.alive,
            "response_time_ms": round(self.response_time_ms, 2),
            "error": self.error,
        }


class AutonomousWatchdog:
    """
    Supervises local grid processes, handles liveness probes,
    and performs self-healing restarts without human intervention.
    """

    def __init__(
        self,
        msgnode_url: str = "http://127.0.0.1:8766/status",
        ollama_url: str = "http://127.0.0.1:11434/api/tags",
        probe_timeout_s: float = 3.0,
    ):
        self.msgnode_url = msgnode_url
        self.ollama_url = ollama_url
        self.probe_timeout_s = probe_timeout_s

    @staticmethod
    def is_port_listening(host: str, port: int, timeout_s: float = 1.0) -> bool:
        """Verifies TCP socket connectivity."""
        try:
            with socket.create_connection((host, port), timeout=timeout_s):
                return True
        except (socket.timeout, OSError):
            return False

    def probe_http_service(self, name: str, url: str, port: int) -> ServiceProbeResult:
        """Performs HTTP health check on the specified service endpoint."""
        start = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NouGen-Watchdog/1.0"})
            with urllib.request.urlopen(req, timeout=self.probe_timeout_s) as resp:
                elapsed = (time.time() - start) * 1000
                if 200 <= resp.status < 300:
                    return ServiceProbeResult(name=name, port=port, alive=True, response_time_ms=elapsed)
                return ServiceProbeResult(
                    name=name, port=port, alive=False, response_time_ms=elapsed, error=f"HTTP {resp.status}"
                )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return ServiceProbeResult(name=name, port=port, alive=False, response_time_ms=elapsed, error=str(e))

    def probe_all(self) -> Dict[str, ServiceProbeResult]:
        """Probes all core fleet runtime dependencies."""
        return {
            "msgnode": self.probe_http_service("msgnode", self.msgnode_url, 8766),
            "ollama": self.probe_http_service("ollama", self.ollama_url, 11434),
        }

    def heal_ollama(self) -> Dict[str, Any]:
        """Restarts or ignites Ollama daemon."""
        logger.warning("Healing: attempting to start cold Ollama daemon...")
        try:
            if platform.system() == "Darwin":
                # Check if Ollama app exists
                app_path = "/Applications/Ollama.app"
                if os.path.exists(app_path):
                    subprocess.Popen(["open", "-a", "Ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return {"action": "open_app", "target": "Ollama.app", "success": True}

            # CLI fallback
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"action": "spawn_cli", "target": "ollama serve", "success": True}
        except Exception as e:
            logger.error("Failed to heal Ollama: %s", e)
            return {"action": "spawn_cli", "target": "ollama", "success": False, "error": str(e)}

    def heal_msgnode(self, launch_script: Optional[str] = None) -> Dict[str, Any]:
        """Restarts msgnode service via launchctl or fallback script."""
        logger.warning("Healing: attempting to restart msgnode...")
        try:
            if platform.system() == "Darwin":
                # Trigger launchctl restart if registered
                res = subprocess.run(
                    ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.nougen.msgnode"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if res.returncode == 0:
                    return {"action": "launchctl_kickstart", "target": "com.nougen.msgnode", "success": True}

            if launch_script and os.path.exists(launch_script):
                subprocess.Popen(["bash", launch_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {"action": "run_script", "target": launch_script, "success": True}

            return {"action": "unresolved", "success": False, "reason": "No launch script or launchctl target"}
        except Exception as e:
            return {"action": "heal_failed", "success": False, "error": str(e)}

    def run_supervision_cycle(self, auto_heal: bool = True) -> Dict[str, Any]:
        """
        Executes one full observation and healing cycle across fleet processes.
        """
        probes = self.probe_all()
        actions: Dict[str, Any] = {}
        all_healthy = True

        for service, result in probes.items():
            if not result.alive:
                all_healthy = False
                if auto_heal:
                    if service == "ollama":
                        actions["ollama"] = self.heal_ollama()
                    elif service == "msgnode":
                        actions["msgnode"] = self.heal_msgnode()

        return {
            "timestamp": time.time(),
            "healthy": all_healthy,
            "probes": {k: v.to_dict() for k, v in probes.items()},
            "healed_actions": actions,
        }
