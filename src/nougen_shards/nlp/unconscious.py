"""
NouGenMorph NLP Engine — Module 5: Autonomic Unconscious Prime Directives.

Provenance:
- Source: Christopher Howard, Breakthrough to Success (CD 1: The Unconscious Mind & Neurological Repatterning)
- War-Gamed & Drafted By: Free Fleet Lane (`ollama-cloud-eatsruger` / `ollama-cloud-davemeralus`) + Local `gemma4:e2b-qat`
- Reviewed By: Antigravity Coach (UDCT Architecture Solver)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class DirectiveCheck:
    """Single unconscious prime directive check against fleet telemetry."""

    directive_id: int
    name: str
    healthy: bool
    detail: str


@dataclass(frozen=True)
class DirectiveAuditResult:
    """Aggregate autonomic health audit across the Prime Directives of the Unconscious Mind."""

    all_healthy: bool
    health_score: float
    checks: List[DirectiveCheck] = field(default_factory=list)
    autonomic_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_healthy": self.all_healthy,
            "health_score": round(self.health_score, 4),
            "checks": [
                {
                    "directive_id": c.directive_id,
                    "name": c.name,
                    "healthy": c.healthy,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
            "autonomic_actions": list(self.autonomic_actions),
        }


class UnconsciousLoop:
    """
    CD 1 Prime Directives of the Unconscious Mind mapped to NouGen Autonomic Fleet Operations:
    1. Stores Memories (FTS5 9-DB Grid + Temporal Indexing)
    2. Runs & Preserves the Body (Hardware Stadium / Disk / RAM / Thermal Protection)
    3. Repatterns & Maintains Instincts (Habit & Skill Evolution)
    4. Takes Everything Personally & Literal Positive Framing (No negative self-commands)
    5. Principle of Least Effort (Path of Least Resistance -> Local E2B & Context Sandbox First)
    6. Symbolic & Holographic Processing (Multi-Signal BM25 + Vector + Graph Synthesis)
    """

    def audit_telemetry(self, telemetry: Dict[str, Any] | None = None) -> DirectiveAuditResult:
        """Audit node and session telemetry against the 6 core unconscious prime directives."""
        data = telemetry or {}
        checks: List[DirectiveCheck] = []
        actions: List[str] = []

        # 1. Stores Memories
        shards_online = bool(data.get("shards_online", True))
        checks.append(
            DirectiveCheck(
                directive_id=1,
                name="Store & Organize Memories (FTS5 9-DB Substrate)",
                healthy=shards_online,
                detail="Canonical .nougen/shards cluster online" if shards_online else "Shard substrate unreachable",
            )
        )
        if not shards_online:
            actions.append("Reconnect canonical .nougen/shards SQLite WAL substrate.")

        # 2. Preserve the Body (Stadium Hardware Health)
        free_disk_gb = float(data.get("free_disk_gb", 10.0))
        free_ram_gb = float(data.get("free_ram_gb", 8.0))
        body_ok = free_disk_gb >= 1.5 and free_ram_gb >= 2.0
        checks.append(
            DirectiveCheck(
                directive_id=2,
                name="Preserve the Body (Hardware Stadium Integrity)",
                healthy=body_ok,
                detail=f"free_disk_gb={free_disk_gb:.1f}, free_ram_gb={free_ram_gb:.1f}",
            )
        )
        if not body_ok:
            actions.append("Reclaim temporary transcode/cache files and throttle parallel workers.")

        # 3. Repattern Instincts & Habits
        skills_loaded = bool(data.get("skills_loaded", True))
        checks.append(
            DirectiveCheck(
                directive_id=3,
                name="Generate & Repattern Habits (Skill Evolution)",
                healthy=skills_loaded,
                detail="Mandatory fleet skills active" if skills_loaded else "Skills bypassed",
            )
        )
        if not skills_loaded:
            actions.append("Call apply_skills(task) before executing domain work.")

        # 4. Literal Positive Instruction (Zero Negative Commands)
        neg_commands = int(data.get("negative_commands", 0))
        pos_ok = neg_commands == 0
        checks.append(
            DirectiveCheck(
                directive_id=4,
                name="Process Positive Literal Instructions",
                healthy=pos_ok,
                detail="Instructions framed in positive target state" if pos_ok else f"{neg_commands} negative commands detected",
            )
        )
        if not pos_ok:
            actions.append("Run WFOEngine and DecisionDestroyer to convert negations into positive targets.")

        # 5. Principle of Least Effort (Conserve Energy via Local E2B & Context Mode)
        local_first = bool(data.get("local_first", True))
        checks.append(
            DirectiveCheck(
                directive_id=5,
                name="Principle of Least Effort (Local E2B & Sandbox First)",
                healthy=local_first,
                detail="Zero-cost local E2B & free fleet lanes prioritized" if local_first else "Unrouted cloud token burn",
            )
        )
        if not local_first:
            actions.append("Route bulk drafting and inspection through local gemma4:e2b-qat and Fleet.map.")

        # 6. Symbolic & Holographic Synthesis
        context_logged = bool(data.get("context_logged", True))
        checks.append(
            DirectiveCheck(
                directive_id=6,
                name="Holographic Context & Symbol Binding",
                healthy=context_logged,
                detail="Session context synchronized with durable shards" if context_logged else "Session context unindexed",
            )
        )
        if not context_logged:
            actions.append("Log session state via log_context_event and promote invariants to shards.")

        healthy_count = sum(1 for c in checks if c.healthy)
        score = healthy_count / float(len(checks))
        return DirectiveAuditResult(
            all_healthy=healthy_count == len(checks),
            health_score=score,
            checks=checks,
            autonomic_actions=actions,
        )
