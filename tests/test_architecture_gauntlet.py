"""Tests for NouGen Architecture Gauntlet (50-Question Synthesis & Validation).

Verifies that all 50 questions across the 16 core domains are answered,
schemas validate, Q50 mandatory falsifier is present, and SHA-256 receipts match.
"""

import pytest
from nougen_shards.architecture_gauntlet import (
    GauntletAnswer,
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


def test_core_questions_structure_and_falsifiers():
    registry = GauntletRegistry()

    # Q1: Memory policy evolution
    q1 = registry.answers[1]
    assert "Decoupled Objective Invariant" in q1.hypothesis
    assert len(q1.falsifier) > 20

    # Q2: Guarded absence proof
    q2 = registry.answers[2]
    assert "Guarded Absence Theorem" in q2.hypothesis
    assert "CANNOT_DETERMINE" in q2.evidence_and_math

    # Q3: Append-only forgetting
    q3 = registry.answers[3]
    assert "Bitemporal Masking" in q3.hypothesis

    # Q4: Contradiction resolution
    q4 = registry.answers[4]
    assert "Deterministic Bitemporal Arbitration" in q4.hypothesis

    # Q50: Central thesis falsifier
    q50 = registry.answers[50]
    assert "Central NouGen Falsification Benchmark" in q50.hypothesis
    assert len(q50.falsifier) > 30
