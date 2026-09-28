import math
import pytest
from nougen_shards.hardcade_cron_out_elevated import (
    JitterBackoffCalculator,
    ReliabilityTracker,
    MisfireEstimator,
    compute_idempotency_key,
)


def test_jitter_backoff_full():
    calc = JitterBackoffCalculator(base_interval=1.0, max_interval=10.0, jitter_type="full")
    delay = calc.compute_delay(attempt=2, seed=42)
    # cap = min(10, 1 * 4) = 4.0
    assert 0.0 <= delay <= 4.0


def test_jitter_backoff_equal():
    calc = JitterBackoffCalculator(base_interval=1.0, max_interval=10.0, jitter_type="equal")
    delay = calc.compute_delay(attempt=2, seed=42)
    # cap = 4.0, half = 2.0 -> range [2.0, 4.0]
    assert 2.0 <= delay <= 4.0


def test_reliability_tracker():
    tracker = ReliabilityTracker(successes=9, failures=1, intervals=[10.0, 10.2, 9.8, 10.1])
    score = tracker.compute_reliability_score(target_interval=10.0)
    assert 0.8 <= score <= 0.9  # success_rate is 0.9, penalized slightly by interval jitter


def test_misfire_estimator():
    estimator = MisfireEstimator(lambda_drift=0.05)
    p0 = estimator.probability(0.0)
    assert p0 == 0.0

    p_drift = estimator.probability(10.0)
    expected = 1.0 - math.exp(-0.5)
    assert pytest.approx(p_drift, 1e-5) == expected


def test_idempotency_key():
    key1 = compute_idempotency_key("sched_1", 1700000000, "data_payload")
    key2 = compute_idempotency_key("sched_1", 1700000000, "data_payload")
    key3 = compute_idempotency_key("sched_1", 1700000001, "data_payload")

    assert key1 == key2
    assert key1 != key3
    assert len(key1) == 64
