import os
import pytest
from nougen_shards.status_semantics import classify_node_offline_reason, StatusLevel
from nougen_shards.keymaker import enforce_deepseek_auth_boundary


def test_classify_node_offline_reason_whoart():
    # WhoArt offline should be classified as planned_offline (UNKNOWN status), not an incident / RED
    res = classify_node_offline_reason("WhoArt", route_reachable=False, service_live=False, scheduled_activity=False)
    assert res["category"] == "planned_offline"
    assert res["status"] == StatusLevel.UNKNOWN
    assert "mobile laptop" in res["reason"]


def test_classify_node_offline_reason_online():
    res = classify_node_offline_reason("blade", route_reachable=True, service_live=True)
    assert res["category"] == "online"
    assert res["status"] == StatusLevel.GREEN


def test_classify_node_offline_reason_unexpected_failure():
    res = classify_node_offline_reason("hyperion", route_reachable=True, service_live=False)
    assert res["category"] == "local_service_down"
    assert res["status"] == StatusLevel.YELLOW


def test_enforce_deepseek_auth_boundary():
    res = enforce_deepseek_auth_boundary()
    assert res["provider"] == "deepseek"
    assert res["auth_bound"] is True
    assert res["status"] == "ENFORCED"
