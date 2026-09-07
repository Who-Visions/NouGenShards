"""Progressive Skill Promotion Framework for NouGen.

Implements the 4-tier progressive promotion lifecycle for autonomous agent skills:
- Tier 0: CANDIDATE (Newly observed/evolved procedural knowledge, unverified)
- Tier 1: PILOT (Passed virtual sandbox verification, undergoing supervised pilot runs)
- Tier 2: PROMOTED (Demonstrated empirical success, high cognitive yield, zero critical regressions)
- Tier 3: CANONICAL (Fleet-standard, mesh-wide verified capability)

Progressive Disclosure:
- Level 1 (Discovery): Light metadata (name, description, tier, triggers) for system prompts
- Level 2 (Activation): Full instruction body, invariants, and implementation scripts loaded on demand

Authority: Relay leg 20260829T120432Z / Rule 0.0.
"""
from __future__ import annotations

import enum
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import core, nougen_sandbox

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Configurations
# ---------------------------------------------------------------------------

class SkillTier(str, enum.Enum):
    """Lifecycle progression tiers for skills."""
    CANDIDATE = "CANDIDATE"      # Tier 0: Unverified draft / newly synthesized
    PILOT = "PILOT"              # Tier 1: Sandbox-verified, bounded pilot trial
    PROMOTED = "PROMOTED"        # Tier 2: Multi-run verified in live supervision
    CANONICAL = "CANONICAL"      # Tier 3: Core fleet/mesh capability
    DEPRECATED = "DEPRECATED"    # Tier -1: Superseded or regressed


@dataclass
class PromotionCriteria:
    """Quantitative thresholds required to promote a skill between tiers."""
    min_pilot_runs: int = 1               # Runs to pass sandbox validation
    min_promoted_runs: int = 3            # Empirical supervised runs before PROMOTED
    min_canonical_runs: int = 10          # Production runs before CANONICAL
    min_success_rate: float = 0.90        # 90% required success rate
    min_cognitive_yield: float = 0.40     # Average marginal yield score threshold
    max_critical_regressions: int = 0     # Zero tolerance for severe invariant breakage


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ProgressiveSkill:
    """Typed representation of a progressively managed skill."""
    name: str
    description: str
    tier: SkillTier = SkillTier.CANDIDATE
    version: str = "0.1.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    body: str = ""
    grounding: str = ""
    virtual_task_code: str = ""
    usage_triggers: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    
    # Telemetry & Empirical Statistics
    runs_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_tokens_spent: int = 0
    total_cost_usd: str = "0.0000"
    avg_cognitive_yield: float = 0.0
    critical_regressions: int = 0
    promotion_history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.runs_count == 0:
            return 0.0
        return self.success_count / self.runs_count

    def to_yaml_frontmatter(self) -> str:
        """Emits standard YAML frontmatter conforming to Antigravity/Stitch/OpenSkill standard."""
        clean_desc = self.description.replace('"', '\\"').replace("\n", " ")
        triggers_str = json.dumps(self.usage_triggers) if self.usage_triggers else "[]"
        return (
            "---\n"
            f"name: {self.name}\n"
            f"description: \"{clean_desc}\"\n"
            f"tier: {self.tier.value}\n"
            f"version: {self.version}\n"
            f"usage_triggers: {triggers_str}\n"
            "---\n"
        )

    def level_1_disclosure(self) -> Dict[str, Any]:
        """Level 1 Progressive Disclosure: Light metadata for system prompt injection."""
        return {
            "name": self.name,
            "description": self.description,
            "tier": self.tier.value,
            "version": self.version,
            "usage_triggers": self.usage_triggers,
            "success_rate": round(self.success_rate, 2),
            "runs_count": self.runs_count,
        }

    def level_2_activation(self) -> str:
        """Level 2 Progressive Disclosure: Full executable SKILL.md body and instructions."""
        frontmatter = self.to_yaml_frontmatter()
        invariants_block = ""
        if self.invariants:
            invariants_block = "\n## Verified Invariants\n" + "\n".join(f"- {inv}" for inv in self.invariants) + "\n"
            
        grounding_block = ""
        if self.grounding:
            grounding_block = f"\n## Grounding & Context\n{self.grounding}\n"

        body_content = self.body.strip() if self.body else "Follow verified procedure."
        return f"{frontmatter}\n# SKILL: {self.name}\n{grounding_block}{invariants_block}\n## Implementation Guide\n{body_content}\n"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tier"] = self.tier.value
        d["success_rate"] = self.success_rate
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProgressiveSkill:
        d = dict(data)
        if "tier" in d and isinstance(d["tier"], str):
            d["tier"] = SkillTier(d["tier"])
        d.pop("success_rate", None)
        return cls(**d)


