"""Regression tests for relay directive 20260913T174622Z."""
from nougen_shards.status_semantics import (
    Observation,
    StatusLevel as S,
    aggregate,
    classify_node,
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


def test_flash_kick_blade_origin_reconciliation():
    from nougen_shards.status_semantics import reconcile_origin_identity, classify_shards_status
    raw_payload = {
        "up": True, "health_up": True, "mcp_up": True,
        "configured": True, "origin": "unknown", "blade_confirmed": False
    }
    witness = {"node": "blade", "blade_confirmed": True}
    reconciled = reconcile_origin_identity(raw_payload, witness)
    assert reconciled["blade_confirmed"] is True
    assert reconciled["origin"] == "blade"

    probe, shards = classify_shards_status(raw_payload, witness_evidence=witness)
    assert probe.status is S.GREEN
    assert probe.evidence["blade_confirmed"] is True
    assert probe.evidence["origin"] == "blade"


def test_flash_kick_phoebus_multidimensional_state_isolation():
    from nougen_shards.status_semantics import classify_node_dimensions, NodeDimensions

    # Phoebus state: vault UP, message route TIMEOUT/UNKNOWN, service UP
    dims = classify_node_dimensions(
        "phoebus",
        vault_status=S.GREEN,
        msg_status=S.UNKNOWN,
        service_status=S.GREEN,
        vault_reason="federation fanout succeeded",
        msg_reason="direct probe timed out",
        timestamps={"vault": NOW, "msg": NOW - 60},
        evidence={"fanout.phoebus": "ok", "msg.route": "timeout"}
    )
    assert isinstance(dims, NodeDimensions)
    assert dims.vault is S.GREEN
    assert dims.msg is S.UNKNOWN  # Not collapsed into RED or offline
    assert dims.service is S.GREEN

    obs_list = dims.aggregate_observations()
    vault_obs = next(o for o in obs_list if o.reported_scope == "vault")
    msg_obs = next(o for o in obs_list if o.reported_scope == "message_route")

    assert vault_obs.status is S.GREEN
    assert msg_obs.status is S.UNKNOWN
    # Ensure vault success does not falsely turn message route GREEN
    assert msg_obs.status != S.GREEN
    # Ensure message timeout does not falsely turn vault RED
    assert vault_obs.status != S.RED

