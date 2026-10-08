"""Tests for Dream-RSI Replay Simulator & Dynamic Portfolio Scheduler."""

import pytest
from nougen_shards.rsi_replay_simulator import (
    CandidateRole,
    DiscoveryAttempt,
    DynamicPortfolioScheduler,
    HistoryReplaySimulator,
    PrefixObserver,
)


def test_discovery_attempt_creation():
    attempt = DiscoveryAttempt.create(
        attempt_id="att_001",
        code="def solve(): return 42",
        exit_code=0,
        score=0.95,
        parent_id=None,
        repairable=False,
    )
    assert attempt.attempt_id == "att_001"
    assert attempt.is_success is True
    assert len(attempt.code_hash) == 64


def test_prefix_observer_causality():
    attempts = [
        DiscoveryAttempt.create(f"id_{i}", f"code_{i}", 0, float(i))
        for i in range(5)
    ]
    observer = PrefixObserver(attempts)
    assert observer.total_count == 5
    assert len(observer.observed_prefix()) == 0

    revealed = observer.advance(2)
    assert len(revealed) == 2
    assert [a.attempt_id for a in observer.observed_prefix()] == ["id_0", "id_1"]
    assert observer.has_next() is True


def test_dynamic_portfolio_scheduler_roles():
    scheduler = DynamicPortfolioScheduler(max_parallelism=3)
    attempts = [
        DiscoveryAttempt.create("root_exp", "root", 0, 0.0, None),  # explore
        DiscoveryAttempt.create("fail_rep", "fail", 1, 0.1, "root_exp", repairable=True),  # recovery
        DiscoveryAttempt.create("success_high", "succ1", 0, 0.9, "root_exp"),  # exploit
        DiscoveryAttempt.create("success_mid", "succ2", 0, 0.7, "root_exp"),  # exploit
    ]
    batch = scheduler.select_batch(attempts, closed_set=set())
    assert len(batch) <= 3
    roles = {role for _, role in batch}
    assert CandidateRole.RECOVERY in roles
    assert CandidateRole.EXPLOITATION in roles


def test_history_replay_simulator_dreaming():
    attempts = [
        DiscoveryAttempt.create("n1", "c1", 0, 0.2),
        DiscoveryAttempt.create("n2", "c2", 0, 0.5, parent_id="n1"),
        DiscoveryAttempt.create("n3", "c3", 1, 0.0, parent_id="n2", repairable=True),
        DiscoveryAttempt.create("n4", "c4", 0, 0.88, parent_id="n2"),
    ]
    sim = HistoryReplaySimulator(attempts)
    res = sim.dream(DynamicPortfolioScheduler(max_parallelism=2))

    assert res.execution_cost == 0.0
    assert res.total_steps > 0
    assert res.max_score == 0.88
    assert res.best_attempt_id == "n4"
    assert "n4" in res.traversed_ids
