"""Pilot Supervision Engine for NouGen.

Operationalizes live multi-agent pilot supervision and progressive guidance:
- Pilot (Player/Executor): Bounded single-play execution agent
- Co-Pilot (Reasoning Governor): Real-time observer of trajectory, margin, invariants & costs
- Supervisor (Coach/Apollo): Higher-intelligence interceptor that steers, breaks deadlocks,
  allocates cognitive quanta, and gates mutations
- Operator (GM/User): Supreme authority for mutation approvals and strategic resets

Authority: Relay leg 20260829T120432Z__chatgpt-app__g-whoentertains / Rule 0.0.
"""
from __future__ import annotations

import enum
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import core
from .reasoning_governor import (
    ConsequenceClass,
    GovernorAction,
    ReasoningDecision,
    ReasoningGovernor,
    TaskClass,
    TrajectoryCheckpoint,
    compute_cognitive_yield,
)
from .progressive_skills import (
    ProgressiveSkillManager,
    SkillTier,
    get_progressive_skill_manager,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Classifications
# ---------------------------------------------------------------------------

class SupervisionRole(str, enum.Enum):
    """Hierarchy roles in the Pilot Supervision Engine."""
    PILOT = "PILOT"              # Player on field: Executes bounded play (Sol-Ai/Gemma4/Worker)
    CO_PILOT = "CO_PILOT"        # Reasoning Governor: Real-time telemetry, epistemic bounds
    SUPERVISOR = "SUPERVISOR"    # Coach: Oversees trajectory, intercepts loops, steers (Apollo)
    OPERATOR = "OPERATOR"        # GM: Supreme authority, mutation approval gate (GM/User)


class InterventionType(str, enum.Enum):
    """Specific supervisory interventions applied to a running trajectory."""
    NONE = "NONE"                              # No intervention required, pilot proceeding
    STEER = "STEER"                            # Inject corrective prompt / focus subgoals
    TOOL_RESTRICTION = "TOOL_RESTRICTION"      # Restrict or disallow cycling tool
    COGNITIVE_EXPANSION = "COGNITIVE_EXPANSION"# Authorize larger reasoning quantum
    ROLLBACK = "ROLLBACK"                      # Directive to discard corrupted state delta
    HALT = "HALT"                              # Immediate stop due to severe failure
    MUTATION_GATE_ESCALATE = "MUTATION_GATE_ESCALATE" # Stop at mutation gate for operator
    SKILL_INJECT = "SKILL_INJECT"              # Inject progressive skill package into prompt


class PilotStatus(str, enum.Enum):
    """State of a supervised pilot session."""
    INITIALIZED = "INITIALIZED"
    EXECUTING = "EXECUTING"
    PAUSED_SUPERVISION = "PAUSED_SUPERVISION"
    ESCALATED_HUMAN = "ESCALATED_HUMAN"
    COMPLETED_SUCCESS = "COMPLETED_SUCCESS"
    COMPLETED_ABSTAIN = "COMPLETED_ABSTAIN"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class SupervisionDirective:
    """Actionable instruction dispatched from Supervisor to Pilot."""
    directive_id: str
    timestamp: str
    intervention_type: InterventionType
    instruction: str
    target_role: SupervisionRole = SupervisionRole.PILOT
    allocated_token_quantum: int = 0
    injected_skill_name: Optional[str] = None
    injected_skill_instructions: Optional[str] = None
    tool_allowlist: Optional[List[str]] = None
    tool_denylist: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PilotStepRecord:
    """Record of a single supervised step in a trajectory."""
    step_index: int
    timestamp: str
    checkpoint: TrajectoryCheckpoint
    decision: ReasoningDecision
    directive: Optional[SupervisionDirective] = None
    action_taken: str = ""
    tool_name: Optional[str] = None
    tool_output_summary: str = ""


@dataclass
class PilotSession:
    """Complete auditable session of a supervised pilot run."""
    session_id: str
    task_description: str
    task_class: TaskClass
    consequence_class: ConsequenceClass
    pilot_name: str = "Sol-Ai"
    supervisor_name: str = "Apollo"
    operator_name: str = "GM"
    status: PilotStatus = PilotStatus.INITIALIZED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    
    # Active Skills & Directives
    active_skills: List[str] = field(default_factory=list)
    step_records: List[PilotStepRecord] = field(default_factory=list)
    directives_issued: List[SupervisionDirective] = field(default_factory=list)
    
    # Financial & Resource Telemetry
    total_tokens_spent: int = 0
    reasoning_tokens_spent: int = 0
    total_cost_usd: str = "0.0000"
    cognitive_yield: Optional[Dict[str, Any]] = None
    extracted_skill_candidate: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_description": self.task_description,
            "task_class": self.task_class.value,
            "consequence_class": self.consequence_class.name,
            "pilot_name": self.pilot_name,
            "supervisor_name": self.supervisor_name,
            "operator_name": self.operator_name,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "active_skills": self.active_skills,
            "steps_count": len(self.step_records),
            "directives_count": len(self.directives_issued),
            "total_tokens_spent": self.total_tokens_spent,
            "reasoning_tokens_spent": self.reasoning_tokens_spent,
            "total_cost_usd": self.total_cost_usd,
            "cognitive_yield": self.cognitive_yield,
            "extracted_skill_candidate": self.extracted_skill_candidate,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Pilot Supervisor Engine
# ---------------------------------------------------------------------------

class PilotSupervisor:
    """Live supervisor governing Pilot agent execution, intervention, and skill evolution."""

    def __init__(
        self,
        governor: Optional[ReasoningGovernor] = None,
        skill_manager: Optional[ProgressiveSkillManager] = None,
        sessions_dir: Optional[Path] = None,
    ):
        self.governor = governor or ReasoningGovernor()
        self.skill_manager = skill_manager or get_progressive_skill_manager()
        self.sessions_dir = sessions_dir or (core.GLOBAL_DIR / "pilot_supervision_sessions").resolve()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._active_sessions: Dict[str, PilotSession] = {}

    def start_session(
        self,
        task_description: str,
        task_class: TaskClass = TaskClass.ROUTINE_LOGIC,
        consequence_class: ConsequenceClass = ConsequenceClass.C0_READ_ONLY,
        pilot_name: str = "Sol-Ai",
        supervisor_name: str = "Apollo",
        initial_skills: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PilotSession:
        """Starts a new supervised pilot execution session."""
        session_id = f"pilot_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Discover matching progressive skills if not explicitly provided
        skills_to_use = list(initial_skills or [])
        if not skills_to_use:
            for s in self.skill_manager.list_skills():
                if s.tier in (SkillTier.PILOT, SkillTier.PROMOTED, SkillTier.CANONICAL):
                    if any(trig.lower() in task_description.lower() for trig in s.usage_triggers):
                        skills_to_use.append(s.name)

        session = PilotSession(
            session_id=session_id,
            task_description=task_description,
            task_class=task_class,
            consequence_class=consequence_class,
            pilot_name=pilot_name,
            supervisor_name=supervisor_name,
            status=PilotStatus.EXECUTING,
            created_at=now_iso,
            updated_at=now_iso,
            active_skills=skills_to_use,
            metadata=metadata or {},
        )
        self._active_sessions[session_id] = session
        self.save_session(session)

        # Log session ignition shard
        core.capture(
            event_type="PILOT_SESSION_STARTED",
            title=f"Pilot Supervision Session: {session_id}",
            content=json.dumps(session.to_dict(), indent=2),
            tags=["pilot_supervision", "ignition", pilot_name.lower()]
        )

        return session

    def evaluate_step(
        self,
        session_id: str,
        checkpoint: TrajectoryCheckpoint,
        action_taken: str = "",
        tool_name: Optional[str] = None,
        tool_output_summary: str = "",
    ) -> Tuple[ReasoningDecision, Optional[SupervisionDirective]]:
        """Evaluates a single step of the pilot agent, emitting governor decisions and supervisor directives."""
        session = self._active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found")

        # 1. Co-Pilot Evaluation via Reasoning Governor
        decision = self.governor.evaluate(checkpoint)
        directive: Optional[SupervisionDirective] = None
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 2. Supervisor Interception Logic
        if decision.selected_action == GovernorAction.ASK_SUPERVISOR:
            # Loop / plateau detected: Coach intervenes to break deadlock
            directive = SupervisionDirective(
                directive_id=f"dir_{uuid.uuid4().hex[:8]}",
                timestamp=now_iso,
                intervention_type=InterventionType.STEER,
                instruction=(
                    f"SUPERVISOR INTERVENTION: Cognitive stall/loop detected at step {checkpoint.step_index}. "
                    "Refocus immediately on unresolved constraints and execute verification check before proceeding."
                ),
                allocated_token_quantum=decision.allocated_token_quantum or 1000,
                tool_denylist=[tool_name] if tool_name and checkpoint.repeated_conclusions_count >= 2 else None,
            )
            session.status = PilotStatus.PAUSED_SUPERVISION

        elif decision.selected_action == GovernorAction.ESCALATE_HUMAN:
            # Mutation gate hit: stop and require GM approval
            directive = SupervisionDirective(
                directive_id=f"dir_{uuid.uuid4().hex[:8]}",
                timestamp=now_iso,
                intervention_type=InterventionType.MUTATION_GATE_ESCALATE,
                instruction="MUTATION GATE HIT: Action requires explicit GM approval before execution.",
                allocated_token_quantum=0,
            )
            session.status = PilotStatus.ESCALATED_HUMAN

        elif decision.selected_action == GovernorAction.VERIFY and decision.reason_code == "PREMATURE_STOP_BLOCKED":
            # Premature stop prevented: mandate verification pass
            directive = SupervisionDirective(
                directive_id=f"dir_{uuid.uuid4().hex[:8]}",
                timestamp=now_iso,
                intervention_type=InterventionType.STEER,
                instruction="Contract claimed satisfied but verification incomplete. Run automated verification check now.",
                allocated_token_quantum=decision.allocated_token_quantum,
            )

        elif decision.selected_action == GovernorAction.RETRIEVE_MEMORY:
            # Evidence missing: inject skill context or direct memory recall
            matching_skills = [
                s for s in self.skill_manager.list_skills()
                if s.tier in (SkillTier.PILOT, SkillTier.PROMOTED, SkillTier.CANONICAL)
                and s.name not in session.active_skills
            ]
            if matching_skills:
                chosen = matching_skills[0]
                session.active_skills.append(chosen.name)
                directive = SupervisionDirective(
                    directive_id=f"dir_{uuid.uuid4().hex[:8]}",
                    timestamp=now_iso,
                    intervention_type=InterventionType.SKILL_INJECT,
                    instruction=f"Injecting Progressive Skill '{chosen.name}' into execution context.",
                    injected_skill_name=chosen.name,
                    injected_skill_instructions=chosen.level_2_activation(),
                    allocated_token_quantum=decision.allocated_token_quantum,
                )

        # 3. Record Step
        record = PilotStepRecord(
            step_index=checkpoint.step_index,
            timestamp=now_iso,
            checkpoint=checkpoint,
            decision=decision,
            directive=directive,
            action_taken=action_taken,
            tool_name=tool_name,
            tool_output_summary=tool_output_summary[:500],
        )
        session.step_records.append(record)
        if directive:
            session.directives_issued.append(directive)

        session.total_tokens_spent = checkpoint.total_tokens_spent
        session.reasoning_tokens_spent = checkpoint.reasoning_tokens_spent
        session.total_cost_usd = str(checkpoint.cost_spent_usd)
        session.updated_at = now_iso

        self.save_session(session)
        return decision, directive

    def finalize_session(
        self,
        session_id: str,
        final_success: bool,
        total_tokens: int,
        reasoning_tokens: int,
        total_cost_usd: Decimal,
        extract_candidate_skill: bool = True,
    ) -> PilotSession:
        """Finalizes the pilot supervision session, computes yield, and promotes candidate skills."""
        session = self._active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found")

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        decisions = [r.decision for r in session.step_records]
        
        # 1. Compute Cognitive Yield Metrics
        yield_metrics = compute_cognitive_yield(
            decisions=decisions,
            final_success=final_success,
            total_tokens=total_tokens,
            reasoning_tokens=reasoning_tokens,
            total_cost_usd=total_cost_usd,
        )
        session.cognitive_yield = yield_metrics.to_dict()
        session.total_tokens_spent = total_tokens
        session.reasoning_tokens_spent = reasoning_tokens
        session.total_cost_usd = str(total_cost_usd)

        # 2. Update status
        if final_success:
            session.status = PilotStatus.COMPLETED_SUCCESS
        else:
            session.status = PilotStatus.FAILED

        # 3. Update skill telemetry for used active skills
        for skill_name in session.active_skills:
            try:
                self.skill_manager.record_run(
                    name=skill_name,
                    success=final_success,
                    tokens_spent=total_tokens // max(1, len(session.active_skills)),
                    cost_usd=total_cost_usd / Decimal(max(1, len(session.active_skills))),
                    cognitive_yield=yield_metrics.verified_success_per_dollar if final_success else 0.0,
                    regressed=not final_success,
                )
            except Exception as exc:
                logger.warning("Could not record telemetry for skill %s: %s", skill_name, exc)

        # 4. Extract candidate skill on high-yield successful runs
        if final_success and extract_candidate_skill and len(session.step_records) >= 2:
            candidate_name = f"skill-{session.task_class.value.lower()}-{uuid.uuid4().hex[:6]}"
            desc = f"Procedural workflow for {session.task_description[:100]}"
            body = (
                f"## Supervised Workflow\n"
                f"- Task: {session.task_description}\n"
                f"- Class: {session.task_class.value}\n"
                f"- Actions executed: {len(session.step_records)} steps\n"
                f"- Directives resolved: {len(session.directives_issued)}\n"
            )
            candidate = self.skill_manager.register_candidate(
                name=candidate_name,
                description=desc,
                body=body,
                grounding=f"Verified through Pilot Supervision Session {session_id}",
                usage_triggers=[session.task_class.value.lower(), "supervised-workflow"],
                invariants=["All invariants verified during pilot supervision run"],
            )
            session.extracted_skill_candidate = candidate.name

        session.updated_at = now_iso
        self.save_session(session)

        # Capture session completion to memory vault
        core.capture(
            event_type="PILOT_SESSION_COMPLETED",
            title=f"Pilot Session Finalized: {session_id} ({session.status.value})",
            content=json.dumps(session.to_dict(), indent=2),
            tags=["pilot_supervision", "completion", session.status.value.lower()]
        )

        return session

    def save_session(self, session: PilotSession) -> Path:
        """Persists session record to disk."""
        path = self.sessions_dir / f"{session.session_id}.json"
        path.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
        return path

    def get_session(self, session_id: str) -> Optional[PilotSession]:
        """Retrieves an active or archived pilot session."""
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]
        path = self.sessions_dir / f"{session_id}.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                # Reconstruct lightweight session
                session = PilotSession(
                    session_id=data["session_id"],
                    task_description=data["task_description"],
                    task_class=TaskClass(data["task_class"]),
                    consequence_class=ConsequenceClass[data["consequence_class"]],
                    pilot_name=data.get("pilot_name", "Sol-Ai"),
                    supervisor_name=data.get("supervisor_name", "Apollo"),
                    status=PilotStatus(data.get("status", "INITIALIZED")),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    active_skills=data.get("active_skills", []),
                    total_tokens_spent=data.get("total_tokens_spent", 0),
                    reasoning_tokens_spent=data.get("reasoning_tokens_spent", 0),
                    total_cost_usd=data.get("total_cost_usd", "0.0000"),
                    cognitive_yield=data.get("cognitive_yield"),
                    extracted_skill_candidate=data.get("extracted_skill_candidate"),
                    metadata=data.get("metadata", {}),
                )
                self._active_sessions[session_id] = session
                return session
            except Exception as exc:
                logger.warning("Failed to load session %s from disk: %s", session_id, exc)
        return None

    def export_supervision_summary(self) -> str:
        """Emits executive markdown summary of all pilot supervision sessions."""
        files = list(self.sessions_dir.glob("*.json"))
        if not files:
            return "(no pilot supervision sessions recorded)"
        
        lines = ["# 🛡️ Pilot Supervision Ledger", ""]
        lines.append("| Session ID | Task Class | Consequence | Status | Tokens | Directives | Extracted Skill |")
        lines.append("|---|---|---|---|---|---|---|")
        
        for f in sorted(files, reverse=True)[:10]:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                lines.append(
                    f"| `{d['session_id']}` | `{d['task_class']}` | `{d['consequence_class']}` | "
                    f"**{d['status']}** | {d['total_tokens_spent']:,} | {d['directives_count']} | `{d.get('extracted_skill_candidate') or 'None'}` |"
                )
            except Exception:
                continue
        return "\n".join(lines)


# Singleton factory helper
_GLOBAL_SUPERVISOR: Optional[PilotSupervisor] = None

def get_pilot_supervisor() -> PilotSupervisor:
    global _GLOBAL_SUPERVISOR
    if _GLOBAL_SUPERVISOR is None:
        _GLOBAL_SUPERVISOR = PilotSupervisor()
    return _GLOBAL_SUPERVISOR