# ---------------------------------------------------------------------------
# Progressive Skill Promotion Manager
# ---------------------------------------------------------------------------

class ProgressiveSkillManager:
    """Orchestrates progressive skill discovery, evaluation, promotion, and persistence."""

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        registry_path: Optional[Path] = None,
        criteria: Optional[PromotionCriteria] = None,
    ):
        self.skills_dir = skills_dir or (core.GLOBAL_DIR / "skills").resolve()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = registry_path or (self.skills_dir / "progressive_registry.json")
        self.criteria = criteria or PromotionCriteria()
        self._skills: Dict[str, ProgressiveSkill] = {}
        self.load_registry()

    def load_registry(self) -> None:
        """Loads registered progressive skills from disk."""
        if self.registry_path.is_file():
            try:
                data = json.loads(self.registry_path.read_text(encoding="utf-8"))
                for item in data.get("skills", []):
                    skill = ProgressiveSkill.from_dict(item)
                    self._skills[skill.name.lower()] = skill
            except Exception as exc:
                logger.warning("Failed to parse progressive registry %s: %s", self.registry_path, exc)

    def save_registry(self) -> None:
        """Persists the progressive skills registry metadata to disk."""
        try:
            payload = {
                "version": "1.0",
                "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "total_skills": len(self._skills),
                "skills": [s.to_dict() for s in self._skills.values()],
            }
            self.registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to save progressive registry: %s", exc)

    def register_candidate(
        self,
        name: str,
        description: str,
        body: str,
        grounding: str = "",
        virtual_task_code: str = "",
        usage_triggers: Optional[List[str]] = None,
        invariants: Optional[List[str]] = None,
    ) -> ProgressiveSkill:
        """Registers a newly synthesized Tier 0 (CANDIDATE) skill."""
        clean_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()).strip("-") or "candidate-skill"
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        skill = ProgressiveSkill(
            name=clean_name,
            description=description.strip() or f"Candidate skill for {clean_name}",
            tier=SkillTier.CANDIDATE,
            version="0.1.0",
            created_at=now_iso,
            updated_at=now_iso,
            body=body,
            grounding=grounding,
            virtual_task_code=virtual_task_code,
            usage_triggers=usage_triggers or [clean_name],
            invariants=invariants or [],
            promotion_history=[{
                "tier": SkillTier.CANDIDATE.value,
                "timestamp": now_iso,
                "reason": "Initial candidate registration",
            }],
        )
        self._skills[clean_name] = skill
        self.save_skill_package(skill)
        self.save_registry()
        return skill

    def verify_candidate_sandbox(self, name: str) -> bool:
        """Runs virtual task verification in sandbox. On success, promotes CANDIDATE -> PILOT."""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found")

        if not skill.virtual_task_code:
            # Generate default invariant verification task if not explicitly provided
            test_script = (
                "import sys\n"
                f"NAME = {skill.name!r}\n"
                f"BODY = {skill.body!r}\n"
                "assert len(NAME) > 2, 'invalid skill name'\n"
                "assert len(BODY) > 20, 'skill body is empty or too brief'\n"
                "print('Virtual Task Passed')\n"
            )
        else:
            test_script = skill.virtual_task_code

        # Run in trusted execution sandbox
        result = nougen_sandbox.execute_sandboxed(test_script, language="python", trusted=True)
        verified = "Virtual Task Passed" in result

        if verified:
            self.promote_skill(
                name=skill.name,
                target_tier=SkillTier.PILOT,
                reason="Passed virtual task verification in sandbox",
            )
            return True
        else:
            logger.warning("Sandbox verification failed for candidate %s: %s", name, result)
            return False

    def record_run(
        self,
        name: str,
        success: bool,
        tokens_spent: int = 0,
        cost_usd: Decimal = Decimal("0.0000"),
        cognitive_yield: float = 0.50,
        regressed: bool = False,
    ) -> ProgressiveSkill:
        """Records an execution run for a skill and updates running statistical telemetry."""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found")

        skill.runs_count += 1
        if success:
            skill.success_count += 1
        else:
            skill.failure_count += 1

        skill.total_tokens_spent += tokens_spent
        current_cost = Decimal(skill.total_cost_usd) + cost_usd
        skill.total_cost_usd = str(current_cost)

        # Exponential moving average of cognitive yield
        alpha = 0.3
        if skill.runs_count == 1:
            skill.avg_cognitive_yield = cognitive_yield
        else:
            skill.avg_cognitive_yield = (alpha * cognitive_yield) + ((1 - alpha) * skill.avg_cognitive_yield)

        if regressed:
            skill.critical_regressions += 1
            if skill.tier in (SkillTier.PROMOTED, SkillTier.CANONICAL):
                self.demote_skill(
                    name=skill.name,
                    target_tier=SkillTier.PILOT,
                    reason=f"Critical regression detected in execution run (run #{skill.runs_count})",
                )

        skill.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.save_skill_package(skill)
        self.save_registry()
        return skill

    def evaluate_promotion(self, name: str) -> Tuple[bool, Optional[SkillTier], str]:
        """Evaluates whether a skill qualifies for promotion to the next tier."""
        skill = self.get_skill(name)
        if not skill:
            return False, None, f"Skill '{name}' not found"

        if skill.tier == SkillTier.CANDIDATE:
            if skill.runs_count >= self.criteria.min_pilot_runs and skill.success_rate >= 1.0:
                return True, SkillTier.PILOT, "Candidate has passed verification hurdle."
            return False, None, f"Candidate requires sandbox verification (runs: {skill.runs_count}/{self.criteria.min_pilot_runs})."

        elif skill.tier == SkillTier.PILOT:
            if (
                skill.runs_count >= self.criteria.min_promoted_runs
                and skill.success_rate >= self.criteria.min_success_rate
                and skill.avg_cognitive_yield >= self.criteria.min_cognitive_yield
                and skill.critical_regressions <= self.criteria.max_critical_regressions
            ):
                return True, SkillTier.PROMOTED, (
                    f"Pilot satisfied empirical criteria ({skill.runs_count} runs, "
                    f"{skill.success_rate * 100:.1f}% success, yield {skill.avg_cognitive_yield:.2f})."
                )
            return False, None, (
                f"Pilot requires >= {self.criteria.min_promoted_runs} runs and "
                f">={self.criteria.min_success_rate * 100}% success rate (current: {skill.runs_count} runs, {skill.success_rate * 100:.1f}%)."
            )

        elif skill.tier == SkillTier.PROMOTED:
            if (
                skill.runs_count >= self.criteria.min_canonical_runs
                and skill.success_rate >= 0.95
                and skill.critical_regressions == 0
            ):
                return True, SkillTier.CANONICAL, (
                    f"Promoted skill reached mesh-wide canonical status ({skill.runs_count} runs, "
                    f"{skill.success_rate * 100:.1f}% success rate)."
                )
            return False, None, f"Promoted skill requires >= {self.criteria.min_canonical_runs} stable runs for Canonical tier."

        return False, None, f"Skill is already at top tier '{skill.tier.value}'."

    def promote_skill(
        self,
        name: str,
        target_tier: Optional[SkillTier] = None,
        reason: str = "Empirical criteria satisfied",
        force: bool = False,
    ) -> ProgressiveSkill:
        """Promotes a skill to the next or specified tier."""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found")

        if target_tier is None:
            can_promote, next_tier, eval_reason = self.evaluate_promotion(name)
            if not can_promote and not force:
                raise ValueError(f"Promotion rejected: {eval_reason}")
            target_tier = next_tier or SkillTier.PROMOTED
            reason = eval_reason

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        old_tier = skill.tier
        skill.tier = target_tier
        skill.updated_at = now_iso
        skill.promotion_history.append({
            "from_tier": old_tier.value,
            "to_tier": target_tier.value,
            "timestamp": now_iso,
            "reason": reason,
            "runs_count": skill.runs_count,
            "success_rate": skill.success_rate,
        })

        # Bump version on tier promotions
        major, minor, patch = map(int, skill.version.split("."))
        if target_tier in (SkillTier.PROMOTED, SkillTier.CANONICAL):
            skill.version = f"{major + 1}.0.0"
        else:
            skill.version = f"{major}.{minor + 1}.0"

        self.save_skill_package(skill)
        self.save_registry()

        # Capture promotion milestone to shard vault
        core.capture(
            event_type="SKILL_PROMOTED",
            title=f"Skill Promoted: {skill.name} -> {target_tier.value}",
            content=json.dumps(skill.to_dict(), indent=2),
            tags=["progressive_skills", "promotion", target_tier.value.lower()]
        )

        return skill

    def demote_skill(
        self,
        name: str,
        target_tier: SkillTier = SkillTier.PILOT,
        reason: str = "Regression or failure in production",
    ) -> ProgressiveSkill:
        """Demotes a skill upon regression or policy violation."""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found")

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        old_tier = skill.tier
        skill.tier = target_tier
        skill.updated_at = now_iso
        skill.promotion_history.append({
            "from_tier": old_tier.value,
            "to_tier": target_tier.value,
            "timestamp": now_iso,
            "reason": f"DEMOTION: {reason}",
            "runs_count": skill.runs_count,
            "success_rate": skill.success_rate,
        })

        self.save_skill_package(skill)
        self.save_registry()

        core.capture(
            event_type="SKILL_DEMOTED",
            title=f"Skill Demoted: {skill.name} -> {target_tier.value}",
            content=json.dumps(skill.to_dict(), indent=2),
            tags=["progressive_skills", "demotion", target_tier.value.lower()]
        )

        return skill

    def get_skill(self, name: str) -> Optional[ProgressiveSkill]:
        """Looks up a progressive skill by name (case-insensitive)."""
        return self._skills.get(name.strip().lower())

    def list_skills(self, tier: Optional[SkillTier] = None) -> List[ProgressiveSkill]:
        """Lists all registered progressive skills, optionally filtered by tier."""
        if tier is None:
            return list(self._skills.values())
        return [s for s in self._skills.values() if s.tier == tier]

    def save_skill_package(self, skill: ProgressiveSkill) -> Path:
        """Writes canonical <skill-name>/SKILL.md and <skill-name>/metadata.json packages."""
        pkg_dir = self.skills_dir / skill.name
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write SKILL.md with full Level 2 instructions
        skill_md_path = pkg_dir / "SKILL.md"
        skill_md_path.write_text(skill.level_2_activation(), encoding="utf-8")

        # 2. Write metadata.json for fast Level 1 progressive disclosure
        meta_path = pkg_dir / "metadata.json"
        meta_path.write_text(json.dumps(skill.level_1_disclosure(), indent=2), encoding="utf-8")

        return skill_md_path

    def export_roster(self) -> str:
        """Returns clean markdown summary roster of all progressive skills."""
        if not self._skills:
            return "(no progressive skills registered)"
        lines = []
        for s in sorted(self._skills.values(), key=lambda x: (x.tier.value, x.name)):
            rate = f"{s.success_rate * 100:.0f}%" if s.runs_count > 0 else "N/A"
            lines.append(f"- **[{s.tier.value}]** `{s.name}` (v{s.version}) - {s.description} | Runs: {s.runs_count} (Pass: {rate})")
        return "\n".join(lines)


# Singleton factory helper
_GLOBAL_MANAGER: Optional[ProgressiveSkillManager] = None

def get_progressive_skill_manager() -> ProgressiveSkillManager:
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = ProgressiveSkillManager()
    return _GLOBAL_MANAGER
