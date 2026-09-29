"""Unit tests for NouGenMorph Evolutionary Ingestion Engine."""

import pytest

from nougen_morph.engine import (
    AdoptionState,
    MorphCandidate,
    MorphEvidence,
    MorphFinding,
    MorphKind,
    NouGenMorphEngine,
)


def test_morph_score_calculation():
    """Verify MorphScore = (U * G * V * C * R) - I."""
    candidate = MorphCandidate(
        name="latent_specification_completion",
        kind=MorphKind.BEHAVIOR,
        donor_source="xda_coding_agent_experiment",
        donor_behavior="Agent inferred UX requirements not explicitly demanded",
        generalized_behavior="Perform evidence-constrained latent specification completion",
        nougen_target="NouGenCode.ProductJudgmentPass",
        usefulness=0.96,
        generalizability=0.98,
        verifiability=0.82,
        compatibility=0.97,
        reversibility=0.99,
        integration_cost=0.08,
    )
    score = candidate.morph_score()
    expected = (0.96 * 0.98 * 0.82 * 0.97 * 0.99) - 0.08
    assert round(score, 4) == round(expected, 4)
    assert score > 0.65


def test_debranding_invariant_quarantine():
    """Verify hardcoding provider brands in generalized forms causes automatic quarantine."""
    engine = NouGenMorphEngine(acceptance_threshold=0.50)
    branded_candidate = MorphCandidate(
        name="claude_code_copy",
        kind=MorphKind.BEHAVIOR,
        donor_source="xda",
        donor_behavior="Claude did nice things",
        generalized_behavior="Use Claude Code everywhere",  # Brand violation!
        nougen_target="NouGenCode.ClaudeEngine",
        usefulness=0.99,
        generalizability=0.99,
        verifiability=0.99,
        compatibility=0.99,
        reversibility=1.0,
        integration_cost=0.05,
    )
    accepted, score = engine.ingest_candidate(branded_candidate)
    assert not accepted
    assert branded_candidate.state == AdoptionState.QUARANTINED


def test_latent_specification_completion_math():
    """Verify LSC formula with heavy hallucination penalty (lambda > 1)."""
    # 5 valid inferred, 0 hallucinated -> LSC = 5 / 5 = 1.0
    lsc_clean = NouGenMorphEngine.calculate_latent_spec_completion(
        explicit_reqs=10, valid_inferred_reqs=5, hallucinated_reqs=0, lambda_penalty=2.0
    )
    assert lsc_clean == 1.0

    # 5 valid inferred, 2 hallucinated (lambda=2) -> LSC = 5 / (5 + 4) = 5/9 ≈ 0.555
    lsc_hallucinated = NouGenMorphEngine.calculate_latent_spec_completion(
        explicit_reqs=10, valid_inferred_reqs=5, hallucinated_reqs=2, lambda_penalty=2.0
    )
    assert round(lsc_hallucinated, 3) == 0.556


def test_evidence_weighted_non_democratic_arbitration():
    """Verify senior engineering arbitration: critical claim blocks shipping regardless of votes."""
    cosmetic_pass_1 = MorphFinding(
        claim_id="f1",
        statement="Component rendered with good contrast",
        severity=0.2,
        evidence_weight=0.5,
        confidence=0.9,
        blast_radius=0.1,
        resolved=False,
    )
    cosmetic_pass_2 = MorphFinding(
        claim_id="f2",
        statement="Code conforms to linter",
        severity=0.1,
        evidence_weight=0.8,
        confidence=1.0,
        blast_radius=0.1,
        resolved=False,
    )
    critical_security_vuln = MorphFinding(
        claim_id="f3",
        statement="Remote code execution vulnerability in path router",
        severity=1.0,
        evidence_weight=0.95,
        confidence=0.98,
        blast_radius=0.9,
        resolved=False,
    )

    # 2 positive/minor findings vs 1 critical
    findings = [cosmetic_pass_1, cosmetic_pass_2, critical_security_vuln]
    can_ship, max_risk = NouGenMorphEngine.evaluate_arbitration(findings, critical_threshold=0.60)

    # Must block shipping!
    assert not can_ship
    assert max_risk > 0.80

    # Once resolved, shipping is unlocked
    critical_security_vuln.resolved = True
    can_ship_after_fix, max_risk_after_fix = NouGenMorphEngine.evaluate_arbitration(findings, critical_threshold=0.60)
    assert can_ship_after_fix
    assert max_risk_after_fix < 0.20
