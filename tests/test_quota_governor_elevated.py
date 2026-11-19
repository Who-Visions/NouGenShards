"""
Unit tests for QuotaGovernorElevated mathematical dynamics.
Tests hazard rate estimation, sigmoidal local steering probability,
hysteresis 1UP reset loop, and telemetry tracking.
"""

import math
import pytest
from nougen_shards.quota_governor_elevated import (
    QuotaGovernorElevated,
    QuotaLevel,
    RoutingDirective
)


def test_hazard_rate_and_time_to_depletion():
    gov = QuotaGovernorElevated()
    # 80 used of 100 limit, velocity 5 units/sec
    hazard, t_exhaust = gov.compute_hazard_rate(used=80.0, limit=100.0, velocity=5.0)
    # Remaining = 20. Hazard = 5 / 20 = 0.25. T_exhaust = 20 / 5 = 4.0s
    assert pytest.approx(hazard, rel=1e-3) == 0.25
    assert pytest.approx(t_exhaust, rel=1e-3) == 4.0

    # Exhausted limit
    h_inf, t_zero = gov.compute_hazard_rate(used=100.0, limit=100.0, velocity=5.0)
    assert math.isinf(h_inf)
    assert t_zero == 0.0


def test_sigmoidal_local_steering_probability():
    gov = QuotaGovernorElevated(sigmoid_midpoint=0.75, sigmoid_steepness=15.0)
    # At exact midpoint 75% -> probability must be exactly 0.50
    p_mid = gov.compute_local_routing_probability(75.0)
    assert pytest.approx(p_mid, rel=1e-3) == 0.50

    # At low usage (20%) -> probability near 0.0
    p_low = gov.compute_local_routing_probability(20.0)
    assert p_low < 0.01

    # At critical usage (95%) -> probability near 1.0
    p_high = gov.compute_local_routing_probability(95.0)
    assert p_high > 0.95


def test_hysteretic_1up_reset():
    gov = QuotaGovernorElevated(hysteresis_reset_threshold=0.55)

    # Drive bucket into RATION (92% used)
    t1 = gov.update_telemetry("openrouter", "deepseek-r1", used=92.0, limit=100.0)
    assert t1["level"] == QuotaLevel.RATION.value
    assert t1["directive"] == RoutingDirective.RATION_CLOUD.value

    # Usage drops slightly to 80% (still above 55% reset threshold) -> remains non-1UP
    t2 = gov.update_telemetry("openrouter", "deepseek-r1", used=80.0, limit=100.0)
    assert t2["is_1up_reset"] is False

    # Usage drops below hysteresis floor (50% <= 55%) -> triggers 1UP reset event!
    t3 = gov.update_telemetry("openrouter", "deepseek-r1", used=50.0, limit=100.0)
    assert t3["level"] == QuotaLevel.ONE_UP.value
    assert t3["directive"] == RoutingDirective.NORMAL.value
    assert t3["is_1up_reset"] is True
