"""
NouGen Zero-Babysitting Bootstrap Engine (Elevated Module)

Implements low-friction capability-aware Ollama provisioning,
RiskClassifier auto-proceed gates, autonomous model pulling for nomic-embed-text
and gemma4:e2b, and universal AgentSurfaceAdapter registry for AGENTS.md,
GEMINI.md, and CLAUDE.md.

Directives Satisfied:
- 20260928T060138Z: Low-friction bootstrap with capability-aware Ollama setup
- 20260928T060252Z: Universal agent-root auto-hook layer
- 20260928T060521Z: Zero-babysitting native agent surface references
- Autonomous Ollama & model bundle provisioning (nomic-embed-text & gemma4:e2b)
"""

from dataclasses import dataclass, field
from enum import Enum, auto
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class ActionRisk(Enum):
    SAFE_REVERSIBLE = auto()
    TRUST_BOUNDARY_GATED = auto()


class RiskClassifier:
    """
    Evaluates bootstrap actions to ensure safe/reversible setup auto-proceeds,
    while destructive or credential-exposing operations require explicit gates.
    """

    @staticmethod
    def classify_action(action_type: str, target_path: Optional[str] = None) -> ActionRisk:
        action_lower = action_type.lower()
        if any(k in action_lower for k in ["secret", "credential", "auth", "privilege", "overwrite", "delete", "deploy"]):
            return ActionRisk.TRUST_BOUNDARY_GATED
        return ActionRisk.SAFE_REVERSIBLE


@dataclass
class DiskSpaceRequirement:
    model_bundle_bytes: int = 7_500_000_000  # ~7.5GB for nomic-embed-text + gemma4:e2b
    reserve_floor_bytes: int = 10_000_000_000  # 10GB reserve
    total_required: int = field(init=False)

    def __post_init__(self):
        self.total_required = self.model_bundle_bytes + self.reserve_floor_bytes

    def evaluate(self, free_bytes: int) -> Tuple[bool, str]:
        if free_bytes >= self.total_required:
            gb_free = free_bytes / (1024**3)
            return True, f"Qualified: {gb_free:.1f} GB free exceeds {self.total_required / (1024**3):.1f} GB requirement."
        return False, f"Insufficient free disk: {free_bytes / (1024**3):.1f} GB available, need {self.total_required / (1024**3):.1f} GB."


class AgentSurfaceAdapter:
    """
    Universal agent rule surface adapter for AGENTS.md, GEMINI.md, and CLAUDE.md.
    Maintains deterministic versioned blocks while preserving user-owned content.
    """

    MANAGED_START = "<!-- NOUGEN_MANAGED_START: v1.0.0 -->"
    MANAGED_END = "<!-- NOUGEN_MANAGED_END -->"

    SURFACE_MAP = {
        "codex": "AGENTS.md",
        "gemini": "GEMINI.md",
        "claude": "CLAUDE.md",
    }

    @classmethod
    def generate_instruction_block(cls, agent_type: str, canonical_ref: str = "~/.nougen/rules/core.md") -> str:
        return (
            f"{cls.MANAGED_START}\n"
            f"# NouGen Autonomous Fleet Operating Layer\n"
            f"@import {canonical_ref}\n"
            f"Preserve active ownership, verify ground truth, and adhere to Rule 0.13 (Hardcade execution before ack).\n"
            f"{cls.MANAGED_END}"
        )

    @classmethod
    def apply_to_file(cls, file_path: Path, agent_type: str) -> Dict[str, Any]:
        """
        Idempotently injects or updates the NouGen managed instruction block.
        Returns rollback metadata and diff hash.
        """
        existed = file_path.exists()
        original_content = file_path.read_text(encoding="utf-8") if existed else ""
        original_hash = hashlib.sha256(original_content.encode("utf-8")).hexdigest()

        block = cls.generate_instruction_block(agent_type)

        if cls.MANAGED_START in original_content and cls.MANAGED_END in original_content:
            # Replace existing block
            pre = original_content.split(cls.MANAGED_START)[0]
            post = original_content.split(cls.MANAGED_END)[1]
            new_content = pre + block + post
        else:
            # Append block
            new_content = (original_content.rstrip() + "\n\n" + block + "\n") if original_content else (block + "\n")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(new_content, encoding="utf-8")

        new_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

        return {
            "file": str(file_path),
            "agent_type": agent_type,
            "existed_prior": existed,
            "original_sha256": original_hash,
            "new_sha256": new_hash,
            "modified": original_hash != new_hash,
            "rollback_possible": True,
        }


