"""Unit tests for Speculative Coach Engine (Hoare AST contracts, SurpriseGate, CounterfactualCreditAssigner)."""
from __future__ import annotations

from pathlib import Path

from nougen_shards.speculative_coach_engine import (
    ASTContractVerifier,
    CounterfactualCreditAssigner,
    HoareContract,
    SpeculativeBranch,
    SpeculativeSwarmExecutor,
    SurpriseGate,
    TacticalNode,
)


def test_ast_contract_verifier_and_surprise_gate(tmp_path: Path) -> None:
    contract = HoareContract(
        required_imports=["math", "json"],
        required_functions={"compute_score": ["x", "y"]},
        forbidden_calls=["eval", "os.system"],
        max_cyclomatic_branches=3,
        postcondition_assertions=["compute_score(2, 3) == 5"],
    )

    bad_code = "import math\ndef compute_score(a):\n    eval('1+1')\n    return a\n"
    ok, violations = ASTContractVerifier.verify_source(bad_code, contract)
    assert not ok
    assert any("FORBIDDEN_CALL: eval" in v for v in violations)
    assert any("MISSING_IMPORT: json" in v for v in violations)
    assert any("SIGNATURE_DRIFT" in v for v in violations)

    good_code = "import math\nimport json\ndef compute_score(x, y):\n    if x > 0:\n        return x + y\n    return y\n"
    ok_good, violations_good = ASTContractVerifier.verify_source(good_code, contract)
    assert ok_good and violations_good == []

    assert SurpriseGate.structural_divergence(good_code, good_code) == 0.0
    orthogonal_code = (
        "class A:\n    pass\nfor i in range(10):\n    try:\n"
        "        x = [j for j in range(i)]\n    except Exception:\n        pass\n"
    )
    jsd = SurpriseGate.structural_divergence(good_code, orthogonal_code)
    assert 0.25 < jsd <= 1.0

    node = TacticalNode(
        node_id="node_alpha",
        target_file="out_mod.py",
        contract=contract,
        branches=[
            SpeculativeBranch("b_primary", "phoebus:ollama:kaedracode", "primary_synthesis", "p1", 0.7),
            SpeculativeBranch("b_spec", "openrouter:free-router", "minimal_patch", "p2", 0.9),
        ],
        verification_cmd="cd .",
    )

    def worker_fn(lane_id: str, prompt: str) -> str:
        return good_code if lane_id == "openrouter:free-router" else bad_code

    def prm_fn(code: str, cmd: str, assertions: list[str]) -> float:
        return 0.95

    executor = SpeculativeSwarmExecutor(tmp_path, worker_fn, prm_fn)
    outcome = executor.execute_tactical_node(node)
    assert outcome["status"] == "COMMITTED_LOCAL_WINNER"
    assert outcome["winning_branch"] == "b_spec"
    assert not outcome["argon_escalated"]
    assert (tmp_path / "out_mod.py").read_text(encoding="utf-8") == good_code

    credit = CounterfactualCreditAssigner()
    deltas = credit.record_drive_outcome(
        "phoebus:ollama:kaedracode",
        [
            {"branch_id": "b_primary", "lane_id": "phoebus:ollama:kaedracode", "passed_contract": False, "utility_score": 0.0, "elapsed_ms": 120},
            {"branch_id": "b_spec", "lane_id": "openrouter:free-router", "passed_contract": True, "utility_score": 0.93, "elapsed_ms": 85},
        ],
        winning_branch_id="b_spec",
    )
    assert deltas["openrouter:free-router"] == 0.93
    assert credit.lane_stats["openrouter:free-router"].speculative_wins_over_primary == 1
