from __future__ import annotations

import ast
import concurrent.futures
import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class HoareContract:
    """Formal neuro-symbolic specification emitted by Argon to eliminate semantic drift."""
    required_imports: List[str]
    required_functions: Dict[str, List[str]]  # func_name -> [arg_names]
    forbidden_calls: List[str]                # e.g., ["eval", "exec", "os.system"]
    max_cyclomatic_branches: int
    postcondition_assertions: List[str]       # Python expressions evaluated post-run


@dataclass(frozen=True)
class SpeculativeBranch:
    branch_id: str
    lane_id: str
    strategy_tag: str                         # "primary_synthesis" | "minimal_patch" | "fallback_refactor"
    prompt_payload: str
    prior_probability: float


@dataclass(frozen=True)
class TacticalNode:
    node_id: str
    target_file: str
    contract: HoareContract
    branches: List[SpeculativeBranch]
    verification_cmd: str
    kl_escalation_threshold: float = 0.78


class ASTContractVerifier:
    """
    Zero-token static verifier that enforces Argon's structural contracts
    before any sandboxed test execution or local PRM scoring occurs.
    """

    @staticmethod
    def verify_source(source_code: str, contract: HoareContract) -> Tuple[bool, List[str]]:
        violations: List[str] = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            return False, [f"SYNTAX_FAULT: line {exc.lineno}: {exc.msg}"]

        found_imports: set[str] = set()
        found_functions: Dict[str, List[str]] = {}
        branch_count = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found_imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                found_imports.add(node.module.split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found_functions[node.name] = [arg.arg for arg in node.args.args]
            elif isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
                branch_count += 1
            elif isinstance(node, ast.Call):
                call_name = ASTContractVerifier._resolve_call_name(node.func)
                if call_name in contract.forbidden_calls:
                    violations.append(f"FORBIDDEN_CALL: {call_name} at line {getattr(node, 'lineno', '?')}")

        for req_imp in contract.required_imports:
            if req_imp.split(".")[0] not in found_imports:
                violations.append(f"MISSING_IMPORT: {req_imp}")

        for fn_name, expected_args in contract.required_functions.items():
            if fn_name not in found_functions:
                violations.append(f"MISSING_FUNCTION: {fn_name}")
            else:
                actual_args = found_functions[fn_name]
                if actual_args != expected_args:
                    violations.append(
                        f"SIGNATURE_DRIFT: {fn_name} expected {expected_args}, got {actual_args}"
                    )

        if branch_count > contract.max_cyclomatic_branches:
            violations.append(
                f"COMPLEXITY_EXCEEDED: {branch_count} branches > cap {contract.max_cyclomatic_branches}"
            )

        return len(violations) == 0, violations

    @staticmethod
    def _resolve_call_name(func_node: ast.AST) -> str:
        if isinstance(func_node, ast.Name):
            return func_node.id
        if isinstance(func_node, ast.Attribute):
            parts: List[str] = [func_node.attr]
            curr = func_node.value
            while isinstance(curr, ast.Attribute):
                parts.append(curr.attr)
                curr = curr.value
            if isinstance(curr, ast.Name):
                parts.append(curr.id)
            return ".".join(reversed(parts))
        return ""


class SurpriseGate:
    """
    Information-theoretic gate that computes structural disagreement (Jensen-Shannon divergence)
    across parallel local swarm outputs. Wakes Argon ONLY when local lanes hit high-entropy deadlock.
    """

    @staticmethod
    def compute_ast_token_distribution(source_code: str) -> Dict[str, float]:
        try:
            tree = ast.parse(source_code)
            counts: Dict[str, int] = {}
            total = 0
            for node in ast.walk(tree):
                key = type(node).__name__
                counts[key] = counts.get(key, 0) + 1
                total += 1
            if total == 0:
                return {"EMPTY": 1.0}
            return {k: v / total for k, v in counts.items()}
        except SyntaxError:
            return {"SYNTAX_ERROR": 1.0}

    @classmethod
    def structural_divergence(cls, code_a: str, code_b: str) -> float:
        dist_p = cls.compute_ast_token_distribution(code_a)
        dist_q = cls.compute_ast_token_distribution(code_b)
        vocab = set(dist_p.keys()) | set(dist_q.keys())

        def kl_div(p: Dict[str, float], q: Dict[str, float]) -> float:
            s = 0.0
            for k in vocab:
                pk = p.get(k, 1e-9)
                qk = q.get(k, 1e-9)
                s += pk * math.log(pk / qk, 2)
            return s

        m = {k: 0.5 * (dist_p.get(k, 1e-9) + dist_q.get(k, 1e-9)) for k in vocab}
        jsd = 0.5 * kl_div(dist_p, m) + 0.5 * kl_div(dist_q, m)
        return min(1.0, max(0.0, jsd))


class SpeculativeSwarmExecutor:
    """
    Runs Argon's TacticalNode across parallel free/local lanes simultaneously,
    scores candidates with zero-token AST contracts + local PRM verification,
    and commits the winning worktree patch without burning Argon cycles.
    """

    def __init__(
        self,
        repo_root: Path,
        worker_call_fn: Callable[[str, str], str],
        prm_score_fn: Callable[[str, str, List[str]], float],
    ):
        self.repo_root = repo_root
        self._call_worker = worker_call_fn
        self._score_prm = prm_score_fn

    def execute_tactical_node(self, node: TacticalNode) -> Dict[str, Any]:
        candidates: List[Dict[str, Any]] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(node.branches)) as pool:
            future_map = {
                pool.submit(self._run_branch_in_isolated_sandbox, node, branch): branch
                for branch in node.branches
            }
            for fut in concurrent.futures.as_completed(future_map):
                branch = future_map[fut]
                try:
                    result = fut.result()
                    candidates.append(result)
                except Exception as exc:
                    candidates.append({
                        "branch_id": branch.branch_id,
                        "lane_id": branch.lane_id,
                        "passed_contract": False,
                        "passed_tests": False,
                        "code": "",
                        "utility_score": 0.0,
                        "error": str(exc),
                    })

        passing = [c for c in candidates if c["passed_contract"] and c["passed_tests"]]
        if passing:
            winner = max(passing, key=lambda c: c["utility_score"])
            target_path = self.repo_root / node.target_file
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(winner["code"], encoding="utf-8")
            return {
                "status": "COMMITTED_LOCAL_WINNER",
                "winning_branch": winner["branch_id"],
                "winning_lane": winner["lane_id"],
                "utility_score": winner["utility_score"],
                "argon_escalated": False,
            }

        # All speculative branches failed: measure structural divergence to decide if Argon wakes up
        codes = [c["code"] for c in candidates if c.get("code")]
        max_jsd = 0.0
        for i in range(len(codes)):
            for j in range(i + 1, len(codes)):
                max_jsd = max(max_jsd, SurpriseGate.structural_divergence(codes[i], codes[j]))

        should_wake_argon = max_jsd >= node.kl_escalation_threshold
        return {
            "status": "ESCALATE_TO_ARGON" if should_wake_argon else "LOCAL_REFINEMENT_LOOP",
            "structural_divergence_jsd": round(max_jsd, 4),
            "argon_escalated": should_wake_argon,
            "compressed_failure_digest": [
                {
                    "branch": c["branch_id"],
                    "lane": c["lane_id"],
                    "violations": c.get("violations", [])[:3],
                    "stderr_tail": c.get("stderr", "")[-300:],
                }
                for c in candidates
            ],
        }

    def _run_branch_in_isolated_sandbox(
        self, node: TacticalNode, branch: SpeculativeBranch
    ) -> Dict[str, Any]:
        generated_code = self._call_worker(branch.lane_id, branch.prompt_payload)
        passed_contract, violations = ASTContractVerifier.verify_source(generated_code, node.contract)

        if not passed_contract:
            return {
                "branch_id": branch.branch_id,
                "lane_id": branch.lane_id,
                "code": generated_code,
                "passed_contract": False,
                "passed_tests": False,
                "violations": violations,
                "utility_score": 0.0,
            }

        with tempfile.TemporaryDirectory(prefix=f"nougen_spec_{branch.branch_id}_") as tmp_dir:
            sandbox_file = Path(tmp_dir) / Path(node.target_file).name
            sandbox_file.write_text(generated_code, encoding="utf-8")

            proc = subprocess.run(
                node.verification_cmd,
                shell=True,
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            passed_tests = proc.returncode == 0

            # Local Iris PRM scores the code quality and invariant alignment at $0 cost
            prm_reward = self._score_prm(
                generated_code,
                node.verification_cmd,
                node.contract.postcondition_assertions,
            )
            utility = (0.4 * branch.prior_probability) + (0.6 * prm_reward) if passed_tests else 0.0

            return {
                "branch_id": branch.branch_id,
                "lane_id": branch.lane_id,
                "code": generated_code,
                "passed_contract": True,
                "passed_tests": passed_tests,
                "violations": [],
                "stderr": proc.stderr,
                "utility_score": round(utility, 4),
            }


@dataclass
class LanePerformanceStats:
    lane_id: str
    total_drives: int = 0
    speculative_wins_over_primary: int = 0
    first_pass_contract_passes: int = 0
    total_latency_ms: float = 0.0

    @property
    def contract_pass_rate(self) -> float:
        return self.first_pass_contract_passes / max(1, self.total_drives)

    @property
    def mean_latency_ms(self) -> float:
        return self.total_latency_ms / max(1, self.total_drives)


class CounterfactualCreditAssigner:
    """
    Computes counterfactual utility deltas across speculative drives and distills
    winning patterns into cached few-shot exemplars for NouGenShards.
    """

    def __init__(self) -> None:
        self.lane_stats: Dict[str, LanePerformanceStats] = {}

    def record_drive_outcome(
        self,
        primary_lane: str,
        candidates: List[Dict[str, Any]],
        winning_branch_id: Optional[str],
    ) -> Dict[str, float]:
        primary_utility = 0.0
        for c in candidates:
            if c.get("lane_id") == primary_lane:
                primary_utility = max(primary_utility, float(c.get("utility_score", 0.0)))

        deltas: Dict[str, float] = {}
        for c in candidates:
            lane = str(c.get("lane_id", "unknown"))
            stats = self.lane_stats.setdefault(lane, LanePerformanceStats(lane_id=lane))
            stats.total_drives += 1
            if c.get("passed_contract"):
                stats.first_pass_contract_passes += 1
            stats.total_latency_ms += float(c.get("elapsed_ms", 0.0))

            u = float(c.get("utility_score", 0.0))
            delta = round(u - primary_utility, 4)
            deltas[lane] = delta
            if lane != primary_lane and c.get("branch_id") == winning_branch_id and delta > 0:
                stats.speculative_wins_over_primary += 1

        return deltas
