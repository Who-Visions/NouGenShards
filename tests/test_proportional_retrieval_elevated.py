"""
Unit tests for ProportionalRetrievalElevated mathematical dynamics.
Tests multi-armed bandit utility calculation, Dirichlet fanout simplex normalization,
Pareto optimal escalation boundaries, and health decoupling invariants.
"""

import pytest
from nougen_shards.proportional_retrieval_elevated import (
    ProportionalRetrievalElevated,
    RetrievalLevel,
    LEVEL_BUDGETS
)


def test_classify_intent_level():
    gov = ProportionalRetrievalElevated()
    assert gov.classify_intent_level("simple query for shard 12") == RetrievalLevel.RECALL
    assert gov.classify_intent_level("please run deep recall on project architecture") == RetrievalLevel.DEEP_RECALL
    assert gov.classify_intent_level("grep deeper into error traces") == RetrievalLevel.GREP_DEEPER
    assert gov.classify_intent_level("perform full coverage audit all shards") == RetrievalLevel.COVERAGE
    assert gov.classify_intent_level("check fleet health and ping peers") == RetrievalLevel.FLEET_STATUS
    assert gov.classify_intent_level("execute stress test on vector db") == RetrievalLevel.STRESS_TEST


def test_dirichlet_simplex_sampling():
    gov = ProportionalRetrievalElevated()
    weights = [2.0, 3.0, 5.0, 1.0]
    simplex = gov.sample_dirichlet_fanout(weights)
    assert len(simplex) == len(weights)
    # Must sum to 1.0 (valid probability distribution)
    assert pytest.approx(sum(simplex), rel=1e-5) == 1.0
    # All components strictly non-negative
    assert all(p >= 0.0 for p in simplex)


def test_pareto_escalation_boundary():
    gov = ProportionalRetrievalElevated(pareto_marginal_threshold=0.001)

    # Escalating from RECALL (250 tokens) to DEEP_RECALL (1200 tokens):
    # delta_cost = 950 tokens.
    # Case A: Massive gain in relevance (from 0.1 to 0.95 -> delta_rel = 0.85).
    # Marginal efficiency = 0.85 / 950 = 0.000894 < 0.001 -> dominated if threshold is high
    escalate, eff = gov.evaluate_pareto_escalation(
        RetrievalLevel.RECALL,
        RetrievalLevel.DEEP_RECALL,
        observed_relevance=0.1,
        target_expected_relevance=0.95
    )
    assert eff > 0.0

    # Case B: Zero or negative relevance gain -> strictly prohibited
    escalate_neg, eff_neg = gov.evaluate_pareto_escalation(
        RetrievalLevel.RECALL,
        RetrievalLevel.DEEP_RECALL,
        observed_relevance=0.8,
        target_expected_relevance=0.7
    )
    assert escalate_neg is False
    assert eff_neg <= 0.0


def test_bayesian_arm_utility_and_update():
    gov = ProportionalRetrievalElevated()
    u_initial = gov.compute_expected_utility(RetrievalLevel.RECALL)

    # Successful retrieval updates alpha
    gov.update_bayesian_arm(RetrievalLevel.RECALL, items_retrieved=5, elapsed_s=0.5)
    u_updated = gov.compute_expected_utility(RetrievalLevel.RECALL)
    assert u_updated > u_initial


def test_timeout_decoupling_zero_manufactured_incidents():
    gov = ProportionalRetrievalElevated()
    res = gov.handle_timeout("recall my memory", RetrievalLevel.RECALL, elapsed_s=2.5)
    assert res["completed"] is False
    assert res["timeout_occurred"] is True
    # Invariant: timeout must never manufacture an infrastructure incident!
    assert res["infrastructure_incident_reported"] is False
    assert "Node health remains unimpugned" in res["message"]
