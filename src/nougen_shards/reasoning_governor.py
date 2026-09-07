"""
Adaptive Reasoning Governance for NouGen.

Master Doctrine:
    BUY COGNITION ONLY WHILE ITS EXPECTED MARGINAL VERIFIED VALUE REMAINS POSITIVE.

This module implements the runtime governor that decides whether an agent should
continue reasoning, retrieve memory, hydrate evidence, call tools, consult a supervisor,
verify, act, abstain, escalate, or stop. It enforces the separation between the
Reasoning Governor ("Is more cognition likely to improve state?") and the Epistemic Gate
("Is current evidence sufficient to license action?").

Authority: NouGen Relay Leg 20260829T120647Z__claude-app__g-whoentertains / Rule 0.0.
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Enums & Classifications
# ---------------------------------------------------------------------------

class TaskClass(str, enum.Enum):
    """Classification of the cognitive demand of a task."""
    FACTUAL_LOOKUP = "FACTUAL_LOOKUP"          # Low reasoning, retrieval-heavy
    ROUTINE_LOGIC = "ROUTINE_LOGIC"            # Deterministic, shallow reasoning
    CODE_REFACTOR = "CODE_REFACTOR"            # Structural, medium reasoning
    SYSTEM_ARCHITECTURE = "SYSTEM_ARCHITECTURE"# Deep multi-component reasoning
    INFRA_MUTATION = "INFRA_MUTATION"          # High risk, verification-heavy
    TAX_FINANCE_AUDIT = "TAX_FINANCE_AUDIT"    # Precision & strict compliance
    OPEN_ENDED_RESEARCH = "OPEN_ENDED_RESEARCH"# Exploratory, hypothesis-heavy
    UNKNOWN = "UNKNOWN"                        # Default unclassified


class ConsequenceClass(int, enum.Enum):
    """Operational impact tier of the eventual action."""
    C0_READ_ONLY = 0              # Zero external side effect (inspections, dry runs)
    C1_REVERSIBLE_LOCAL = 1       # Scratch edits, temporary files, local logs
    C2_EXTERNAL_READ_CALL = 2     # API queries, remote fetches, token expenditure
    C3_STATEFUL_MUTATION = 3      # Git commits, database writes, build deploys
    C4_IRREVERSIBLE_PROD = 4      # Production pushes, financial transactions, schema drops


class RuntimeState(str, enum.Enum):
    """The three diagnostic cognitive states."""
    UNDER_REASONING = "UNDER_REASONING"    # Stops before invariants/evidence are satisfied
    ADEQUATE_REASONING = "ADEQUATE_REASONING" # Minimum sufficient cognition for contract
    OVER_REASONING = "OVER_REASONING"      # Cognition continues after marginal progress collapsed


class GovernorAction(str, enum.Enum):
    """Action directed by the Reasoning Governor at each trajectory checkpoint."""
    CONTINUE_REASONING = "CONTINUE_REASONING"  # Spend next cognitive quantum
    RETRIEVE_MEMORY = "RETRIEVE_MEMORY"        # Fetch cached cognition/shards
    HYDRATE_EVIDENCE = "HYDRATE_EVIDENCE"      # Load deeper representation
    CALL_TOOL = "CALL_TOOL"                    # Execute environment inspection/probe
    ASK_SUPERVISOR = "ASK_SUPERVISOR"          # Intercept loop/drift with higher intelligence
    FORK_HYPOTHESIS = "FORK_HYPOTHESIS"        # Explore competing paths
    VERIFY = "VERIFY"                          # Run test, linters, or assurance checks
    ACT = "ACT"                                # Execute the licensed action
    ABSTAIN = "ABSTAIN"                        # Stop and decline when knowability/evidence is zero
    ESCALATE_HUMAN = "ESCALATE_HUMAN"          # Hand off to GM / operator
    STOP = "STOP"                              # Halt cognitive process


class TerminalState(str, enum.Enum):
    """Terminal state descriptor when STOP or final action is reached."""
    NONE = "NONE"                                            # Not terminal
    STOP_ANSWER = "STOP_ANSWER"                              # Verified contract satisfied
    STOP_ABSTAIN = "STOP_ABSTAIN"                            # Unknowable / insufficient evidence
    STOP_TOOL_REQUIRED = "STOP_TOOL_REQUIRED"                # Blocked on external tool
    STOP_HUMAN_REQUIRED = "STOP_HUMAN_REQUIRED"              # GM approval / mutation gate
    STOP_AUTHORIZATION_DENIED = "STOP_AUTHORIZATION_DENIED"  # Policy or safety gate
    STOP_INFORMATION_UNAVAILABLE = "STOP_INFORMATION_UNAVAILABLE"


class ReasoningValueBucket(str, enum.Enum):
    """Categorization of estimated marginal value."""
    HIGH_POSITIVE = "HIGH_POSITIVE"    # V_r >> 0: High expected gain over cost
    LOW_POSITIVE = "LOW_POSITIVE"      # V_r > 0: Modest expected gain
    MARGINAL_ZERO = "MARGINAL_ZERO"    # V_r ~ 0: Indifferent / plateau reached
    NEGATIVE_WASTE = "NEGATIVE_WASTE"  # V_r < 0: Cognition is burning tokens with no delta


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryCheckpoint:
    """Observable telemetry state at a trajectory decision point."""
    trajectory_id: str
    step_index: int
    task_class: TaskClass = TaskClass.UNKNOWN
    consequence_class: ConsequenceClass = ConsequenceClass.C0_READ_ONLY
    reasoning_tokens_spent: int = 0
    total_tokens_spent: int = 0
    elapsed_seconds: float = 0.0
    cost_spent_usd: Decimal = field(default_factory=lambda: Decimal("0.0000"))
    
    # Progress & constraint signals
    subgoals_total: int = 1
    subgoals_completed: int = 0
    contradictions_count: int = 0
    unresolved_constraints: int = 0
    evidence_items_count: int = 0
    evidence_state: str = "PARTIAL"       # "COMPLETE", "PARTIAL", "EMPTY", "UNKNOWABLE"
    verification_state: str = "NOT_STARTED" # "PASSED", "FAILED", "NOT_STARTED", "PENDING"
    
    # Repetition & loop telemetry
    last_action_fingerprint: str = ""
    action_history: List[str] = field(default_factory=list)
    state_delta: float = 0.5               # 0.0 (no progress) to 1.0 (major breakthrough)
    repeated_conclusions_count: int = 0
    consecutive_zero_delta_steps: int = 0
    
    # Epistemic & contract flags
    is_knowable: bool = True
    output_contract_satisfied: bool = False
    supervisor_anomaly_flag: bool = False
    mutation_gate_hit: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningDecision:
    """Auditable record of a governance decision."""
    decision_id: str
    trajectory_id: str
    timestamp: str
    step_index: int
    configuration_hash: str
    task_class: str
    consequence_class: str
    runtime_state: RuntimeState
    marginal_value_estimate: float
    value_bucket: ReasoningValueBucket
    selected_action: GovernorAction
    terminal_state: TerminalState
    reason_code: str
    rationale: str
    allocated_token_quantum: int = 0
    epistemic_licensed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "trajectory_id": self.trajectory_id,
            "timestamp": self.timestamp,
            "step_index": self.step_index,
            "configuration_hash": self.configuration_hash,
            "task_class": self.task_class,
            "consequence_class": self.consequence_class,
            "runtime_state": self.runtime_state.value,
            "marginal_value_estimate": round(self.marginal_value_estimate, 4),
            "value_bucket": self.value_bucket.value,
            "selected_action": self.selected_action.value,
            "terminal_state": self.terminal_state.value,
            "reason_code": self.reason_code,
            "rationale": self.rationale,
            "allocated_token_quantum": self.allocated_token_quantum,
            "epistemic_licensed": self.epistemic_licensed,
            "metadata": self.metadata,
        }


@dataclass
class ReasoningProfile:
    """Empirically derived reasoning profile for a specific configuration."""
    configuration_hash: str
    model_name: str
    task_class: TaskClass
    consequence_class: ConsequenceClass
    typical_tokens_to_success: int = 2000
    typical_latency_seconds: float = 3.5
    success_rate: float = 0.90
    over_reasoning_rate: float = 0.05
    under_reasoning_rate: float = 0.05
    tool_efficiency: float = 0.85
    verification_efficiency: float = 0.90
    supervision_benefit: float = 0.40
    loop_tendency: float = 0.02
    recommended_token_budget: int = 4000


# ---------------------------------------------------------------------------
# Adaptive Reasoning Governor Core
# ---------------------------------------------------------------------------

class ReasoningGovernor:
    """
    Evaluates trajectory state to buy cognition only while expected marginal verified value > 0.
    """

    def __init__(
        self,
        base_token_quantum: int = 1000,
        max_zero_delta_steps: int = 2,
        loop_repeat_threshold: int = 2,
        high_consequence_verification_hurdle: float = 0.85,
    ):
        self.base_token_quantum = base_token_quantum
        self.max_zero_delta_steps = max_zero_delta_steps
        self.loop_repeat_threshold = loop_repeat_threshold
        self.high_consequence_verification_hurdle = high_consequence_verification_hurdle

    def compute_marginal_value(
        self, checkpoint: TrajectoryCheckpoint, profile: Optional[ReasoningProfile] = None
    ) -> Tuple[float, ReasoningValueBucket, str]:
        """
        Estimates V_r = ExpectedQualityGain - ReasoningCost - LatencyCost - DriftRisk - OpportunityCost.
        Returns (v_r_score, value_bucket, primary_reason).
        """
        # 1. Hard stop on unknowable tasks: information cannot be created from pure thought
        if not checkpoint.is_knowable or checkpoint.evidence_state == "UNKNOWABLE":
            return -1.0, ReasoningValueBucket.NEGATIVE_WASTE, "Task is unknowable from pure reasoning; requires abstention."

        # 2. Output contract already satisfied + verified: marginal value is zero or negative
        if checkpoint.output_contract_satisfied and checkpoint.verification_state == "PASSED":
            return -0.8, ReasoningValueBucket.NEGATIVE_WASTE, "Contract satisfied and verified; further reasoning is wasteful."

        # 3. Repeated zero-delta plateau / loops
        if checkpoint.consecutive_zero_delta_steps >= self.max_zero_delta_steps:
            return -0.6, ReasoningValueBucket.NEGATIVE_WASTE, f"Zero state delta for {checkpoint.consecutive_zero_delta_steps} consecutive steps; cognitive stall detected."

        if checkpoint.repeated_conclusions_count >= self.loop_repeat_threshold:
            return -0.7, ReasoningValueBucket.NEGATIVE_WASTE, "Circular deliberation detected with repeated identical conclusions."

        # 4. Compute Positive Gain Potentials
        quality_gain = 0.0

        # Unresolved contradictions yield high gain from additional reasoning / verification
        if checkpoint.contradictions_count > 0:
            quality_gain += 0.40 * min(3, checkpoint.contradictions_count)

        # Unresolved subgoals / constraints
        subgoal_progress = checkpoint.subgoals_completed / max(1, checkpoint.subgoals_total)
        if subgoal_progress < 1.0:
            quality_gain += 0.35 * (1.0 - subgoal_progress)

        if checkpoint.unresolved_constraints > 0:
            quality_gain += 0.25 * min(4, checkpoint.unresolved_constraints)

        # Consequence weighting: Higher consequence scales up the value of verification/planning
        consequence_mult = 1.0 + (0.25 * int(checkpoint.consequence_class))
        quality_gain *= consequence_mult

        # Failed verification needs reasoning to diagnose
        if checkpoint.verification_state == "FAILED":
            quality_gain += 0.45

        # 5. Compute Costs & Penalties
        # Reasoning cost penalty grows with token consumption relative to task class baseline
        token_penalty = 0.0
        if checkpoint.reasoning_tokens_spent > 8000:
            token_penalty = min(0.60, (checkpoint.reasoning_tokens_spent - 8000) / 10000.0)

        # Drift risk based on action repetitions
        drift_risk = 0.0
        if len(checkpoint.action_history) >= 4:
            recent = checkpoint.action_history[-4:]
            if len(set(recent)) <= 2:
                drift_risk = 0.30

        # Net Marginal Value Calculation
        v_r = quality_gain - token_penalty - drift_risk

        # Clamp and bucket
        v_r = max(-1.0, min(1.0, v_r))

        if v_r >= 0.40:
            bucket = ReasoningValueBucket.HIGH_POSITIVE
            reason = "High positive expected gain: unresolved contradictions or pending subgoals justify cognition."
        elif v_r > 0.05:
            bucket = ReasoningValueBucket.LOW_POSITIVE
            reason = "Modest positive expected gain: bounded cognition licensed for progress."
        elif v_r >= -0.15:
            bucket = ReasoningValueBucket.MARGINAL_ZERO
            reason = "Marginal value plateau: cognition no longer producing clear state advancement."
        else:
            bucket = ReasoningValueBucket.NEGATIVE_WASTE
            reason = "Negative marginal value: high drift risk or redundant computation."

        return v_r, bucket, reason

    def epistemic_check(self, checkpoint: TrajectoryCheckpoint) -> Tuple[bool, str]:
        """
        Epistemic Action Gate:
        Separately answers 'Is current evidence sufficient to license external action?'
        """
        if not checkpoint.is_knowable or checkpoint.evidence_state == "UNKNOWABLE":
            return False, "Evidence is inherently absent/unknowable; action must be ABSTAIN."

        if checkpoint.contradictions_count > 0:
            return False, f"Cannot license action with {checkpoint.contradictions_count} unresolved contradictions."

        if checkpoint.unresolved_constraints > 0:
            return False, f"Cannot license action with {checkpoint.unresolved_constraints} unresolved constraints."

        # High consequence requires explicit verified state
        if checkpoint.consequence_class >= ConsequenceClass.C3_STATEFUL_MUTATION:
            if checkpoint.verification_state != "PASSED":
                return False, f"High consequence ({checkpoint.consequence_class.name}) requires verified state 'PASSED'."

        if checkpoint.evidence_state == "EMPTY":
            return False, "Evidence state is empty; action cannot be licensed without supporting facts."

        return True, "Evidence and invariants satisfy the action contract."

    def evaluate(
        self,
        checkpoint: TrajectoryCheckpoint,
        profile: Optional[ReasoningProfile] = None,
        config_hash: str = "default_config",
    ) -> ReasoningDecision:
        """
        Evaluates the trajectory checkpoint and returns an auditable ReasoningDecision.
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        
        v_r, bucket, val_reason = self.compute_marginal_value(checkpoint, profile)
        epistemic_ok, epistemic_reason = self.epistemic_check(checkpoint)

        # -------------------------------------------------------------------
        # Rule 1: Unknowable task / Information unavailable -> STOP + ABSTAIN
        # -------------------------------------------------------------------
        if not checkpoint.is_knowable or checkpoint.evidence_state == "UNKNOWABLE":
            return ReasoningDecision(
                decision_id=decision_id,
                trajectory_id=checkpoint.trajectory_id,
                timestamp=now_iso,
                step_index=checkpoint.step_index,
                configuration_hash=config_hash,
                task_class=checkpoint.task_class.value,
                consequence_class=checkpoint.consequence_class.name,
                runtime_state=RuntimeState.ADEQUATE_REASONING,
                marginal_value_estimate=v_r,
                value_bucket=bucket,
                selected_action=GovernorAction.ABSTAIN,
                terminal_state=TerminalState.STOP_ABSTAIN,
                reason_code="EPISTEMIC_ABSTAIN_UNKNOWABLE",
                rationale="Task is unverifiable/unknowable. Reasoning Governor halts expenditure; Epistemic Gate enforces abstention over hallucination.",
                allocated_token_quantum=0,
                epistemic_licensed=False,
            )

        # -------------------------------------------------------------------
        # Rule 2: Mutation gate hit -> STOP + HUMAN_REQUIRED
        # -------------------------------------------------------------------
        if checkpoint.mutation_gate_hit:
            return ReasoningDecision(
                decision_id=decision_id,
                trajectory_id=checkpoint.trajectory_id,
                timestamp=now_iso,
                step_index=checkpoint.step_index,
                configuration_hash=config_hash,
                task_class=checkpoint.task_class.value,
                consequence_class=checkpoint.consequence_class.name,
                runtime_state=RuntimeState.ADEQUATE_REASONING,
                marginal_value_estimate=0.0,
                value_bucket=ReasoningValueBucket.MARGINAL_ZERO,
                selected_action=GovernorAction.ESCALATE_HUMAN,
                terminal_state=TerminalState.STOP_HUMAN_REQUIRED,
                reason_code="MUTATION_GATE_HIT",
                rationale="Action crossed operational mutation gate; escalating to operator for approval.",
                allocated_token_quantum=0,
                epistemic_licensed=False,
            )

        # -------------------------------------------------------------------
        # Rule 3: Loop / Stall / Over-reasoning detection -> ASK_SUPERVISOR or STEER
        # -------------------------------------------------------------------
        is_loop = (
            checkpoint.consecutive_zero_delta_steps >= self.max_zero_delta_steps
            or checkpoint.repeated_conclusions_count >= self.loop_repeat_threshold
            or checkpoint.supervisor_anomaly_flag
        )

        if is_loop and not (checkpoint.output_contract_satisfied and epistemic_ok):
            return ReasoningDecision(
                decision_id=decision_id,
                trajectory_id=checkpoint.trajectory_id,
                timestamp=now_iso,
                step_index=checkpoint.step_index,
                configuration_hash=config_hash,
                task_class=checkpoint.task_class.value,
                consequence_class=checkpoint.consequence_class.name,
                runtime_state=RuntimeState.OVER_REASONING,
                marginal_value_estimate=v_r,
                value_bucket=bucket,
                selected_action=GovernorAction.ASK_SUPERVISOR,
                terminal_state=TerminalState.NONE,
                reason_code="OVER_REASONING_INTERCEPT",
                rationale="Loop or cognitive plateau detected. Activating supervisor to steer or break deadlocks.",
                allocated_token_quantum=0,
                epistemic_licensed=False,
            )

        # -------------------------------------------------------------------
        # Rule 4: Contract Satisfied & Epistemic Gate Passed -> STOP + ANSWER / ACT
        # -------------------------------------------------------------------
        if checkpoint.output_contract_satisfied:
            if epistemic_ok:
                action = GovernorAction.ACT if checkpoint.consequence_class >= ConsequenceClass.C1_REVERSIBLE_LOCAL else GovernorAction.STOP
                terminal = TerminalState.STOP_ANSWER
                return ReasoningDecision(
                    decision_id=decision_id,
                    trajectory_id=checkpoint.trajectory_id,
                    timestamp=now_iso,
                    step_index=checkpoint.step_index,
                    configuration_hash=config_hash,
                    task_class=checkpoint.task_class.value,
                    consequence_class=checkpoint.consequence_class.name,
                    runtime_state=RuntimeState.ADEQUATE_REASONING,
                    marginal_value_estimate=v_r,
                    value_bucket=bucket,
                    selected_action=action,
                    terminal_state=terminal,
                    reason_code="CONTRACT_SATISFIED_VERIFIED",
                    rationale="Output contract satisfied and verified. Adequate reasoning achieved; halting cognition.",
                    allocated_token_quantum=0,
                    epistemic_licensed=True,
                )
            else:
                # Agent thinks it is done, but verification/epistemic invariants failed (Under-reasoning)
                return ReasoningDecision(
                    decision_id=decision_id,
                    trajectory_id=checkpoint.trajectory_id,
                    timestamp=now_iso,
                    step_index=checkpoint.step_index,
                    configuration_hash=config_hash,
                    task_class=checkpoint.task_class.value,
                    consequence_class=checkpoint.consequence_class.name,
                    runtime_state=RuntimeState.UNDER_REASONING,
                    marginal_value_estimate=0.50,
                    value_bucket=ReasoningValueBucket.HIGH_POSITIVE,
                    selected_action=GovernorAction.VERIFY,
                    terminal_state=TerminalState.NONE,
                    reason_code="PREMATURE_STOP_BLOCKED",
                    rationale=f"Premature stop prevented: contract claimed satisfied but {epistemic_reason}. Steering to VERIFY.",
                    allocated_token_quantum=self.base_token_quantum,
                    epistemic_licensed=False,
                )

        # -------------------------------------------------------------------
        # Rule 5: Verification Failed -> VERIFY / CONTINUE_REASONING
        # -------------------------------------------------------------------
        if checkpoint.verification_state == "FAILED":
            return ReasoningDecision(
                decision_id=decision_id,
                trajectory_id=checkpoint.trajectory_id,
                timestamp=now_iso,
                step_index=checkpoint.step_index,
                configuration_hash=config_hash,
                task_class=checkpoint.task_class.value,
                consequence_class=checkpoint.consequence_class.name,
                runtime_state=RuntimeState.UNDER_REASONING,
                marginal_value_estimate=max(0.70, v_r),
                value_bucket=ReasoningValueBucket.HIGH_POSITIVE,
                selected_action=GovernorAction.CONTINUE_REASONING,
                terminal_state=TerminalState.NONE,
                reason_code="VERIFICATION_FAILURE_DIAGNOSIS",
                rationale="Test/check failure detected. Allocating cognitive quantum for root cause diagnosis.",
                allocated_token_quantum=int(self.base_token_quantum * 1.5),
                epistemic_licensed=False,
            )

        # -------------------------------------------------------------------
        # Rule 6: Evidence Missing -> RETRIEVE_MEMORY or HYDRATE_EVIDENCE
        # -------------------------------------------------------------------
        if checkpoint.evidence_state in ("EMPTY", "PARTIAL") and checkpoint.evidence_items_count == 0:
            quantum = self.base_token_quantum
            if checkpoint.consequence_class >= ConsequenceClass.C3_STATEFUL_MUTATION:
                quantum = int(quantum * 1.5)
            return ReasoningDecision(
                decision_id=decision_id,
                trajectory_id=checkpoint.trajectory_id,
                timestamp=now_iso,
                step_index=checkpoint.step_index,
                configuration_hash=config_hash,
                task_class=checkpoint.task_class.value,
                consequence_class=checkpoint.consequence_class.name,
                runtime_state=RuntimeState.UNDER_REASONING,
                marginal_value_estimate=v_r,
                value_bucket=bucket if bucket != ReasoningValueBucket.NEGATIVE_WASTE else ReasoningValueBucket.HIGH_POSITIVE,
                selected_action=GovernorAction.RETRIEVE_MEMORY,
                terminal_state=TerminalState.NONE,
                reason_code="EVIDENCE_RETRIEVAL_REQUIRED",
                rationale="Missing critical factual foundation. Directing recall/retrieval before deep deliberation.",
                allocated_token_quantum=quantum,
                epistemic_licensed=False,
            )

        # -------------------------------------------------------------------
        # Rule 7: Positive Marginal Value -> Allocate Cognition Quantum
        # -------------------------------------------------------------------
        if bucket in (ReasoningValueBucket.HIGH_POSITIVE, ReasoningValueBucket.LOW_POSITIVE):
            quantum = self.base_token_quantum
            if checkpoint.consequence_class >= ConsequenceClass.C3_STATEFUL_MUTATION:
                quantum = int(quantum * 1.5)
            
            action = GovernorAction.CONTINUE_REASONING
            if checkpoint.unresolved_constraints > 0 and checkpoint.step_index > 3:
                action = GovernorAction.CALL_TOOL

            return ReasoningDecision(
                decision_id=decision_id,
                trajectory_id=checkpoint.trajectory_id,
                timestamp=now_iso,
                step_index=checkpoint.step_index,
                configuration_hash=config_hash,
                task_class=checkpoint.task_class.value,
                consequence_class=checkpoint.consequence_class.name,
                runtime_state=RuntimeState.ADEQUATE_REASONING,
                marginal_value_estimate=v_r,
                value_bucket=bucket,
                selected_action=action,
                terminal_state=TerminalState.NONE,
                reason_code="MARGINAL_COGNITION_PURCHASED",
                rationale=val_reason,
                allocated_token_quantum=quantum,
                epistemic_licensed=False,
            )

        # -------------------------------------------------------------------
        # Rule 8: Marginal Zero / Negative -> Plateau reached
        # -------------------------------------------------------------------
        return ReasoningDecision(
            decision_id=decision_id,
            trajectory_id=checkpoint.trajectory_id,
            timestamp=now_iso,
            step_index=checkpoint.step_index,
            configuration_hash=config_hash,
            task_class=checkpoint.task_class.value,
            consequence_class=checkpoint.consequence_class.name,
            runtime_state=RuntimeState.OVER_REASONING,
            marginal_value_estimate=v_r,
            value_bucket=bucket,
            selected_action=GovernorAction.STOP,
            terminal_state=TerminalState.STOP_ANSWER if epistemic_ok else TerminalState.STOP_ABSTAIN,
            reason_code="MARGINAL_VALUE_COLLAPSE",
            rationale="Cognitive gains have plateaued. Halting further reasoning expenditure.",
            allocated_token_quantum=0,
            epistemic_licensed=epistemic_ok,
        )


