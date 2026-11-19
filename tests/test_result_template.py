"""
Tests for Universal Deterministic Result Engine & Evaluation Template Evaluator.
Verifies:
  - Bounded interval properties: 0 <= R_min <= R_max <= 1
  - Monotonicity: adding evidence sharpens [R_min, R_max]
  - Hard gate enforcement: any failed gate causes instant FAIL
  - Threshold tau gating: PASS when R_min >= tau, FAIL when R_max < tau, else UNKNOWN_WITHIN_BUDGET
  - Deterministic hashing: byte-identical canonical SHA-256 for template and evidence
"""

import pytest
from nougen_shards.result_template import (
    EvaluationStatus,
    MetricCriterion,
    ResultTemplate,
    compute_evidence_hash,
    evaluate_result,
)


@pytest.fixture
def standard_template():
    return ResultTemplate(
        template_id="poe_evaluation_v1",
        version="1.0.0",
        tau=0.75,
        metrics=(
            MetricCriterion(name="test_pass_rate", weight=3.0, min_value=0.0, max_value=1.0),
            MetricCriterion(name="code_coverage", weight=2.0, min_value=0.0, max_value=1.0),
            MetricCriterion(name="lint_clean", weight=1.0, min_value=0.0, max_value=1.0),
        ),
        hard_gates=("security_check", "compilation_success"),
        description="Standard POE Verification Template",
    )


def test_template_canonical_hash_determinism(standard_template):
    h1 = standard_template.canonical_hash()
    h2 = standard_template.canonical_hash()
    assert h1 == h2
    assert len(h1) == 64


def test_evidence_hash_determinism():
    ev1 = {"b": 2, "a": 1, "c": [1, 2, 3]}
    ev2 = {"a": 1, "c": [1, 2, 3], "b": 2}
    assert compute_evidence_hash(ev1) == compute_evidence_hash(ev2)


def test_hard_gate_failure_instant_fail(standard_template):
    evidence = {
        "security_check": False,  # Failed gate
        "compilation_success": True,
        "test_pass_rate": 1.0,
        "code_coverage": 1.0,
        "lint_clean": 1.0,
    }
    result = evaluate_result(evidence, standard_template)
    assert not result.hard_gates_passed
    assert result.status == EvaluationStatus.FAIL
    assert "security_check" in result.hard_gate_failures


def test_complete_evidence_pass(standard_template):
    evidence = {
        "security_check": True,
        "compilation_success": True,
        "test_pass_rate": 1.0,
        "code_coverage": 0.8,
        "lint_clean": 1.0,
    }
    # Weighted score: (3*1.0 + 2*0.8 + 1*1.0) / 6.0 = (3.0 + 1.6 + 1.0) / 6.0 = 5.6 / 6.0 = 0.933333...
    result = evaluate_result(evidence, standard_template)
    assert result.hard_gates_passed
    assert result.coverage == 1.0
    assert result.r_min == pytest.approx(result.r_max)
    assert result.r_min >= standard_template.tau
    assert result.status == EvaluationStatus.PASS


def test_missing_evidence_unknown_within_budget(standard_template):
    # Only test_pass_rate known (1.0), coverage and lint unknown
    evidence = {
        "security_check": True,
        "compilation_success": True,
        "test_pass_rate": 1.0,
    }
    # R_min = (3*1.0 + 0 + 0) / 6.0 = 3.0 / 6.0 = 0.50
    # R_max = (3*1.0 + 2*1.0 + 1*1.0) / 6.0 = 6.0 / 6.0 = 1.00
    # tau = 0.75 -> R_min (0.50) < 0.75 <= R_max (1.00) -> UNKNOWN_WITHIN_BUDGET
    result = evaluate_result(evidence, standard_template)
    assert result.hard_gates_passed
    assert result.coverage == pytest.approx(0.50)
    assert result.r_min == pytest.approx(0.50)
    assert result.r_max == pytest.approx(1.00)
    assert result.status == EvaluationStatus.UNKNOWN_WITHIN_BUDGET


def test_missing_evidence_definite_fail(standard_template):
    # test_pass_rate is 0.0, even with max unknown it cannot reach tau 0.75
    evidence = {
        "security_check": True,
        "compilation_success": True,
        "test_pass_rate": 0.0,
    }
    # R_min = 0.0
    # R_max = (3*0.0 + 2*1.0 + 1*1.0) / 6.0 = 3.0 / 6.0 = 0.50
    # tau = 0.75 -> R_max (0.50) < 0.75 -> FAIL
    result = evaluate_result(evidence, standard_template)
    assert result.hard_gates_passed
    assert result.r_max == pytest.approx(0.50)
    assert result.status == EvaluationStatus.FAIL


def test_monotonic_interval_contraction(standard_template):
    ev_initial = {
        "security_check": True,
        "compilation_success": True,
        "test_pass_rate": 0.8,
    }
    res1 = evaluate_result(ev_initial, standard_template)

    ev_refined = {
        "security_check": True,
        "compilation_success": True,
        "test_pass_rate": 0.8,
        "code_coverage": 0.7,
    }
    res2 = evaluate_result(ev_refined, standard_template)

    # Adding evidence must contract interval: res2.r_min >= res1.r_min and res2.r_max <= res1.r_max
    assert res2.r_min >= res1.r_min
    assert res2.r_max <= res1.r_max
    assert res2.coverage > res1.coverage
