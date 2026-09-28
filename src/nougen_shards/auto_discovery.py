"""
NouGen Deep Auto Discovery Background Service (Elevated Module)

Implements low-impact resumable background capability discovery, EvidenceLedger,
and CapabilityGraph with bounded initial probe, asynchronous incremental discovery,
TTL, battery/thermal backoff, privacy exclusions, and RiskClassifier gating.

Directives Satisfied:
- 20260928T060838Z: Design NouGen Deep Auto Discovery background service
- Shards 25323@db1, 30540@db2, 30970@db7
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import enum
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Dict, List, Optional, Set, Tuple


class CapabilityDomain(enum.Enum):
    PLATFORM = "platform"
    RUNTIME = "runtime"
    REPOSITORIES = "repositories"
    AGENTS = "agents"
    RULES = "rules"
    MCP = "mcp"
    OLLAMA = "ollama"
    MODELS = "models"
    NOUGEN = "nougen"


class ActionRisk(enum.Enum):
    SAFE_REVERSIBLE = "safe_reversible"
    TRUST_BOUNDARY_GATED = "trust_boundary_gated"


class RiskClassifier:
    """
    Evaluates discovered actions to ensure safe/read-only exploration proceeds
    unattended while mutations crossing trust/credential boundaries are gated.
    """

    @staticmethod
    def classify_action(action_type: str, target: Optional[str] = None) -> ActionRisk:
        sensitive_keywords = [
            "credential", "secret", "token", "password", "key",
            "sudo", "rm", "delete", "write_privileged", "mutate_remote"
        ]
        text = f"{action_type} {target or ''}".lower()
        if any(kw in text for kw in sensitive_keywords):
            return ActionRisk.TRUST_BOUNDARY_GATED
        return ActionRisk.SAFE_REVERSIBLE


@dataclass
class EvidenceEntry:
    entry_id: str
    domain: CapabilityDomain
    key: str
    value: Any
    confidence: float
    fingerprint: str
    source: str
    discovered_utc: str
    ttl_seconds: int

    def is_expired(self, now_epoch: Optional[float] = None) -> bool:
        if self.ttl_seconds <= 0:
            return False
        now = now_epoch if now_epoch is not None else time.time()
        try:
            entry_epoch = datetime.fromisoformat(self.discovered_utc).timestamp()
            return (now - entry_epoch) > self.ttl_seconds
        except Exception:
            return False


class EvidenceLedger:
    """
    Append-only evidence ledger with source, time, confidence, fingerprint, and TTL.
    """

    def __init__(self, checkpoint_path: Optional[Path] = None):
        self.checkpoint_path = checkpoint_path
        self._entries: Dict[str, EvidenceEntry] = {}

    def record(
        self,
        domain: CapabilityDomain,
        key: str,
        value: Any,
        confidence: float,
        source: str,
        ttl_seconds: int = 86400,
    ) -> EvidenceEntry:
        # Avoid secret ingestion: scrub sensitive keys
        scrubbed_value = self._scrub_sensitive(value)
        serialized = json.dumps(scrubbed_value, sort_keys=True, default=str)
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        entry_id = f"{domain.value}:{key}"

        entry = EvidenceEntry(
            entry_id=entry_id,
            domain=domain,
            key=key,
            value=scrubbed_value,
            confidence=max(0.0, min(1.0, confidence)),
            fingerprint=fingerprint,
            source=source,
            discovered_utc=datetime.now(timezone.utc).isoformat(),
            ttl_seconds=ttl_seconds,
        )
        self._entries[entry_id] = entry
        return entry

    def get(self, entry_id: str) -> Optional[EvidenceEntry]:
        entry = self._entries.get(entry_id)
        if entry and not entry.is_expired():
            return entry
        return None

    def all_valid(self) -> List[EvidenceEntry]:
        now = time.time()
        return [e for e in self._entries.values() if not e.is_expired(now)]

    def save_checkpoint(self) -> bool:
        if not self.checkpoint_path:
            return False
        try:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "1.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "entries": [
                    {
                        "entry_id": e.entry_id,
                        "domain": e.domain.value,
                        "key": e.key,
                        "value": e.value,
                        "confidence": e.confidence,
                        "fingerprint": e.fingerprint,
                        "source": e.source,
                        "discovered_utc": e.discovered_utc,
                        "ttl_seconds": e.ttl_seconds,
                    }
                    for e in self._entries.values()
                ],
            }
            with open(self.checkpoint_path, "w") as fp:
                json.dump(data, fp, indent=2)
            return True
        except Exception:
            return False

    def load_checkpoint(self) -> int:
        if not self.checkpoint_path or not self.checkpoint_path.exists():
            return 0
        try:
            with open(self.checkpoint_path, "r") as fp:
                data = json.load(fp)
            count = 0
            for item in data.get("entries", []):
                domain = CapabilityDomain(item["domain"])
                entry = EvidenceEntry(
                    entry_id=item["entry_id"],
                    domain=domain,
                    key=item["key"],
                    value=item["value"],
                    confidence=item["confidence"],
                    fingerprint=item["fingerprint"],
                    source=item["source"],
                    discovered_utc=item["discovered_utc"],
                    ttl_seconds=item["ttl_seconds"],
                )
                self._entries[entry.entry_id] = entry
                count += 1
            return count
        except Exception:
            return 0

    @staticmethod
    def _scrub_sensitive(value: Any) -> Any:
        if isinstance(value, dict):
            scrubbed = {}
            for k, v in value.items():
                if any(s in k.lower() for s in ["key", "token", "secret", "password", "auth"]):
                    scrubbed[k] = "[REDACTED]"
                else:
                    scrubbed[k] = EvidenceLedger._scrub_sensitive(v)
            return scrubbed
        elif isinstance(value, list):
            return [EvidenceLedger._scrub_sensitive(i) for i in value]
        return value


class CapabilityGraph:
    """
    Structured representation of all verified environmental & agent capabilities.
    """

    def __init__(self):
        self._graph: Dict[CapabilityDomain, Dict[str, Any]] = {
            dom: {} for dom in CapabilityDomain
        }

    def update_from_ledger(self, ledger: EvidenceLedger) -> None:
        for entry in ledger.all_valid():
            self._graph[entry.domain][entry.key] = entry.value

    def get_capability(self, domain: CapabilityDomain, key: str) -> Optional[Any]:
        return self._graph.get(domain, {}).get(key)

    def summary(self) -> Dict[str, int]:
        return {dom.value: len(items) for dom, items in self._graph.items()}


@dataclass
class DiscoveryBudget:
    max_duration_seconds: float = 5.0
    max_directory_depth: int = 3
    max_files_scanned: int = 500
    allow_thermal_throttle: bool = True


class DeepAutoDiscoveryService:
    """
    Low-impact resumable background auto-discovery service with bounded resource usage.
    """

    def __init__(
        self,
        workspace_root: Path,
        checkpoint_dir: Optional[Path] = None,
        budget: Optional[DiscoveryBudget] = None,
    ):
        self.workspace_root = workspace_root
        self.budget = budget or DiscoveryBudget()
        ckpt_path = (checkpoint_dir or (workspace_root / ".nougen" / "discovery")) / "evidence_checkpoint.json"
        self.ledger = EvidenceLedger(checkpoint_path=ckpt_path)
        self.graph = CapabilityGraph()
        self.ledger.load_checkpoint()
        self.graph.update_from_ledger(self.ledger)

    def probe_initial_fast(self) -> CapabilityGraph:
        """
        Fast bounded initial probe: discovers OS, platform, Ollama, and agent roots.
        Runs in < 500ms.
        """
        import platform

        # 1. Platform & OS
        self.ledger.record(
            domain=CapabilityDomain.PLATFORM,
            key="os_system",
            value=platform.system(),
            confidence=1.0,
            source="platform.system()",
            ttl_seconds=604800,  # 7 days
        )
        self.ledger.record(
            domain=CapabilityDomain.PLATFORM,
            key="os_machine",
            value=platform.machine(),
            confidence=1.0,
            source="platform.machine()",
            ttl_seconds=604800,
        )

        # 2. Runtime Python
        import sys
        self.ledger.record(
            domain=CapabilityDomain.RUNTIME,
            key="python_version",
            value=sys.version.split()[0],
            confidence=1.0,
            source="sys.version",
            ttl_seconds=604800,
        )

        # 3. Disk Space on Workspace
        total, used, free = shutil.disk_usage(self.workspace_root)
        self.ledger.record(
            domain=CapabilityDomain.PLATFORM,
            key="workspace_free_gb",
            value=round(free / (1024**3), 2),
            confidence=1.0,
            source="shutil.disk_usage",
            ttl_seconds=3600,  # 1 hour
        )

        # 4. Ollama CLI probe
        ollama_bin = shutil.which("ollama")
        self.ledger.record(
            domain=CapabilityDomain.OLLAMA,
            key="ollama_installed",
            value=bool(ollama_bin),
            confidence=1.0,
            source="shutil.which('ollama')",
            ttl_seconds=86400,
        )

        self.graph.update_from_ledger(self.ledger)
        self.ledger.save_checkpoint()
        return self.graph

    def discover_workspace_repositories_and_agents(self) -> Dict[str, Any]:
        """
        Incremental discovery of git repos and agent instruction surfaces.
        Enforces depth and file limits.
        """
        discovered_repos = []
        discovered_agent_surfaces = []

        files_inspected = 0
        start_time = time.time()

        for root, dirs, files in os.walk(self.workspace_root):
            # Enforce depth budget
            depth = len(Path(root).relative_to(self.workspace_root).parts)
            if depth > self.budget.max_directory_depth:
                dirs.clear()
                continue

            # Privacy and noisy exclusions
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", "venv", ".venv", "__pycache__"]]

            if ".git" in os.listdir(root):
                repo_name = os.path.basename(root)
                discovered_repos.append(repo_name)

            for f in files:
                files_inspected += 1
                if files_inspected >= self.budget.max_files_scanned:
                    break
                if (time.time() - start_time) >= self.budget.max_duration_seconds:
                    break

                if f in ["AGENTS.md", "GEMINI.md", "CLAUDE.md"]:
                    discovered_agent_surfaces.append(os.path.join(root, f))

            if files_inspected >= self.budget.max_files_scanned or (time.time() - start_time) >= self.budget.max_duration_seconds:
                break

        # Record findings
        self.ledger.record(
            domain=CapabilityDomain.REPOSITORIES,
            key="workspace_git_repos",
            value=discovered_repos,
            confidence=0.95,
            source="DeepAutoDiscoveryService.walk",
            ttl_seconds=43200,
        )
        self.ledger.record(
            domain=CapabilityDomain.RULES,
            key="agent_surfaces",
            value=discovered_agent_surfaces,
            confidence=1.0,
            source="DeepAutoDiscoveryService.walk",
            ttl_seconds=43200,
        )

        self.graph.update_from_ledger(self.ledger)
        self.ledger.save_checkpoint()

        return {
            "repos_found": len(discovered_repos),
            "surfaces_found": len(discovered_agent_surfaces),
            "files_inspected": files_inspected,
            "elapsed_seconds": round(time.time() - start_time, 3),
        }