# ---------------------------------------------------------------------------
# Cognitive Yield & Metabolic Efficiency Telemetry
# ---------------------------------------------------------------------------

@dataclass
class CognitiveYieldMetrics:
    """Calculates metabolic and outcome efficiency over trajectory decisions."""
    total_decisions: int
    total_reasoning_tokens: int
    total_tokens: int
    total_cost_usd: Decimal
    verified_success: bool
    runtime_state_counts: Dict[str, int]
    actions_counts: Dict[str, int]
    
    # Efficiency Indicators
    verified_success_per_dollar: float
    verified_success_per_1m_tokens: float
    reasoning_waste_ratio: float
    premature_stops_prevented: int
    loops_prevented: int
    abstention_accuracy: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "total_reasoning_tokens": self.total_reasoning_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": str(self.total_cost_usd),
            "verified_success": self.verified_success,
            "runtime_state_counts": self.runtime_state_counts,
            "actions_counts": self.actions_counts,
            "verified_success_per_dollar": round(self.verified_success_per_dollar, 4),
            "verified_success_per_1m_tokens": round(self.verified_success_per_1m_tokens, 4),
            "reasoning_waste_ratio": round(self.reasoning_waste_ratio, 4),
            "premature_stops_prevented": self.premature_stops_prevented,
            "loops_prevented": self.loops_prevented,
            "abstention_accuracy": round(self.abstention_accuracy, 4),
        }


