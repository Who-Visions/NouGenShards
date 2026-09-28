"""
Unit tests for TokenFuseElevated mathematical dynamics.
Tests leaky bucket dissipation, Lyapunov candidate stability, Shannon allocation entropy,
and circuit breaker thresholds.
"""

import math
import time
import pytest
from nougen_shards.token_fuse_elevated import (
    TokenFuseElevated,
    ElevatedTaskProfile,
    TokenFuseBreaker
)


def test_token_fuse_leaky_bucket_decay():
    fuse = TokenFuseElevated(
        session_id="test_decay",
        max_session_tokens=10000,
        max_task_tokens=5000,
        leak_rate=500.0  # 500 tokens/sec
    )
    fuse.request_task_lease("task_1")
    # Record initial tokens
    fuse.record_usage("task_1", input_tokens=1000, output_tokens=500)
    assert fuse.bucket_level == 1500.0

    # Simulate 1 second time passage
    fuse._decay_leaky_bucket(fuse.last_leak_update + 1.0)
    assert pytest.approx(fuse.bucket_level, rel=1e-2) == 1000.0

    # Simulate 3 more seconds
    fuse._decay_leaky_bucket(fuse.last_leak_update + 3.0)
    assert fuse.bucket_level == 0.0


def test_token_fuse_lyapunov_stability_calculation():
    fuse = TokenFuseElevated(
        session_id="test_lyapunov",
        max_session_tokens=1000,
        leak_rate=50.0,
        lyapunov_threshold=0.80
    )
    fuse.bucket_level = 500.0  # 50% capacity
    v, v_dot, is_stable = fuse.compute_lyapunov_stability(current_burn_rate=100.0)
    assert pytest.approx(v, rel=1e-3) == 0.5 * (0.5 ** 2)
    assert is_stable is True  # Stable below threshold

    # Drive bucket level above critical threshold with positive acceleration
    fuse.bucket_level = 900.0  # 90% capacity
    v_high, v_dot_high, is_stable_high = fuse.compute_lyapunov_stability(current_burn_rate=500.0)
    assert v_dot_high > 0.05
    assert is_stable_high is False


def test_token_fuse_allocation_entropy():
    fuse = TokenFuseElevated(
        session_id="test_entropy",
        max_session_tokens=50000
    )
    fuse.request_task_lease("task_a")
    fuse.request_task_lease("task_b")

    # Perfectly balanced allocation: 1000 tokens each
    fuse.record_usage("task_a", input_tokens=1000)
    fuse.record_usage("task_b", input_tokens=1000)
    entropy = fuse.compute_allocation_entropy()
    # Shannon entropy of uniform 2-distribution: - (0.5 ln 0.5 + 0.5 ln 0.5) = ln(2)
    expected_entropy = math.log(2)
    assert pytest.approx(entropy, rel=1e-3) == expected_entropy


def test_token_fuse_per_task_hard_breaker():
    fuse = TokenFuseElevated(
        session_id="test_task_break",
        max_session_tokens=50000,
        max_task_tokens=2000
    )
    fuse.request_task_lease("subagent_runaway")
    fuse.record_usage("subagent_runaway", input_tokens=1500)

    with pytest.raises(TokenFuseBreaker, match="exceeded hard limit"):
        fuse.record_usage("subagent_runaway", input_tokens=600)

    assert fuse.tasks["subagent_runaway"].active is False


def test_token_fuse_concurrent_task_ceiling():
    fuse = TokenFuseElevated(
        session_id="test_ceiling",
        max_tasks=2
    )
    assert fuse.request_task_lease("worker_1") is True
    assert fuse.request_task_lease("worker_2") is True

    with pytest.raises(TokenFuseBreaker, match="Concurrent task ceiling reached"):
        fuse.request_task_lease("worker_3")

    fuse.close_task("worker_1")
    assert fuse.request_task_lease("worker_3") is True
