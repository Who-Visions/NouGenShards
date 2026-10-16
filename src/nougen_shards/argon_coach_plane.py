"""Argon Head Coach Control Plane & 99.99% Free-Swarm Execution Router.

Implements the explicit split between the 0.01% Strategic Control Plane
(Antigravity Argon) and the 99.99% Zero-Cost Execution Plane (Ollama on
Phoebus/Blade, Cloudflare Workers AI, and OpenRouter free lanes).

Invariants:
1. BudgetGovernor mathematically enforces the >=99.5%–99.99% free-lane ratio.
2. Argon never ingests raw repository dumps; it receives only a bounded
   Minimum Sufficient Truth (MST) projection with a deterministic SHA-256
   lineage fingerprint.
3. Argon emits a formal GamePlanDAG where every PlayStep carries a shell
   verification gate.
4. Local workers execute steps with bounded self-healing retries; Iris
   (gemma4:e2b-qat) diagnoses fumbles locally before Argon is ever re-summoned.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple


class LaneTier(str, Enum):
    HEAD_COACH_ARGON = "antigravity:argon"          # 0.01% Control & Architecture Plane
    LOCAL_KAEDRA = "phoebus:ollama:kaedracode"      # $0.00 Heavy Local Code & Draft
    LOCAL_IRIS = "local:ollama:gemma4:e2b-qat"      # $0.00 Assurance & Evidence Verification
    LOCAL_DAV1D = "blade:ollama:dav1d:e2b"          # $0.00 Stadium Anchor & CLI Triage
    EDGE_CF_AI = "cloudflare:qwen3-30b-a3b-fp8"     # $0.00 Zero-VRAM Fast Edge Synthesis
    FREE_OPENROUTER = "openrouter:free-router"      # $0.00 High-Context Cloud Fallback


@dataclass(frozen=True)
class PlayStep:
    step_id: str
    assigned_lane: LaneTier
    target_files: List[str]
    objective: str
    prompt_template: str
    verification_cmd: str
    timeout_s: int = 90
    max_local_retries: int = 3
    depends_on: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GamePlanDAG:
    plan_id: str
    goal: str
    lineage_fingerprint: str
    invariants: List[str]
    steps: List[PlayStep]
    rollback_strategy: str
    created_utc: float

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for s in data["steps"]:
            if isinstance(s.get("assigned_lane"), LaneTier):
                s["assigned_lane"] = s["assigned_lane"].value
        return data


class BudgetGovernor:
    """Enforces the 99.99% free/local routing rule across rolling token and invocation windows."""

    def __init__(self, max_argon_invocation_ratio: float = 0.005, hard_floor_free_calls: int = 200):
        self.max_argon_ratio = max_argon_invocation_ratio
        self.hard_floor_free_calls = hard_floor_free_calls
        self.total_invocations = 0
        self.argon_invocations = 0
        self.total_tokens_free = 0
        self.total_tokens_argon = 0

    def record_call(self, lane: LaneTier, tokens_used: int) -> None:
        tokens = max(0, int(tokens_used))
        self.total_invocations += 1
        if lane == LaneTier.HEAD_COACH_ARGON:
            self.argon_invocations += 1
            self.total_tokens_argon += tokens
        else:
            self.total_tokens_free += tokens

    @property
    def free_token_ratio(self) -> float:
        total = self.total_tokens_free + self.total_tokens_argon
        if total == 0:
            return 1.0
        return self.total_tokens_free / total

    @property
    def free_invocation_ratio(self) -> float:
        if self.total_invocations == 0:
            return 1.0
        return (self.total_invocations - self.argon_invocations) / self.total_invocations

    def can_summon_coach(
        self,
        complexity_score: float,
        is_architectural_fork: bool,
        local_fumble_count: int,
    ) -> Tuple[bool, str]:
        if is_architectural_fork:
            return True, "ARCHITECTURAL_FORK_OVERRIDE"
        if local_fumble_count >= 3:
            return True, "LOCAL_QB_FUMBLE_ESCALATION"
        if self.total_invocations >= self.hard_floor_free_calls:
            current_argon_ratio = self.argon_invocations / max(1, self.total_invocations)
            if current_argon_ratio >= self.max_argon_ratio and complexity_score < 0.92:
                return False, f"BUDGET_CAP_ACTIVE (argon_ratio={current_argon_ratio:.5f})"
        if complexity_score >= 0.85:
            return True, "HIGH_COMPLEXITY_WARGAME"
        return False, "ROUTED_TO_FREE_SWARM"


def _strip_json_fences(raw: str) -> str:
    """Strips optional markdown code fences from model JSON output."""
    text = raw.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


class ArgonHeadCoach:
    """
    The 0.01% Strategic Brain on Antigravity.
    Consumes only bounded Minimum Sufficient Truth (MST) envelopes and outputs deterministic GamePlanDAGs.
    """

    def __init__(
        self,
        governor: BudgetGovernor,
        argon_dispatch_fn: Callable[[str, str], Tuple[str, int]],
        worker_dispatch_fn: Callable[[LaneTier, str], Tuple[str, int]],
        sandbox_verify_fn: Callable[[str, int], Tuple[int, str]],
        shard_capture_fn: Callable[[str, str, List[str]], None],
    ):
        self.governor = governor
        self._call_argon = argon_dispatch_fn
        self._call_worker = worker_dispatch_fn
        self._verify_sandbox = sandbox_verify_fn
        self._capture_shard = shard_capture_fn

    def build_mst_projection(
        self,
        goal: str,
        shard_snippets: List[Dict[str, Any]],
        ast_skeletons: Dict[str, str],
        active_claims: List[str],
        max_chars: int = 12000,
    ) -> Tuple[str, str]:
        """Compresses live fleet state into a strict token-bounded packet with a replay hash."""
        ranked_shards = sorted(
            shard_snippets,
            key=lambda s: float(s.get("density_score", 0.5)) * float(s.get("utility_score", 0.5)),
            reverse=True,
        )[:8]

        packet = {
            "mission_goal": goal,
            "active_lane_claims": active_claims,
            "ast_signatures": {k: v[:1200] for k, v in ast_skeletons.items()},
            "high_density_shards": [
                {
                    "id": s.get("id"),
                    "db": s.get("_db_index"),
                    "title": s.get("title"),
                    "summary": str(s.get("content", ""))[:450],
                }
                for s in ranked_shards
            ],
        }
        serialized = json.dumps(packet, sort_keys=True, separators=(",", ":"))
        if len(serialized) > max_chars:
            serialized = serialized[:max_chars]
        lineage_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return serialized, lineage_hash

    def draft_playbook(self, goal: str, mst_packet: str, lineage_hash: str) -> GamePlanDAG:
        """Invokes Argon once to war-game the entire end-to-end execution DAG."""
        system_spec = (
            "You are the NouGen Head Coach running on Antigravity Argon. "
            "Emit ONLY valid JSON matching the GamePlanDAG schema. "
            "Assign all coding, drafting, and testing steps to local/free lanes: "
            "'phoebus:ollama:kaedracode', 'local:ollama:gemma4:e2b-qat', "
            "'blade:ollama:dav1d:e2b', 'cloudflare:qwen3-30b-a3b-fp8', or 'openrouter:free-router'. "
            "Every step MUST include a deterministic shell verification_cmd."
        )
        raw_json, tokens = self._call_argon(system_spec, mst_packet)
        self.governor.record_call(LaneTier.HEAD_COACH_ARGON, tokens)
        payload = json.loads(_strip_json_fences(raw_json))

        steps: List[PlayStep] = []
        for s in payload.get("steps", []):
            lane = LaneTier(s["assigned_lane"])
            if lane == LaneTier.HEAD_COACH_ARGON:
                raise ValueError(
                    f"Step {s.get('step_id')} illegally assigned to {lane.value}; "
                    "Argon is strictly Control Plane and cannot run field plays."
                )
            steps.append(
                PlayStep(
                    step_id=s["step_id"],
                    assigned_lane=lane,
                    target_files=list(s.get("target_files", [])),
                    objective=s["objective"],
                    prompt_template=s["prompt_template"],
                    verification_cmd=s["verification_cmd"],
                    timeout_s=int(s.get("timeout_s", 90)),
                    max_local_retries=int(s.get("max_local_retries", 3)),
                    depends_on=list(s.get("depends_on", [])),
                )
            )

        return GamePlanDAG(
            plan_id=f"playbook_{lineage_hash}_{int(time.time())}",
            goal=goal,
            lineage_fingerprint=lineage_hash,
            invariants=list(payload.get("invariants", [])),
            steps=steps,
            rollback_strategy=payload.get("rollback_strategy", "git checkout -- ."),
            created_utc=time.time(),
        )

    def execute_playbook(self, dag: GamePlanDAG) -> Dict[str, Any]:
        """Executes the DAG across the 99.99% free swarm with self-healing local retry loops."""
        completed: Dict[str, str] = {}
        telemetry: List[Dict[str, Any]] = []

        for step in dag.steps:
            for dep in step.depends_on:
                if dep not in completed:
                    raise RuntimeError(f"Step {step.step_id} blocked: dependency {dep} did not complete.")

            attempt = 0
            step_passed = False
            last_error = ""

            while attempt < step.max_local_retries and not step_passed:
                attempt += 1
                contextualized_prompt = step.prompt_template
                if last_error:
                    contextualized_prompt += (
                        f"\n\n[PREVIOUS_ATTEMPT_STDERR]:\n{last_error[:1500]}\n"
                        f"Fix the fault while preserving invariants: {dag.invariants}"
                    )

                worker_output, tokens = self._call_worker(step.assigned_lane, contextualized_prompt)
                self.governor.record_call(step.assigned_lane, tokens)

                exit_code, verify_log = self._verify_sandbox(step.verification_cmd, step.timeout_s)
                telemetry.append({
                    "step_id": step.step_id,
                    "lane": step.assigned_lane.value,
                    "attempt": attempt,
                    "tokens": tokens,
                    "exit_code": exit_code,
                })

                if exit_code == 0:
                    step_passed = True
                    completed[step.step_id] = worker_output
                else:
                    last_error = verify_log

            if not step_passed:
                # Escalate to Iris for local assurance diagnosis before touching Argon
                iris_diag, iris_tokens = self._call_worker(
                    LaneTier.LOCAL_IRIS,
                    f"Diagnose why step {step.step_id} failed verification `{step.verification_cmd}`:\n{last_error[:2000]}",
                )
                self.governor.record_call(LaneTier.LOCAL_IRIS, iris_tokens)
                return {
                    "status": "FUMBLE_HALTED",
                    "failed_step": step.step_id,
                    "iris_diagnosis": iris_diag,
                    "free_token_ratio": self.governor.free_token_ratio,
                    "telemetry": telemetry,
                }

        # Distill the victory into a permanent high-density shard
        self._capture_shard(
            f"Verified Playbook Execution: {dag.goal[:80]}",
            json.dumps({
                "plan_id": dag.plan_id,
                "lineage": dag.lineage_fingerprint,
                "free_token_ratio": round(self.governor.free_token_ratio, 6),
                "steps_completed": list(completed.keys()),
            }),
            ["argon_coach", "verified_playbook", "zero_cost_swarm"],
        )

        return {
            "status": "TOUCHDOWN",
            "plan_id": dag.plan_id,
            "free_token_ratio": self.governor.free_token_ratio,
            "telemetry": telemetry,
        }
