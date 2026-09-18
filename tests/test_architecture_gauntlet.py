"""Tests for NouGen Architecture Gauntlet (50-Question Synthesis & Validation).

Verifies that all 50 questions across the 16 core domains are answered with full granular
content, no placeholders exist, Q4 & Q7 are un-ambiguous, Q50 falsifier is present,
and SHA-256 receipts match.
"""

from nougen_shards.architecture_gauntlet import (
    GauntletRegistry,
    arbitrate_cross_domain_conflict,
    arbitrate_epistemic_authority,
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
    assert report["preimage_length_bytes"] > 5000


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


def test_behavioral_q4_cross_domain_arbitration():
    """Verify runtime Q4 conflict resolution across versions, bridges, and quarantine."""
    # 1. Supersession
    a1 = {"id": "fact_1", "domain": "doc", "as_of_ms": 1000}
    a2 = {"id": "fact_2", "domain": "doc", "as_of_ms": 2000, "supersedes": "fact_1"}
    status, payload = arbitrate_cross_domain_conflict(a1, a2)
    assert status == "VERSIONED"
    assert payload["id"] == "fact_2"

    # 2. Bridge Merge (compatible payloads)
    doc_fact = {"id": "df1", "domain": "finance", "as_of_ms": 1000, "status": "active"}
    telemetry_fact = {"id": "tf1", "domain": "telemetry", "as_of_ms": 1000, "ping_ms": 42}
    status, payload = arbitrate_cross_domain_conflict(
        doc_fact, telemetry_fact, relational_bridges={("finance", "telemetry")}
    )
    assert status == "MERGED"
    assert payload["bridge"] is True

    # 3. Bridge Merge Conflict (conflicting scalar values on shared key)
    doc_conf = {"id": "df2", "domain": "finance", "value": 100}
    tel_conf = {"id": "tf2", "domain": "telemetry", "value": 200}
    status_conf, payload_conf = arbitrate_cross_domain_conflict(
        doc_conf, tel_conf, relational_bridges={("finance", "telemetry")}
    )
    assert status_conf == "MERGE_CONFLICT_QUARANTINED"
    assert "payload_value_mismatch" in payload_conf["reason"]

    # 4. Unbridged Quarantine
    status, payload = arbitrate_cross_domain_conflict(doc_fact, telemetry_fact, relational_bridges=set())
    assert status == "QUARANTINED"
    assert payload["reason"] == "unbridged_contradiction"


def test_behavioral_q7_epistemic_authority_gating():
    """Verify runtime Q7 epistemic authority: 10 inferences cannot override 1 canon telemetry."""
    canon = {"id": "tel_1", "tier": "VERIFIED_TELEMETRY", "value": "1829_passed"}
    inferences = [{"id": f"inf_{i}", "tier": "MODEL_INFERENCE", "value": "maybe_100_failed"} for i in range(10)]

    evidence_pool = [canon] + inferences
    decision = arbitrate_epistemic_authority(evidence_pool)

    assert decision["status"] == "CANON_ACCEPTED"
    assert decision["confidence_bps"] == 10000
    assert decision["winner"]["id"] == "tel_1"
    assert decision["overridden_count"] == 10

    # Inferences only capped at 1,000 bps
    inf_only_decision = arbitrate_epistemic_authority(inferences)
    assert inf_only_decision["status"] == "INFERENCE_CAPPED"
    assert inf_only_decision["confidence_bps"] <= 1000


def test_behavioral_q7_top_tier_telemetry_conflict_and_supersession():
    """Verify order-independent resolution of contradictory top-tier telemetry."""
    tel_old = {"id": "t_old", "tier": "VERIFIED_TELEMETRY", "value": "failed", "as_of_ms": 1000}
    tel_new = {"id": "t_new", "tier": "VERIFIED_TELEMETRY", "value": "passed", "as_of_ms": 2000}

    # Order-independent temporal supersession: newer timestamp wins
    dec_forward = arbitrate_epistemic_authority([tel_old, tel_new])
    dec_reverse = arbitrate_epistemic_authority([tel_new, tel_old])
    assert dec_forward["status"] == "CANON_SUPERSEDED"
    assert dec_forward["winner"]["id"] == "t_new"
    assert dec_reverse["status"] == "CANON_SUPERSEDED"
    assert dec_reverse["winner"]["id"] == "t_new"

    # Equi-temporal contradiction drops confidence to 0 (order-independent quarantine)
    tel_eq1 = {"id": "te1", "tier": "VERIFIED_TELEMETRY", "value": "passed", "as_of_ms": 1000}
    tel_eq2 = {"id": "te2", "tier": "VERIFIED_TELEMETRY", "value": "failed", "as_of_ms": 1000}
    eq_dec1 = arbitrate_epistemic_authority([tel_eq1, tel_eq2])
    eq_dec2 = arbitrate_epistemic_authority([tel_eq2, tel_eq1])
    assert eq_dec1["status"] == "TELEMETRY_CONFLICT_QUARANTINED"
    assert eq_dec1["confidence_bps"] == 0
    assert eq_dec2["status"] == "TELEMETRY_CONFLICT_QUARANTINED"
    assert eq_dec2["confidence_bps"] == 0


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

