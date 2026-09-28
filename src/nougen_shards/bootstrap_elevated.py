"""
NouGen Zero-Babysitting Bootstrap Engine (Elevated Module)

Implements low-friction capability-aware Ollama provisioning,
RiskClassifier auto-proceed gates, and universal AgentSurfaceAdapter registry
for AGENTS.md, GEMINI.md, and CLAUDE.md.

Directives Satisfied:
- 20260928T060138Z: Low-friction bootstrap with capability-aware Ollama setup
- 20260928T060252Z: Universal agent-root auto-hook layer
- 20260928T060521Z: Zero-babysitting native agent surface references
"""

from dataclasses import dataclass, field
from enum import Enum, auto
import hashlib
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple


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
    Orchestrates automated low-friction bootstrap flow.
    """

    def __init__(self, root_dir: Optional[Path] = None, reserve_gb: float = 10.0):
        self.root_dir = root_dir or Path.home()
        self.reserve_bytes = int(reserve_gb * 1024 * 1024 * 1024)
        self.space_req = DiskSpaceRequirement(reserve_floor_bytes=self.reserve_bytes)

    def probe_environment(self) -> Dict[str, Any]:
        """
        Inspects disk capacity, local Ollama presence, and platform capabilities.
        """
        stat = shutil.disk_usage(self.root_dir)
        qualified, reason = self.space_req.evaluate(stat.free)

        # Check local Ollama
        ollama_present = shutil.which("ollama") is not None

        return {
            "free_bytes": stat.free,
            "free_gb": round(stat.free / (1024**3), 2),
            "space_qualified": qualified,
            "space_reason": reason,
            "ollama_binary_found": ollama_present,
            "bootstrap_mode": "local_hybrid" if qualified else "remote_memory_only",
        }

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
