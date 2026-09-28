"""Kaedra Proportional Retrieval Law & Escalation Governance.

Codifies the standing NouGen operating doctrine established in Relay leg
20260926T000004Z__chatgpt-app__g-whoentertains:

1. Ordinary "recall" means the cheapest useful retrieval first.
2. Do not silently escalate recall into deep recall, fleet-wide fanout,
   multi-vault completeness proof, health diagnostics, or stress testing.
3. "deep recall", "grep deeper", "coverage", "fleet status", and "stress test"
   are distinct escalation levels.
4. A request timeout means only that the request did not complete in its time
   window. It is NOT evidence that the node is unhealthy.
5. Escalate retrieval only when the operator explicitly requests it or necessary
   evidence is missing.
6. Kaedra must not manufacture infrastructure problems through unnecessarily
   aggressive querying and then recommend spending engineering time or token
   budgets fixing behavior caused by assistant's own retrieval strategy.
7. Keep knowledge retrieval semantics separate from infrastructure health semantics.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class RetrievalLevel(str, enum.Enum):
    RECALL = "recall"  # lightweight useful retrieval (cheapest, local FTS5)
    DEEP_RECALL = "deep recall"  # broader reconstruction
    GREP_DEEPER = "grep deeper"  # aggressive retrieval expansion
    COVERAGE = "coverage"  # completeness proof across shard cluster
    FLEET_STATUS = "fleet status"  # operational health check (NOT knowledge retrieval)
    STRESS_TEST = "stress test"  # intentionally expensive load


@dataclass(frozen=True)
class LevelBudget:
    max_results: int
    max_fanout_nodes: int
    timeout_seconds: float
    allow_cross_lane: bool
    requires_explicit_intent: bool


LEVEL_BUDGETS: Dict[RetrievalLevel, LevelBudget] = {
    RetrievalLevel.RECALL: LevelBudget(
        max_results=5,
        max_fanout_nodes=1,
        timeout_seconds=2.0,
        allow_cross_lane=False,
        requires_explicit_intent=False,
    ),
    RetrievalLevel.DEEP_RECALL: LevelBudget(
        max_results=20,
        max_fanout_nodes=3,
        timeout_seconds=5.0,
        allow_cross_lane=True,
        requires_explicit_intent=True,
    ),
    RetrievalLevel.GREP_DEEPER: LevelBudget(
        max_results=50,
        max_fanout_nodes=5,
        timeout_seconds=10.0,
        allow_cross_lane=True,
        requires_explicit_intent=True,
    ),
    RetrievalLevel.COVERAGE: LevelBudget(
        max_results=100,
        max_fanout_nodes=9,
        timeout_seconds=20.0,
        allow_cross_lane=True,
        requires_explicit_intent=True,
    ),
    RetrievalLevel.FLEET_STATUS: LevelBudget(
        max_results=10,
        max_fanout_nodes=9,
        timeout_seconds=3.0,
        allow_cross_lane=True,
        requires_explicit_intent=True,
    ),
    RetrievalLevel.STRESS_TEST: LevelBudget(
        max_results=500,
        max_fanout_nodes=9,
        timeout_seconds=60.0,
        allow_cross_lane=True,
        requires_explicit_intent=True,
    ),
}


def classify_retrieval_level(query_or_directive: str) -> RetrievalLevel:
    """Deterministically classify query text into its proportional retrieval level.
    
    Defaults strictly to RECALL unless explicit keyword signals justify escalation.
    """
    normalized = query_or_directive.strip().lower()

    if "stress test" in normalized or "load test" in normalized:
        return RetrievalLevel.STRESS_TEST
    if "fleet status" in normalized or "fleet health" in normalized or "ping peers" in normalized:
        return RetrievalLevel.FLEET_STATUS
    if "coverage" in normalized or "completeness proof" in normalized or "audit all shards" in normalized:
        return RetrievalLevel.COVERAGE
    if "grep deeper" in normalized or "deep grep" in normalized or "aggressive search" in normalized:
        return RetrievalLevel.GREP_DEEPER
    if "deep recall" in normalized or "reconstruct" in normalized or "broad recall" in normalized:
        return RetrievalLevel.DEEP_RECALL

    # Default: Proportional Law mandates cheapest recall first
    return RetrievalLevel.RECALL


@dataclass
class RetrievalExecutionResult:
    query: str
    level: RetrievalLevel
    budget: LevelBudget
    items: List[Dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    completed: bool = True
    timeout_occurred: bool = False
    infrastructure_incident_reported: bool = False
    message: str = ""


class ProportionalRetrievalGovernor:
    """Enforces that knowledge retrieval queries obey bounded budgets and
    cannot manufacture false positive infrastructure incidents upon timeouts.
    """

    def __init__(self, node_health_verifier: Optional[Any] = None) -> None:
        self.node_health_verifier = node_health_verifier

    def resolve_level(
        self, query: str, explicit_override: Optional[RetrievalLevel] = None
    ) -> Tuple[RetrievalLevel, LevelBudget]:
        level = explicit_override or classify_retrieval_level(query)
        budget = LEVEL_BUDGETS[level]
        return level, budget

    def handle_timeout(
        self, query: str, level: RetrievalLevel, elapsed_s: float
    ) -> RetrievalExecutionResult:
        """Rule 4 & 7: A timeout is merely a deadline expiration, NOT infrastructure failure."""
        budget = LEVEL_BUDGETS[level]
        return RetrievalExecutionResult(
            query=query,
            level=level,
            budget=budget,
            items=[],
            latency_ms=elapsed_s * 1000.0,
            completed=False,
            timeout_occurred=True,
            # CRITICAL INVARIANT: never mark node unhealthy purely due to retrieval timeout!
            infrastructure_incident_reported=False,
            message=(
                f"Query timed out after {elapsed_s:.2f}s under budget for '{level.value}'. "
                "Node health remains unimpugned without independent physical health probe."
            ),
        )
