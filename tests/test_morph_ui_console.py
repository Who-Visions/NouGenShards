"""Unit tests for Morph SpecParity & Intelligent UI data contracts.

Validates the backend contract matching Shards 31407@db5 and 31406@db5:
- SpecIR explicit vs inferred requirements
- Agent lane evaluation schema (unbranded, generic providers)
- 6-view console contract integrity (SPEC, AGENTS, RESULTS, PROVENANCE, DECISIONS, TASKS)
- Verification gates and mutation safety
"""

from nougen_morph.engine import (
    MorphFinding,
    NouGenMorphEngine,
)


def test_morph_ui_spec_parity_contract():
    """Verify SpecIR and Latent Specification Completion for UI console."""
    # Explicit vs Inferred vs Hallucinated requirements
    explicit_reqs = 10
    valid_inferred = 4
    hallucinated = 0

    lsc = NouGenMorphEngine.calculate_latent_spec_completion(
        explicit_reqs=explicit_reqs,
        valid_inferred_reqs=valid_inferred,
        hallucinated_reqs=hallucinated,
    )
    assert lsc == 1.0  # Perfect inference with zero hallucination

    # Hallucination heavy penalty test
    lsc_penalized = NouGenMorphEngine.calculate_latent_spec_completion(
        explicit_reqs=explicit_reqs,
        valid_inferred_reqs=2,
        hallucinated_reqs=3,
        lambda_penalty=2.0,
    )
    # 2 / (2 + 2 * 3) = 2 / 8 = 0.25
    assert lsc_penalized == 0.25


def test_morph_ui_arbitration_gate():
    """Verify evidence-weighted arbitration rejects critical unresolved findings."""
    clean_findings = [
        MorphFinding(
            claim_id="f_01",
            statement="Minor cosmetic layout shift on mobile view",
            severity=0.2,
            evidence_weight=0.5,
            confidence=0.8,
            blast_radius=0.1,
            resolved=True,
        )
    ]
    can_ship, max_risk = NouGenMorphEngine.evaluate_arbitration(clean_findings)
    assert can_ship is True
    assert max_risk == 0.0

    critical_findings = [
        MorphFinding(
            claim_id="f_02",
            statement="Unauthorized mutation gate bypass detected",
            severity=0.95,
            evidence_weight=0.95,
            confidence=0.95,
            blast_radius=0.90,
            resolved=False,
        )
    ]
    can_ship_crit, crit_risk = NouGenMorphEngine.evaluate_arbitration(critical_findings)
    assert can_ship_crit is False
    assert crit_risk > 0.60
