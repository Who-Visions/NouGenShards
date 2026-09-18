"""Regression tests for relay directive 20260913T174622Z."""
from nougen_shards.status_semantics import (
    Observation,
    StatusLevel as S,
    aggregate,
    classify_node,
    classify_node_dimensions,
    classify_shards_status,
    classify_tool_error,
    render,
)

NOW = 1_000_000.0


def obs(comp, scope, status, reason="r", age=0.0):
    return Observation(comp, scope, status, reason, last_verified_at=NOW - age)


def test_probe_failure_with_unknown_backend_is_probe_red_shards_unknown():
    # The exact ChatGPT incident payload.
    probe, shards = classify_shards_status({
        "up": False, "health_up": False, "mcp_up": False,
        "configured": True, "origin": "unknown", "blade_confirmed": False})
    assert probe.status is S.RED and probe.reported_scope == "probe"
    assert shards.status is S.UNKNOWN
    assert render([probe, shards]) == [
        "🔴 Shard health probe: endpoint check failed",
        "⚪ Shards: not established by this probe",
    ]


def test_probe_success_reconciles_node_origin_and_blade_confirmed():
    # FLASH KICK live node proof reconciliation test
    probe, shards = classify_shards_status({
        "up": True, "health_up": True, "mcp_up": True,
        "configured": True, "origin": "blade1tb", "blade_confirmed": True})
    assert probe.status is S.GREEN
    assert shards.status is S.GREEN
    assert shards.confidence == 1.0

    # Auto-reconciliation test when origin is blade1tb but blade_confirmed was omitted
    probe_auto, shards_auto = classify_shards_status({
        "up": True, "health_up": True, "mcp_up": True,
        "configured": True, "node": "blade1tb"})
    assert probe_auto.status is S.GREEN
    assert shards_auto.status is S.GREEN
    assert probe_auto.evidence["blade_confirmed"] is True


def test_tool_registration_mismatch_is_orange_not_bus_down():
    reg, bus = classify_tool_error("nougenmsg_latest", "unknown tool", "NouGenMsg bus")
    assert reg.status is S.ORANGE
    assert bus.status is S.UNKNOWN
    assert "registration" in reg.observed_component


def test_offline_node_is_unknown_never_red():
    for n in (classify_node("blade", None),
              classify_node("blade", 9999.0),
              classify_node("blade", None, declared_offline=True)):
        assert n.status is S.UNKNOWN
    assert "declared" in classify_node("blade", None, declared_offline=True).reason


def test_stale_green_degrades_to_yellow_and_says_why():
    stale = obs("tracker", "service", S.GREEN, "daily exported", age=3600).aged(NOW)
    assert stale.status is S.YELLOW
    assert stale.reason.startswith("stale:")
    # Age never turns anything RED.
    assert obs("x", "service", S.UNKNOWN, age=99999).aged(NOW).status is S.UNKNOWN


def test_partial_federation_visibility_is_yellow_naming_the_gap():
    fleet = aggregate("fleet", "fleet", [
        obs("phoebus", "node", S.GREEN),
        obs("whoart", "node", S.GREEN),
        obs("blade", "node", S.UNKNOWN),
    ], now=NOW)
    assert fleet.status is S.YELLOW
    assert "2/3" in fleet.reason and "blade" in fleet.reason


def test_parent_never_red_from_child_probe():
    parent = aggregate("Shards", "service", [obs("Shard health probe", "probe", S.RED)], now=NOW)
    assert parent.status is S.UNKNOWN
    assert "Shard health probe" in parent.reason


def test_direct_red_at_parent_scope_stays_red():
    parent = aggregate("Shards", "service", [
        obs("Shard health probe", "probe", S.GREEN),
        obs("Shards", "service", S.RED, "recall returned SQLITE_CORRUPT"),
    ], now=NOW)
    assert parent.status is S.RED
    assert "SQLITE_CORRUPT" in parent.reason


def test_all_children_green_is_green_and_no_evidence_is_unknown():
    assert aggregate("fleet", "fleet", [obs("a", "node", S.GREEN)], now=NOW).status is S.GREEN
    assert aggregate("fleet", "fleet", [], now=NOW).status is S.UNKNOWN


def test_telemetry_record_carries_required_fields():
    d = obs("Shards", "service", S.RED).to_dict()
    for k in ("observed_component", "reported_scope", "evidence",
              "confidence", "status", "last_verified_at"):
        assert k in d
    assert d["status"] == "RED"


def test_flash_kick_phoebus_multidimensional_node_state():
    # FLASH KICK Phoebus directive: regression test the exact mixed state
    # phoebus vault=UP, phoebus msg=TIMEOUT, whoart vault=UP, blade federated recall=TIMEOUT
    phoebus = classify_node_dimensions(
        node="phoebus",
        vault_ok=True,
        msg_ok=False,
        msg_error="NouGenMsg route timed out",
    )
    assert phoebus.vault_status is S.GREEN
    assert phoebus.msg_status is S.ORANGE
    assert phoebus.identity_confirmed is True

    whoart = classify_node_dimensions(
        node="whoart",
        vault_ok=True,
        msg_ok=True,
    )
    assert whoart.vault_status is S.GREEN
    assert whoart.msg_status is S.GREEN

    blade = classify_node_dimensions(
        node="blade",
        vault_ok=False,
        vault_error="federated recall TIMEOUT",
        msg_ok=True,
    )
    assert blade.vault_status is S.RED
    assert blade.msg_status is S.GREEN

    # Verify no dimension collapses into a false unified status
    assert phoebus.vault_status != phoebus.msg_status
    assert blade.vault_status != blade.msg_status