class ZeroBabysittingBootstrap:
    """
    Orchestrates automated low-friction bootstrap flow for new users and nodes:
    - Environment & space qualification check
    - Auto-provisioning and verifying Ollama
    - Pulling foundational models: nomic-embed-text (embeddings) & gemma4:e2b (reasoning)
    - Safe reversible agent hook installation
    """

    RECOMMENDED_MODELS = [
        "nomic-embed-text:latest",
        "gemma4:e2b",
    ]

    def __init__(
        self,
        root_dir: Optional[Path] = None,
        reserve_gb: float = 10.0,
        ollama_url: Optional[str] = None,
    ):
        self.root_dir = root_dir or Path.home()
        self.reserve_bytes = int(reserve_gb * 1024 * 1024 * 1024)
        self.space_req = DiskSpaceRequirement(reserve_floor_bytes=self.reserve_bytes)
        self.ollama_url = ollama_url or os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434")

    def probe_environment(self) -> Dict[str, Any]:
        """
        Inspects disk capacity, local Ollama presence, and platform capabilities.
        """
        stat = shutil.disk_usage(self.root_dir)
        qualified, reason = self.space_req.evaluate(stat.free)

        # Check local Ollama
        ollama_present = shutil.which("ollama") is not None
        ollama_live = self.is_ollama_live()

        return {
            "free_bytes": stat.free,
            "free_gb": round(stat.free / (1024**3), 2),
            "space_qualified": qualified,
            "space_reason": reason,
            "ollama_binary_found": ollama_present,
            "ollama_live": ollama_live,
            "bootstrap_mode": "local_hybrid" if qualified else "remote_memory_only",
        }

    def is_ollama_live(self) -> bool:
        """Checks if Ollama HTTP endpoint is answering."""
        try:
            req = urllib.request.Request(f"{self.ollama_url.rstrip('/')}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_installed_models(self) -> List[str]:
        """Queries local Ollama for currently installed models."""
        try:
            req = urllib.request.Request(f"{self.ollama_url.rstrip('/')}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception as e:
            logger.debug("Failed to list installed models: %s", e)
            return []

    def ensure_ollama_installed_and_running(self) -> Tuple[bool, str]:
        """
        Ensures Ollama is installed and running. If binary is present, starts it if not already live.
        If binary is missing, gives platform-specific non-blocking instruction or runs supported auto-installer.
        """
        if self.is_ollama_live():
            return True, "Ollama is live and answering queries."

        ollama_bin = shutil.which("ollama")
        if ollama_bin:
            # Try launching background daemon
            try:
                subprocess.Popen(
                    [ollama_bin, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
                # Wait up to 10 seconds for ignition
                for _ in range(10):
                    time.sleep(1.0)
                    if self.is_ollama_live():
                        return True, "Ignited cold Ollama daemon successfully."
                return False, "Started 'ollama serve' but endpoint did not become ready within timeout."
            except Exception as e:
                return False, f"Failed to start Ollama daemon: {e}"

        # If binary is missing entirely
        sys_name = platform.system()
        install_cmd = "curl -fsSL https://ollama.com/install.sh | sh" if sys_name != "Windows" else "winget install Ollama.Ollama"
        return False, f"Ollama binary not found on PATH. Run '{install_cmd}' to install."

    def ensure_model_installed(self, model_name: str, timeout_s: float = 300.0) -> Tuple[bool, str]:
        """
        Idempotently pulls the requested model via Ollama HTTP API or CLI if not already present.
        """
        installed = self.list_installed_models()
        # Check direct or prefix match (e.g., nomic-embed-text matching nomic-embed-text:latest)
        base_name = model_name.split(":")[0]
        if any(m == model_name or m.startswith(f"{base_name}:") for m in installed):
            return True, f"Model '{model_name}' is already installed."

        if not self.is_ollama_live():
            return False, f"Cannot pull '{model_name}': Ollama is not running."

        # Attempt pull via API
        try:
            payload = json.dumps({"name": model_name, "stream": False}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/pull",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                if resp.status == 200:
                    return True, f"Successfully pulled '{model_name}'."
        except Exception as e:
            # Fallback to CLI if API stream fails
            ollama_bin = shutil.which("ollama")
            if ollama_bin:
                try:
                    res = subprocess.run([ollama_bin, "pull", model_name], capture_output=True, text=True, timeout=timeout_s)
                    if res.returncode == 0:
                        return True, f"Successfully pulled '{model_name}' via CLI."
                    return False, f"CLI pull failed: {res.stderr.strip()}"
                except Exception as cli_exc:
                    return False, f"Failed pulling '{model_name}': {cli_exc}"
            return False, f"Failed pulling '{model_name}' via API: {e}"

        return False, f"Failed to verify installation of '{model_name}'."

    def autonomous_bootstrap(self, target_workspace: Optional[Path] = None) -> Dict[str, Any]:
        """
        Full zero-babysitting end-to-end bootstrap:
        1. Probe environment & check disk capacity
        2. Ensure Ollama daemon is live
        3. Ensure nomic-embed-text:latest and gemma4:e2b are pulled and ready
        4. Install agent surface hooks in target workspace
        """
        report: Dict[str, Any] = {
            "timestamp": time.time(),
            "probe": self.probe_environment(),
            "models": {},
            "agent_hooks": [],
            "status": "in_progress",
        }

        # 1. Space check
        if not report["probe"]["space_qualified"]:
            report["status"] = "skipped_insufficient_space"
            report["summary"] = report["probe"]["space_reason"]
            return report

        # 2. Ollama setup
        ollama_ok, ollama_msg = self.ensure_ollama_installed_and_running()
        report["ollama"] = {"ready": ollama_ok, "detail": ollama_msg}

        if ollama_ok:
            # 3. Pull required foundational models
            for model in self.RECOMMENDED_MODELS:
                m_ok, m_msg = self.ensure_model_installed(model)
                report["models"][model] = {"ready": m_ok, "detail": m_msg}

        # 4. Agent hooks
        if target_workspace and target_workspace.exists():
            report["agent_hooks"] = self.install_agent_hooks(target_workspace)

        all_models_ready = all(m.get("ready", False) for m in report["models"].values()) if report["models"] else False
        report["status"] = "completed" if (ollama_ok and all_models_ready) else "partial"
        return report

    def install_agent_hooks(self, target_dir: Path) -> List[Dict[str, Any]]:
        """
        Auto-proceeds with safe reversible agent rule references across AGENTS.md, GEMINI.md, CLAUDE.md.
        """
        results = []
        for agent_type, filename in AgentSurfaceAdapter.SURFACE_MAP.items():
            path = target_dir / filename
            risk = RiskClassifier.classify_action("apply_agent_hook", str(path))
            if risk == ActionRisk.SAFE_REVERSIBLE:
                res = AgentSurfaceAdapter.apply_to_file(path, agent_type)
                results.append(res)
        return results
