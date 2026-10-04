"""
Unit tests for NouGenCode Intelligence & Cleanup Scoring Engine.
Validates all 8 mathematical formulas and the NouGenCodeAuditor report generation.
"""
import pytest
from nougen_shards.nougen_code_scorer import (
    compute_intelligence_density,
    compute_repair_priority,
    compute_redundancy_similarity,
    compute_refactor_value,
    compute_dead_code_probability,
    compute_trust_boundary_risk,
    evaluate_refactor_acceptance,
    compute_simplification_gain,
    NouGenCodeAuditor,
)


def test_compute_intelligence_density():
    # 50 unique tokens, 5 capabilities, 100 LOC
    density = compute_intelligence_density(50, 5, 100)
    assert density == round((50 * 5) / 101, 4)
    assert density > 0


def test_compute_repair_priority():
    # Severity 9.0, Blast Radius 4.0, Complexity 2.0
    priority = compute_repair_priority(9.0, 4.0, 2.0)
    assert priority == round(36.0 / 3.0, 4)
    assert priority == 12.0


def test_compute_redundancy_similarity():
    set_a = {"tokenA", "tokenB", "tokenC", "tokenD"}
    set_b = {"tokenC", "tokenD", "tokenE", "tokenF"}
    # Overlap is 2 tokens out of 8 total slots -> 2 * 2 / 8 = 0.5
    similarity = compute_redundancy_similarity(set_a, set_b)
    assert similarity == 0.5


def test_compute_refactor_value():
    # LOC delta = 50 lines removed, mult = 1.5, risk = 0.2
    val = compute_refactor_value(50, maintenance_multiplier=1.5, regression_risk=0.2)
    assert val == round((50 * 1.5) - 0.2, 4)
    assert val == 74.8


def test_compute_dead_code_probability():
    assert compute_dead_code_probability(0, 10) == 1.0  # Zero refs = 100% dead
    assert compute_dead_code_probability(5, 10) == 0.5
    assert compute_dead_code_probability(10, 10) == 0.0  # Full refs = 0% dead
    assert compute_dead_code_probability(15, 10) == 0.0  # Clamped to 0.0


def test_compute_trust_boundary_risk():
    # 3 unsanitized inputs, privilege level 3, exposure 0.8
    risk = compute_trust_boundary_risk(3, 3, 0.8)
    assert risk == 7.2


def test_evaluate_refactor_acceptance():
    # 1. Accepted: tests pass, zero capability loss, density improves
    assert evaluate_refactor_acceptance(
        tests_passing=True,
        capability_loss=0,
        old_density=2.45,
        new_density=3.10,
    ) is True

    # 2. Rejected: tests fail
    assert evaluate_refactor_acceptance(
        tests_passing=False,
        capability_loss=0,
        old_density=2.45,
        new_density=3.10,
    ) is False

    # 3. Rejected: capability loss > 0
    assert evaluate_refactor_acceptance(
        tests_passing=True,
        capability_loss=1,
        old_density=2.45,
        new_density=3.10,
    ) is False

    # 4. Rejected: density regresses
    assert evaluate_refactor_acceptance(
        tests_passing=True,
        capability_loss=0,
        old_density=3.50,
        new_density=2.10,
    ) is False


def test_compute_simplification_gain():
    # Complexity goes from 50 to 20 -> 60% gain
    gain = compute_simplification_gain(50.0, 20.0)
    assert gain == 60.0


def test_nougen_code_auditor_clean_module():
    clean_code = '''
def calculate_ratio(a: float, b: float) -> float:
    """Calculates ratio safely."""
    return a / b if b != 0 else 0.0

def format_percentage(ratio: float) -> str:
    return f"{ratio:.1%}"
'''
    report = NouGenCodeAuditor.audit_source_text(clean_code, file_name="math_utils.py", ref_count=8)
    assert report.file_path == "math_utils.py"
    assert report.loc > 0
    assert report.intelligence_density > 0
    assert report.dead_code_probability < 0.5
    assert report.trust_boundary_risk == 0.0
    assert report.refactor_candidate is False
