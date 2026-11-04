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
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


def _env_num(name: str, default: float) -> float:
    """A tunable from the environment, with the constant as a fallback only (Rule 0.2)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _lane(name: str, default: str) -> str:
    return os.environ.get(f"NOUGEN_LANE_{name}", "").strip() or default


# The Argon models the Antigravity CLI serves, by reasoning tier (`agy models`, 2026-11-04).
ARGON_TIERS = ("low", "medium", "high")
ARGON_MODEL_PREFIX = os.environ.get("NOUGEN_ARGON_MODEL_PREFIX", "gemini-4-argon-")


def resolve_argon_model(complexity_score: Optional[float] = None, served: Optional[List[str]] = None) -> str:
    """The concrete Argon model ID to dispatch to.

    NOUGEN_ARGON_MODEL pins it. Otherwise the tier follows the work: high for war-game-grade
    complexity, medium by default, low for light planning. When `served` (for example the
    output of `agy models`) is given, a tier it does not list falls back to the nearest one it does.
    """
    pinned = os.environ.get("NOUGEN_ARGON_MODEL", "").strip()
    if pinned:
        return pinned
    hi = _env_num("NOUGEN_ARGON_HIGH_AT", 0.85)
    lo = _env_num("NOUGEN_ARGON_LOW_BELOW", 0.4)
    if complexity_score is None:
        tier = "medium"
    elif complexity_score >= hi:
        tier = "high"
    elif complexity_score < lo:
        tier = "low"
    else:
        tier = "medium"
    want = f"{ARGON_MODEL_PREFIX}{tier}"
    if served:
        order = {"high": ["high", "medium", "low"], "medium": ["medium", "high", "low"], "low": ["low", "medium", "high"]}[tier]
        for t in order:
            if f"{ARGON_MODEL_PREFIX}{t}" in served:
                return f"{ARGON_MODEL_PREFIX}{t}"
    return want


class LaneTier(str, Enum):
    # Routing keys, not model tags: each is overridable with NOUGEN_LANE_<NAME> so a fleet that
    # serves a different model on a node can repoint the lane without a code change. The Argon
    # control plane's concrete model is resolved per call by resolve_argon_model().
    HEAD_COACH_ARGON = _lane("HEAD_COACH_ARGON", "antigravity:argon")        # 0.01% Control & Architecture Plane
    LOCAL_KAEDRA = _lane("LOCAL_KAEDRA", "phoebus:ollama:kaedracode")        # $0.00 Heavy Local Code & Draft
    LOCAL_IRIS = _lane("LOCAL_IRIS", "local:ollama:gemma4:e2b-qat")          # $0.00 Assurance & Evidence Verification
    LOCAL_DAV1D = _lane("LOCAL_DAV1D", "blade:ollama:dav1d:e2b")             # $0.00 Stadium Anchor & CLI Triage
    EDGE_CF_AI = _lane("EDGE_CF_AI", "cloudflare:qwen3-30b-a3b-fp8")         # $0.00 Zero-VRAM Fast Edge Synthesis
    FREE_OPENROUTER = _lane("FREE_OPENROUTER", "openrouter:free-router")     # $0.00 High-Context Cloud Fallback


FIELD_LANES = [lane for lane in LaneTier if lane is not LaneTier.HEAD_COACH_ARGON]
DEFAULT_TIMEOUT_S = int(_env_num("NOUGEN_PLAY_TIMEOUT_S", 90))
DEFAULT_RETRIES = int(_env_num("NOUGEN_PLAY_RETRIES", 3))
TIMEOUT_EXIT = 124  # what `timeout` returns, so a hung check reads as a timeout, not a test failure


@dataclass(frozen=True)
class PlayStep:
    step_id: str
    assigned_lane: LaneTier
    target_files: List[str]
    objective: str
    prompt_template: str
    verification_cmd: str
    timeout_s: int = DEFAULT_TIMEOUT_S
    max_local_retries: int = DEFAULT_RETRIES
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
    argon_model: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for s in data["steps"]:
            if isinstance(s.get("assigned_lane"), LaneTier):
                s["assigned_lane"] = s["assigned_lane"].value
        return data


class BudgetGovernor:
    """Enforces the 99.99% free/local routing rule across rolling token and invocation windows."""

    def __init__(
        self,
        max_argon_invocation_ratio: Optional[float] = None,
        hard_floor_free_calls: Optional[int] = None,
        min_free_token_ratio: Optional[float] = None,
        warmup_argon_calls: Optional[int] = None,
    ):
        def pick(value, env, default):
            return value if value is not None else _env_num(env, default)

        self.max_argon_ratio = pick(max_argon_invocation_ratio, "NOUGEN_ARGON_MAX_RATIO", 0.005)
        self.hard_floor_free_calls = int(pick(hard_floor_free_calls, "NOUGEN_ARGON_FLOOR_CALLS", 200))
        # Tokens count too: a few huge Argon calls can blow the budget while the call ratio looks fine.
        self.min_free_token_ratio = pick(min_free_token_ratio, "NOUGEN_ARGON_MIN_FREE_TOKENS", 0.995)
        # Before the floor is reached the call ratio means little, so only this many Argon calls are allowed.
        self.warmup_argon_calls = int(pick(warmup_argon_calls, "NOUGEN_ARGON_WARMUP_CALLS", 2))
        self.fumble_escalate_at = int(_env_num("NOUGEN_ARGON_FUMBLE_AT", 3))
        self.override_complexity = _env_num("NOUGEN_ARGON_OVERRIDE_AT", 0.92)
        self.wargame_complexity = _env_num("NOUGEN_ARGON_WARGAME_AT", 0.85)
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
        if local_fumble_count >= self.fumble_escalate_at:
            return True, "LOCAL_QB_FUMBLE_ESCALATION"
        if complexity_score < self.override_complexity:
            if self.total_invocations >= self.hard_floor_free_calls:
                current_argon_ratio = self.argon_invocations / max(1, self.total_invocations)
                if current_argon_ratio >= self.max_argon_ratio:
                    return False, f"BUDGET_CAP_ACTIVE (argon_ratio={current_argon_ratio:.5f})"
            elif self.argon_invocations >= self.warmup_argon_calls:
                return False, (
                    f"BUDGET_WARMUP_CAP ({self.argon_invocations}/{self.warmup_argon_calls} Argon calls "
                    f"before {self.hard_floor_free_calls} total)"
                )
            if self.free_token_ratio < self.min_free_token_ratio:
                return False, f"TOKEN_BUDGET_CAP (free_token_ratio={self.free_token_ratio:.5f})"
        if complexity_score >= self.wargame_complexity:
            return True, "HIGH_COMPLEXITY_WARGAME"
        return False, "ROUTED_TO_FREE_SWARM"


def _strip_json_fences(raw: str) -> str:
    """The JSON object in a model reply: inside a code fence, after prose, or bare."""
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if not text.startswith("{") and "{" in text and "}" in text:
        return text[text.index("{"): text.rindex("}") + 1]
    return text


def _tail(text: str, n: int) -> str:
    """The last n characters: a traceback's useful part is at the end, not in the log header."""
    text = text or ""
    return text if len(text) <= n else "..." + text[-n:]


