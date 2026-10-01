"""Unit tests for NouGen Information Dynamics & HURRICANE KICK Benchmark Suite."""
import pytest
from nougen_shards.information_dynamics import (
    CALIBRATION_VERSION,
    EVIDENCE_ANCHORS,
    BeliefDistribution,
    EvidenceRetrievalGovernor,
    FleetErrorEnergyTracker,
    InformationDynamicsBenchmark,
    NodeProviderInvariantVerifier,
    RateDistortionEngine,
    SemanticChannelEvaluator,
    SurprisalEstimator,
    WorkingProjection,
)


def test_surprisal_estimator_properties():
    est = SurprisalEstimator(alpha=1.0)
    corpus = "quantum entanglement tensor network in condensed matter physics"
    est.update(corpus)

    # Identical repeated event yields 0.0 marginal surprisal
    assert est.calculate_surprisal(corpus) == 0.0

    # Unseen novel event yields high surprisal
    surprisal_novel = est.calculate_surprisal("completely unrelated archaeological discovery in mesoamerica")
    assert surprisal_novel > 3.0


def test_belief_distribution_kl_divergence():
    p1 = BeliefDistribution({"action_deploy": 0.9, "action_abort": 0.1})
    p2 = BeliefDistribution({"action_deploy": 0.1, "action_abort": 0.9})
    
    # Significant shift in belief distribution
    kl = p2.divergence_kl(p1)
    assert kl > 1.0

    # Identical distributions have zero KL divergence
    assert p1.divergence_kl(p1) == 0.0


def test_rate_distortion_decision_vs_text():
    # Decision function depends only on whether safety is compromised
    def mock_decision(text: str):
        if "breach" in text or "violation" in text:
            return {"trigger_alarm": 0.95, "standby": 0.05}
        return {"trigger_alarm": 0.05, "standby": 0.95}

    history = [
        "Normal operations resumed on node blade1tb.",
        "System telemetry healthy, temperature 56C.",
        "Routine memory sync complete.",
    ]
    
    # Projection strips wording but preserves safe status
    proj = RateDistortionEngine.project(
        history_shards=history,
        compressor_fn=lambda _: "System operational and healthy.",
        decision_fn=mock_decision,
    )
    
    assert proj.decision_distortion == 0.0
    assert proj.is_valid(max_distortion_threshold=0.05)
    assert proj.compression_ratio < 1.0


def test_evidence_retrieval_stopping_rule():
    gov = EvidenceRetrievalGovernor(sufficiency_threshold=0.85, acquisition_cost_per_query=0.03)

    # Low sufficiency -> continue
    cont, _ = gov.should_continue_retrieval(current_sufficiency=0.70, expected_marginal_gain=0.10)
    assert cont is True

    # High sufficiency and low marginal gain -> stop
    cont_stop, reason = gov.should_continue_retrieval(current_sufficiency=0.90, expected_marginal_gain=0.01)
    assert cont_stop is False
    assert "Stopping" in reason


def test_semantic_channel_capacity():
    # Healthy channel where semantic fidelity preserves critical task rate
    healthy = SemanticChannelEvaluator.evaluate(
        transport_bytes_per_sec=50000.0,
        semantic_fidelity=0.98,
        task_complexity_bits=256.0,
        transmission_duration_sec=1.0,
    )
    assert healthy.intent_preserved is True
    assert healthy.status == "HEALTHY_SEMANTIC_PRESERVATION"

    # Degraded semantic channel (lossy transformation)
    degraded = SemanticChannelEvaluator.evaluate(
        transport_bytes_per_sec=50000.0,
        semantic_fidelity=0.50,
        task_complexity_bits=256.0,
        transmission_duration_sec=1.0,
    )
    assert degraded.intent_preserved is False
    assert degraded.status == "SEMANTIC_CHANNEL_COLLAPSE"


def test_fleet_error_energy_and_negative_drift():
    tracker = FleetErrorEnergyTracker()
    
    # Simulating stabilizing self-correction over 3 timesteps
    tracker.compute_energy(state_divergence=2.0, stale_belief_duration_s=30, unacked_critical_relays=2, provenance_violations=1, duplicate_work_count=1)
    tracker.compute_energy(state_divergence=1.0, stale_belief_duration_s=10, unacked_critical_relays=1, provenance_violations=0, duplicate_work_count=0)
    tracker.compute_energy(state_divergence=0.1, stale_belief_duration_s=1, unacked_critical_relays=0, provenance_violations=0, duplicate_work_count=0)

    drift = tracker.expected_drift()
    assert drift < 0.0  # Proves negative expected drift (self-stabilizing)
    assert tracker.is_stabilizing() is True


def test_provider_swap_invariants():
    st_prior = {
        "session_id": "ses_99ab",
        "logical_clock": 100,
        "state_hash": "hash_v1",
        "canonical_doctrine": "GEMINI.md",
    }
    st_valid = {
        "session_id": "ses_99ab",
        "logical_clock": 101,
        "parent_state_hash": "hash_v1",
        "state_hash": "hash_v2",
        "canonical_doctrine": "GEMINI.md",
    }
    valid, errs = NodeProviderInvariantVerifier.verify_swap(st_prior, st_valid)
    assert valid is True
    assert len(errs) == 0

    st_corrupt = {
        "session_id": "ses_other",
        "logical_clock": 99,  # Inversion
        "parent_state_hash": "wrong_hash",
        "canonical_doctrine": "CORRUPTED",
    }
    invalid, corrupt_errs = NodeProviderInvariantVerifier.verify_swap(st_prior, st_corrupt)
    assert invalid is False
    assert len(corrupt_errs) == 4


def test_hurricane_kick_full_benchmark_suite():
    benchmark = InformationDynamicsBenchmark()
    res = benchmark.run_all_benchmarks()

    assert res["calibration_version"] == CALIBRATION_VERSION
    assert len(res["evidence_anchors"]) == 8
    assert res["all_conditions_passed"] is True
    
    benchmarks = res["benchmarks"]
    assert "duplicate" in benchmarks and benchmarks["duplicate"]["passed"] is True
    assert "negation" in benchmarks and benchmarks["negation"]["passed"] is True
    assert "contradiction" in benchmarks and benchmarks["contradiction"]["passed"] is True
    assert "rare_irrelevant" in benchmarks and benchmarks["rare_irrelevant"]["passed"] is True
    assert "stale_evidence" in benchmarks and benchmarks["stale_evidence"]["passed"] is True
    assert "semantic_thrashing" in benchmarks and benchmarks["semantic_thrashing"]["passed"] is True
    assert "channel_loss" in benchmarks and benchmarks["channel_loss"]["passed"] is True
    assert "node_outage" in benchmarks and benchmarks["node_outage"]["passed"] is True
    assert "provider_swap" in benchmarks and benchmarks["provider_swap"]["passed"] is True
    assert "irreversible_actions" in benchmarks and benchmarks["irreversible_actions"]["passed"] is True
