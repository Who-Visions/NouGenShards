"""Unit tests for Kaedra Proportional Retrieval Law & Escalation Governance."""

from nougen_shards.proportional_retrieval import (
    RetrievalLevel,
    LEVEL_BUDGETS,
    classify_retrieval_level,
    ProportionalRetrievalGovernor,
)


def test_default_proportional_recall():
    """Rule 1: Ordinary queries default to RECALL (cheapest useful retrieval)."""
    assert classify_retrieval_level("what is the severity lock shard?") == RetrievalLevel.RECALL
    assert classify_retrieval_level("find corbin hades canon") == RetrievalLevel.RECALL
    assert classify_retrieval_level("who is kenji oda?") == RetrievalLevel.RECALL


def test_explicit_escalation_classification():
    """Rule 3: Distinct escalation levels are explicitly respected."""
    assert classify_retrieval_level("please run deep recall on chapter 4") == RetrievalLevel.DEEP_RECALL
    assert classify_retrieval_level("grep deeper across all archives") == RetrievalLevel.GREP_DEEPER
    assert classify_retrieval_level("check coverage and completeness proof") == RetrievalLevel.COVERAGE
    assert classify_retrieval_level("inspect fleet status across nodes") == RetrievalLevel.FLEET_STATUS
    assert classify_retrieval_level("run a stress test on the socket") == RetrievalLevel.STRESS_TEST


def test_level_budgets_invariants():
    """Ensure budgets enforce progressive limits and strict ceilings."""
    recall_b = LEVEL_BUDGETS[RetrievalLevel.RECALL]
    deep_b = LEVEL_BUDGETS[RetrievalLevel.DEEP_RECALL]
    grep_b = LEVEL_BUDGETS[RetrievalLevel.GREP_DEEPER]

    assert recall_b.max_results < deep_b.max_results < grep_b.max_results
    assert recall_b.max_fanout_nodes <= deep_b.max_fanout_nodes <= grep_b.max_fanout_nodes
    assert recall_b.allow_cross_lane is False
    assert deep_b.allow_cross_lane is True


def test_timeout_does_not_manufacture_infrastructure_incident():
    """Rule 4 & 7: Timeout does not imply node failure or trigger incident report."""
    gov = ProportionalRetrievalGovernor()
    result = gov.handle_timeout("sample query", RetrievalLevel.RECALL, elapsed_s=2.05)

    assert result.timeout_occurred is True
    assert result.completed is False
    assert result.infrastructure_incident_reported is False
    assert "Node health remains unimpugned" in result.message