def _topological(steps: List["PlayStep"]) -> List["PlayStep"]:
    """Steps in dependency order (stable for ties). Raises on an unknown dependency or a cycle."""
    by_id = {s.step_id: s for s in steps}
    for s in steps:
        for dep in s.depends_on:
            if dep not in by_id:
                raise RuntimeError(f"Step {s.step_id} blocked: dependency {dep} is not in the plan.")
    ordered: List[PlayStep] = []
    state: Dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(s: PlayStep) -> None:
        mark = state.get(s.step_id)
        if mark == 2:
            return
        if mark == 1:
            raise RuntimeError(f"Plan has a dependency cycle through step {s.step_id}.")
        state[s.step_id] = 1
        for dep in s.depends_on:
            visit(by_id[dep])
        state[s.step_id] = 2
        ordered.append(s)

    for s in steps:
        visit(s)
    return ordered


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
        def dump(p: Dict[str, Any]) -> str:
            return json.dumps(p, sort_keys=True, separators=(",", ":"))

        serialized = dump(packet)
        # Over budget: drop the lowest-ranked shards, then shorten AST signatures, so the packet
        # always stays valid JSON (a raw character cut would break it mid-string).
        while len(serialized) > max_chars and packet["high_density_shards"]:
            packet["high_density_shards"].pop()
            serialized = dump(packet)
        budget = 1200
        while len(serialized) > max_chars and budget > 80 and packet["ast_signatures"]:
            budget //= 2
            packet["ast_signatures"] = {k: v[:budget] for k, v in ast_skeletons.items()}
            serialized = dump(packet)
        if len(serialized) > max_chars:
            packet["ast_signatures"] = {}
            packet["mission_goal"] = goal[: max(0, max_chars // 2)]
            serialized = dump(packet)
        lineage_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return serialized, lineage_hash

    def draft_playbook(
        self,
        goal: str,
        mst_packet: str,
        lineage_hash: str,
        complexity_score: float = 1.0,
        is_architectural_fork: bool = False,
        local_fumble_count: int = 0,
        served_models: Optional[List[str]] = None,
    ) -> GamePlanDAG:
        """Invokes Argon once to war-game the entire end-to-end execution DAG.

        The budget governor is asked first; a refusal raises PermissionError instead of calling Argon.
        """
        allowed, reason = self.governor.can_summon_coach(complexity_score, is_architectural_fork, local_fumble_count)
        if not allowed:
            raise PermissionError(f"Argon not summoned: {reason}")
        model = resolve_argon_model(complexity_score, served_models)
        lanes = ", ".join(f"'{lane.value}'" for lane in FIELD_LANES)
        system_spec = (
            f"You are the NouGen Head Coach running on Antigravity Argon ({model}). "
            "Emit ONLY valid JSON matching the GamePlanDAG schema. "
            f"Assign all coding, drafting, and testing steps to local/free lanes: {lanes}. "
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
            verify = str(s.get("verification_cmd") or "").strip()
            if not verify:
                # An empty check exits 0 and would "pass" anything.
                raise ValueError(f"Step {s.get('step_id')} has no verification_cmd; every play needs a real gate.")
            timeout_s = int(s.get("timeout_s", DEFAULT_TIMEOUT_S) or 0)
            retries = int(s.get("max_local_retries", DEFAULT_RETRIES) or 0)
            steps.append(
                PlayStep(
                    step_id=s["step_id"],
                    assigned_lane=lane,
                    target_files=list(s.get("target_files", [])),
                    objective=s["objective"],
                    prompt_template=s["prompt_template"],
                    verification_cmd=verify,
                    timeout_s=timeout_s if timeout_s > 0 else DEFAULT_TIMEOUT_S,
                    max_local_retries=retries if retries > 0 else DEFAULT_RETRIES,
                    depends_on=list(s.get("depends_on", [])),
                )
            )
        _topological(steps)  # reject unknown dependencies and cycles at draft time

        return GamePlanDAG(
            plan_id=f"playbook_{lineage_hash}_{int(time.time())}",
            goal=goal,
            lineage_fingerprint=lineage_hash,
            invariants=list(payload.get("invariants", [])),
            steps=steps,
            rollback_strategy=payload.get("rollback_strategy", "git checkout -- ."),
            created_utc=time.time(),
            argon_model=model,
        )

    def _verify(self, cmd: str, timeout_s: int) -> Tuple[int, str]:
        """The sandbox gate, never raising: a hung or unrunnable check becomes a failed attempt."""
        try:
            return self._verify_sandbox(cmd, timeout_s)
        except subprocess.TimeoutExpired as e:
            return TIMEOUT_EXIT, f"TIMEOUT after {timeout_s}s: {cmd}\n{_tail(str(e.output or ''), 1500)}"
        except (OSError, ValueError, RuntimeError) as e:
            return 127, f"VERIFY_ERROR {type(e).__name__}: {e}"

    def execute_playbook(self, dag: GamePlanDAG) -> Dict[str, Any]:
        """Executes the DAG across the 99.99% free swarm with self-healing local retry loops."""
        completed: Dict[str, str] = {}
        telemetry: List[Dict[str, Any]] = []

        for step in _topological(dag.steps):

            attempt = 0
            step_passed = False
            last_error = ""

            while attempt < step.max_local_retries and not step_passed:
                attempt += 1
                contextualized_prompt = step.prompt_template
                if last_error:
                    contextualized_prompt += (
                        f"\n\n[PREVIOUS_ATTEMPT_STDERR]:\n{_tail(last_error, 1500)}\n"
                        f"Fix the fault while preserving invariants: {dag.invariants}"
                    )

                worker_output, tokens = self._call_worker(step.assigned_lane, contextualized_prompt)
                self.governor.record_call(step.assigned_lane, tokens)

                exit_code, verify_log = self._verify(step.verification_cmd, step.timeout_s)
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
                    f"Diagnose why step {step.step_id} failed verification `{step.verification_cmd}`:\n{_tail(last_error, 2000)}",
                )
                self.governor.record_call(LaneTier.LOCAL_IRIS, iris_tokens)
                # Undo the half-finished play before handing back, so the tree is left clean.
                rollback_exit, rollback_log = (None, "")
                if dag.rollback_strategy and dag.rollback_strategy.strip():
                    rollback_exit, rollback_log = self._verify(dag.rollback_strategy, DEFAULT_TIMEOUT_S)
                return {
                    "status": "FUMBLE_HALTED",
                    "failed_step": step.step_id,
                    "iris_diagnosis": iris_diag,
                    "rollback": {"cmd": dag.rollback_strategy, "exit_code": rollback_exit, "log": _tail(rollback_log, 800)},
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
