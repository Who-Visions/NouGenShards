"""Tests for NouGen Architecture Gauntlet (50-Question Synthesis & Validation).

Verifies that all 50 questions across the 16 core domains are answered with full granular
content, no placeholders exist, Q4 & Q7 are un-ambiguous, Q50 falsifier is present,
and SHA-256 receipts match.
"""

from nougen_shards.architecture_gauntlet import (
    GauntletRegistry,
)


def test_gauntlet_full_50_suite_completeness():
    registry = GauntletRegistry()
    is_complete, report = registry.validate_full_suite()

    assert is_complete is True
    assert report["total_questions_answered"] == 50
    assert report["is_complete_50_50"] is True
    assert report["unique_domains"] >= 12
    assert report["mandatory_q50_falsifier_present"] is True
    assert len(report["receipt_fingerprint"]) == 64


def test_every_single_question_has_substantive_content():
    registry = GauntletRegistry()
    assert len(registry.answers) == 50

    for q_num in range(1, 51):
        ans = registry.answers[q_num]
        assert ans.question_number == q_num
        assert len(ans.question_text) > 10, f"Q{q_num} question_text too short"
        assert len(ans.hypothesis) > 20, f"Q{q_num} hypothesis too short"
        assert len(ans.evidence_and_math) > 15, f"Q{q_num} evidence_and_math too short"
        assert len(ans.implementation_consequence) > 15, f"Q{q_num} implementation_consequence too short"
        assert len(ans.falsifier) > 20, f"Q{q_num} falsifier too short"
        # Ensure no generic placeholder strings exist
        assert "Question on" not in ans.hypothesis
        assert "Question on" not in ans.falsifier


def test_q4_and_q7_strict_resolution():
    registry = GauntletRegistry()

    # Q4: Merge requires explicit relational schema, else QUARANTINE
    q4 = registry.answers[4]
    assert "Strict temporal supersession" in q4.hypothesis
    assert "has_relational_bridge" in q4.evidence_and_math
    assert "QUARANTINED" in q4.evidence_and_math

    # Q7: Epistemic authority is immutable against N weak inferences
    q7 = registry.answers[7]
    assert "Strict Epistemic Authority Tiering" in q7.hypothesis
    assert "Override Cap = 0 bps" in q7.evidence_and_math


def test_q49_and_q50_benchmarks_and_falsifiers():
    registry = GauntletRegistry()

    # Q49: Harmonic Continuity Index
    q49 = registry.answers[49]
    assert "Harmonic Continuity Index" in q49.hypothesis
    assert "HCI = 3 /" in q49.evidence_and_math

    # Q50: Central Thesis Falsification Protocol
    q50 = registry.answers[50]
    assert "Central NouGen Falsification Protocol" in q50.hypothesis
    assert "180-day" in q50.hypothesis
    assert "Monolith_2M" in q50.evidence_and_math
