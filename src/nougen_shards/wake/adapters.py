"""
Provider-Agnostic Wake Adapters for NouGenAi Ecosystem.
Normalizes detection, injection, idle-wake, session resume, and capability matrix
across Claude Code, Antigravity, OpenAI Codex, and Ollama.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProviderAdapter(ABC):
    """Abstract base contract for all provider wake adapters."""

    name: str = "generic"

    @abstractmethod
    def detect(self) -> bool:
        """Return True if this runtime / provider is installed and present on this node."""
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """Return normalized capability dictionary."""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return live health, transport status, and endpoint diagnostics."""
        raise NotImplementedError

    @abstractmethod
    def inject(self, message: str, domain: str = "default") -> Dict[str, Any]:
        """Inject message into active agent context / inbox (in-turn delivery)."""
        raise NotImplementedError

    @abstractmethod
    def wake(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Awaken an idle session to process an incoming event / brief."""
        raise NotImplementedError

    def resume(self, session_hint: str) -> Dict[str, Any]:
        """Resume a previous session if supported."""
        return {"supported": False, "status": "not_implemented"}

    def receipt(self, event_id: str) -> Dict[str, Any]:
        """Check receiver-side proof / acknowledgment for an event."""
        return {"event_id": event_id, "verified": False, "proof": "unsupported"}

    def explain_unavailable(self) -> str:
        """Return actionable explanation when runtime is unavailable."""
        return f"Runtime '{self.name}' is not installed or not discoverable on PATH."


class ClaudeAdapter(ProviderAdapter):
    """Adapter for Claude Code CLI and named pipe socket protocol."""

    name = "claude"

    def detect(self) -> bool:
        return bool(shutil.which("claude") or shutil.which("claude.cmd"))

    def capabilities(self) -> Dict[str, Any]:
        return {
            "can_inject_active": True,
            "can_wake_idle": True,
            "can_resume_session": True,
            "transport": "named_pipe_and_inbox",
            "requires_user_presence": False,
            "auto_claim": True,
        }

    def health(self) -> Dict[str, Any]:
        from ..nougenmsg import AgentPinger
        pipes = AgentPinger._discover_claude_endpoints()
        reg_path = Path(AgentPinger._cc_registry_path())
        reg_count = 0
        if reg_path.is_file():
            try:
                reg_count = len(json.loads(reg_path.read_text(encoding="utf-8")).get("sessions", {}))
            except Exception:
                pass
        return {
            "detected": self.detect(),
            "active_pipes": len(pipes),
            "registered_sessions": reg_count,
            "inbox_dir": str(AgentPinger._claude_inbox_dir()),
            "status": "healthy" if (pipes or reg_count > 0 or self.detect()) else "inactive",
        }

    def inject(self, message: str, domain: str = "default") -> Dict[str, Any]:
        from ..nougenmsg import AgentPinger
        return AgentPinger.ping_claude(message)

    def wake(self, event: Dict[str, Any]) -> Dict[str, Any]:
        text = event.get("text") or event.get("brief") or event.get("goal") or "Wake brief"
        res = self.inject(text)
        return {
            "runtime": self.name,
            "woken": bool(res.get("delivered")),
            "delivery": res,
            "timestamp": time.time(),
        }


class AntigravityAdapter(ProviderAdapter):
    """Adapter for Antigravity (AGY) CLI and lifecycle hook system."""

    name = "antigravity"

    def _bin_path(self) -> Optional[str]:
        explicit = os.environ.get("NOUGEN_AGY_BIN")
        if explicit and os.path.isfile(explicit):
            return explicit
        return (
            shutil.which("agy")
            or shutil.which("agy.exe")
            or shutil.which("agy.cmd")
            or (os.path.expanduser(r"~\AppData\Local\agy\bin\agy.EXE") if os.path.isfile(os.path.expanduser(r"~\AppData\Local\agy\bin\agy.EXE")) else None)
        )

    def detect(self) -> bool:
        return bool(self._bin_path())

    def capabilities(self) -> Dict[str, Any]:
        return {
            "can_inject_active": True,
            "can_wake_idle": True,
            "can_resume_session": True,
            "transport": "pre_invocation_hook_and_agy_msg",
            "requires_user_presence": False,
            "auto_claim": True,
        }

    def is_idle(self) -> bool:
        """Observable state check: returns True if no agy.exe process is actively running a turn."""
        if not self.detect():
            return False
        if sys.platform == "win32":
            try:
                out = subprocess.check_output('tasklist /FI "IMAGENAME eq agy.exe" /FO CSV /NH', shell=True, text=True)
                # If agy.exe appears in tasklist, count instances
                lines = [line for line in out.strip().splitlines() if "agy.exe" in line.lower()]
                # If only 0 or 1 instance (the server itself vs active worker), determine state
                return len(lines) <= 1
            except Exception:
                return True
        return True

    def health(self) -> Dict[str, Any]:
        from ..agy_msg import get_inbox_dir
        bin_path = self._bin_path()
        hook_path = Path.home() / ".gemini" / "config" / "hooks.json"
        hook_active = False
        if hook_path.is_file():
            try:
                hook_data = json.loads(hook_path.read_text(encoding="utf-8"))
                hook_active = bool(hook_data.get("hooks", {}).get("PreInvocation") or hook_data.get("nougen-agy-inbox", {}).get("PreInvocation"))
            except Exception:
                pass

        idle_state = "IDLE" if self.is_idle() else "ACTIVE_IN_TURN"
        if not bin_path:
            idle_state = "NOT_INSTALLED"

        return {
            "detected": bool(bin_path),
            "binary_path": bin_path,
            "observable_state": idle_state,
            "is_idle": self.is_idle(),
            "pre_invocation_hook_registered": hook_active,
            "inbox_dir": str(get_inbox_dir()),
            "status": "healthy" if (bin_path and hook_active) else ("warning" if bin_path else "missing"),
        }

    def inject(self, message: str, domain: str = "default") -> Dict[str, Any]:
        from ..nougenmsg import AgentPinger
        return AgentPinger.ping_antigravity(message, domain=domain)

    def wake(self, event: Dict[str, Any]) -> Dict[str, Any]:
        bin_path = self._bin_path()
        if not bin_path:
            return {"status": "error", "classification": "TRANSPORT_ERROR", "message": self.explain_unavailable()}

        leg_id = event.get("leg_id") or event.get("id")
        goal = event.get("goal") or "Autonomous Wake Directive"
        brief = event.get("text") or event.get("brief") or goal

        full_prompt = (
            f"=== NOUGEN AUTONOMOUS RELAY WAKE ===\n"
            f"INBOUND_LEG_ID: {leg_id or 'none'}\n"
            f"GOAL: {goal}\n\n"
            f"BRIEF / CONTEXT:\n{brief}\n\n"
            f"INSTRUCTIONS: Execute autonomously, verify evidence, quote INBOUND_LEG_ID in handoff receipt, and publish to main."
        )

        # Idempotency check via ledger
        idempotency_file = Path.home() / ".nougen" / ".agy_woken_legs.json"
        if leg_id and idempotency_file.is_file():
            try:
                ledger = json.loads(idempotency_file.read_text(encoding="utf-8"))
                if ledger.get(leg_id, {}).get("status") in ["woken", "completed", "success"]:
                    return {
                        "runtime": self.name,
                        "status": "skipped",
                        "classification": "IDEMPOTENT_SKIP",
                        "message": f"Leg '{leg_id}' already processed.",
                        "leg_id": leg_id,
                    }
            except Exception:
                pass

        workspace_cwd = Path(os.environ["NOUGEN_SHARDS_ROOT"]) if os.environ.get("NOUGEN_SHARDS_ROOT") else Path.home() / "Watchtower" / "NouGen" / "NouGenShards-push-main"
        if not workspace_cwd.is_dir():
            workspace_cwd = Path.cwd()

        proc_env = dict(os.environ)
        proc_env["PYTHONPATH"] = str(workspace_cwd / "src")
        proc_env["NOUGEN_AGENT"] = "agy-cli"

        flags = [f for f in os.environ.get("NOUGEN_AGY_FLAGS", "--dangerously-skip-permissions").split() if f]
        cmd = [bin_path, *flags, "-p", full_prompt]
        timeout_s = int(os.environ.get("NOUGEN_AGY_TIMEOUT_SEC", "300"))

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace_cwd),
                env=proc_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=timeout_s,
            )
            success = (proc.returncode == 0)
            status = "success" if success else "error"
            classification = "SUCCESS" if success else "EXECUTION_ERROR"

            # Record in idempotency ledger
            if leg_id:
                try:
                    idempotency_file.parent.mkdir(parents=True, exist_ok=True)
                    data = {}
                    if idempotency_file.is_file():
                        try:
                            data = json.loads(idempotency_file.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    data[leg_id] = {"status": status, "timestamp": time.time(), "exit_code": proc.returncode}
                    idempotency_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception:
                    pass

            return {
                "runtime": self.name,
                "status": status,
                "classification": classification,
                "exit_code": proc.returncode,
                "leg_id": leg_id,
                "stdout": (proc.stdout.strip() if proc.stdout else "")[-2000:],
                "stderr": (proc.stderr.strip() if proc.stderr else "")[-500:],
                "timestamp": time.time(),
            }
        except subprocess.TimeoutExpired:
            return {"runtime": self.name, "status": "timeout", "classification": "TIMEOUT", "leg_id": leg_id, "timestamp": time.time()}
        except Exception as exc:
            return {"runtime": self.name, "status": "exception", "classification": "EXCEPTION", "error": str(exc), "leg_id": leg_id, "timestamp": time.time()}


class CodexAdapter(ProviderAdapter):
    """Adapter for OpenAI Codex agent runtime."""

    name = "codex"

    def _binary(self) -> Optional[str]:
        configured = os.environ.get("NOUGEN_CODEX_BIN")
        if configured and Path(configured).is_file():
            return configured
        return shutil.which("codex") or shutil.which("codex.cmd")

    def detect(self) -> bool:
        return self._binary() is not None

    def capabilities(self) -> Dict[str, Any]:
        return {
            "can_inject_active": True,
            "can_wake_idle": self._binary() is not None,
            "can_resume_session": self._binary() is not None,
            "transport": "codex_exec_resume_private_stdio",
            "requires_user_presence": self._binary() is None,
            "auto_claim": False,
        }

    def health(self) -> Dict[str, Any]:
        inbox = Path.home() / ".codex" / "inbox"
        return {
            "detected": self.detect(),
            "inbox_exists": inbox.is_dir(),
            "inbox_path": str(inbox),
            "status": "healthy" if self.detect() else "inactive",
        }

    def inject(self, message: str, domain: str = "default") -> Dict[str, Any]:
        from ..nougenmsg import AgentPinger
        return AgentPinger.ping_codex(message)

    def wake(self, event: Dict[str, Any]) -> Dict[str, Any]:
        from .codex_bridge import CodexWakeBridge
        return CodexWakeBridge().wake(event)

    def receipt(self, event_id: str) -> Dict[str, Any]:
        from .codex_bridge import CodexWakeBridge
        return CodexWakeBridge().receipt(event_id)


class OllamaAdapter(ProviderAdapter):
    """Adapter for local Ollama tactical execution."""

    name = "ollama"

    def detect(self) -> bool:
        return bool(shutil.which("ollama"))

    def capabilities(self) -> Dict[str, Any]:
        return {
            "can_inject_active": True,
            "can_wake_idle": True,
            "can_resume_session": False,
            "transport": "http_rest_api",
            "requires_user_presence": False,
            "auto_claim": True,
        }

    def health(self) -> Dict[str, Any]:
        import urllib.request
        url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        if not url.startswith("http"):
            url = f"http://{url}"
        try:
            with urllib.request.urlopen(f"{url}/api/tags", timeout=2) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name") for m in data.get("models", [])]
                return {"detected": True, "online": True, "url": url, "models": models, "status": "healthy"}
        except Exception as exc:
            return {"detected": self.detect(), "online": False, "url": url, "error": str(exc), "status": "offline"}

    def inject(self, message: str, domain: str = "default") -> Dict[str, Any]:
        from ..nougenmsg import AgentPinger
        return AgentPinger.ping_ollama(message)

    def wake(self, event: Dict[str, Any]) -> Dict[str, Any]:
        prompt = event.get("text") or event.get("brief") or event.get("goal") or "Evaluate relay event"
        res = self.inject(prompt)
        return {"runtime": self.name, "status": "success" if "error" not in res else "error", "response": res}


ADAPTERS: Dict[str, ProviderAdapter] = {
    "claude": ClaudeAdapter(),
    "antigravity": AntigravityAdapter(),
    "codex": CodexAdapter(),
    "ollama": OllamaAdapter(),
}


def get_adapter(name: str) -> Optional[ProviderAdapter]:
    return ADAPTERS.get(name.lower().strip())


def list_adapters() -> Dict[str, ProviderAdapter]:
    return ADAPTERS.copy()