def compute_cognitive_yield(
    decisions: List[ReasoningDecision],
    final_success: bool,
    total_tokens: int,
    reasoning_tokens: int,
    total_cost_usd: Decimal,
    is_knowable: bool = True,
) -> CognitiveYieldMetrics:
    """
    Computes metabolic efficiency metrics over a set of reasoning decisions.
    """
    state_counts = {s.value: 0 for s in RuntimeState}
    action_counts = {a.value: 0 for a in GovernorAction}
    premature_stops = 0
    loops = 0
    waste_decisions = 0
    correct_abstentions = 0

    for d in decisions:
        state_counts[d.runtime_state.value] = state_counts.get(d.runtime_state.value, 0) + 1
        action_counts[d.selected_action.value] = action_counts.get(d.selected_action.value, 0) + 1

        if d.reason_code == "PREMATURE_STOP_BLOCKED":
            premature_stops += 1
        if d.reason_code == "OVER_REASONING_INTERCEPT":
            loops += 1
        if d.runtime_state == RuntimeState.OVER_REASONING or d.value_bucket == ReasoningValueBucket.NEGATIVE_WASTE:
            waste_decisions += 1
        if not is_knowable and d.selected_action == GovernorAction.ABSTAIN:
            correct_abstentions += 1

    total_d = max(1, len(decisions))
    waste_ratio = waste_decisions / total_d

    # Success per dollar
    cost_float = float(total_cost_usd) if total_cost_usd > Decimal("0") else 0.0001
    succ_per_dollar = (1.0 if final_success else 0.0) / cost_float

    # Success per 1M tokens
    tok_m = max(1, total_tokens) / 1_000_000.0
    succ_per_1m = (1.0 if final_success else 0.0) / tok_m

    abstention_acc = 1.0 if (not is_knowable and correct_abstentions > 0) else (1.0 if is_knowable else 0.0)

    return CognitiveYieldMetrics(
        total_decisions=len(decisions),
        total_reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN),
        verified_success=final_success,
        runtime_state_counts=state_counts,
        actions_counts=action_counts,
        verified_success_per_dollar=succ_per_dollar,
        verified_success_per_1m_tokens=succ_per_1m,
        reasoning_waste_ratio=waste_ratio,
        premature_stops_prevented=premature_stops,
        loops_prevented=loops,
        abstention_accuracy=abstention_acc,
    )
