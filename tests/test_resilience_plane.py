from datetime import datetime, timedelta, timezone

import pytest

from nougen_shards.resilience_plane import (
    CapabilityProbe,
    EvidenceSignal,
    PersistenceHooks,
    RecoveryCandidate,
    RouteAssertion,
    RouteProbe,
    RouteState,
    aggregate_federation,
    build_proof_receipt,
    choose_recovery,
    hostile_action_verified,
    persist_resilience_record,
    resolve_live_evidence,
    resolve_capability_graph,
    resolve_routes,
    route_delta,
    route_probes_from_status_payload,
    score_hypotheses,
    verify_recovery,
)


NOW = datetime(2026, 9, 29, 15, 30, tzinfo=timezone.utc)


def probe(route, health=True, mcp=True, *, age_s=0, ttl_s=60, domains=()):
    return RouteProbe(
        route_id=route, health_ok=health, mcp_ok=mcp, expected=True,
        observed_at=(NOW - timedelta(seconds=age_s)).isoformat(),
        source="fixture-probe", provenance={"request_id": f"probe-{route}"},
        ttl_s=ttl_s, fault_domains=tuple(domains),
    )


def signal(signal_id, likelihoods, *, domain="runtime", category="availability",
           reliability=1.0, age_s=0, ttl_s=60, verified=False):
    return EvidenceSignal(
        signal_id=signal_id, source="fixture-source",
        provenance={"fixture": signal_id},
        observed_at=(NOW - timedelta(seconds=age_s)).isoformat(), ttl_s=ttl_s,
        fault_domain=domain, category=category, reliability=reliability,
        likelihood_ratios=likelihoods, directly_verified=verified,
    )


def test_three_live_routes_keep_federation_green_with_degraded_redundancy():
    expected = ("edge-a", "edge-b", "mobile-c", "space-d")
    routes = resolve_routes([
        probe("edge-a", domains=("region-1",)),
        probe("edge-b", domains=("region-2",)),
        probe("mobile-c", domains=("region-3",)),
        probe("space-d", False, False, domains=("storage-mount",)),
    ], expected, now=NOW)

    fleet = aggregate_federation(routes, expected, now=NOW)

    assert fleet.state == RouteState.GREEN
    assert fleet.redundancy == "degraded"
    assert fleet.serving_count == 3 and fleet.red_count == 1
    assert fleet.serving_ratio == 0.75
    assert fleet.fault_domains["storage-mount"] == ("space-d",)
    assert routes["space-d"].source == "fixture-probe"
    assert routes["space-d"].observed_at == NOW.isoformat()


def test_stale_and_missing_route_evidence_become_unknown():
    routes = resolve_routes([probe("old-route", age_s=61)],
                            ("old-route", "missing-route"), now=NOW)

    assert routes["old-route"].state == RouteState.UNKNOWN
    assert routes["old-route"].freshness == "stale"
    assert routes["missing-route"].state == RouteState.UNKNOWN
    assert routes["missing-route"].observed_at is None
    assert routes["missing-route"].source == "current-sweep"
    assert routes["missing-route"].provenance["observation"] == "missing"


def test_small_future_clock_skew_is_fresh_but_large_skew_is_unknown():
    slight_skew = probe("slight-skew")
    slight_skew = RouteProbe(
        slight_skew.route_id, slight_skew.health_ok, slight_skew.mcp_ok,
        slight_skew.expected, (NOW + timedelta(seconds=2)).isoformat(),
        slight_skew.source, slight_skew.provenance, slight_skew.ttl_s,
    )
    large_skew = RouteProbe(
        "large-skew", True, True, True, (NOW + timedelta(seconds=6)).isoformat(),
        "fixture-probe", {}, 60,
    )
    routes = resolve_routes([slight_skew, large_skew],
                            ("slight-skew", "large-skew"), now=NOW)
    assert routes["slight-skew"].state == RouteState.GREEN
    assert routes["large-skew"].state == RouteState.UNKNOWN


def test_unknown_expected_state_never_turns_mobile_route_red():
    route = RouteProbe("mobile-route", False, False, expected=False,
                       observed_at=NOW.isoformat(), source="live-probe",
                       provenance={"schedule": "not-expected"}, ttl_s=60)
    resolved = resolve_routes([route], ("mobile-route",), now=NOW)["mobile-route"]
    assert resolved.state == RouteState.UNKNOWN


def test_correlated_evidence_is_not_multiplied_as_independent():
    priors = {"runtime_fault": 0.2, "hostile_action": 0.01, "other": 0.79}
    strongest = signal("runtime-error", {"runtime_fault": 12.0})
    repeated = signal("second-runtime-error", {"runtime_fault": 4.0})

    one = score_hypotheses(priors, [strongest], now=NOW)
    two = score_hypotheses(priors, [strongest, repeated], now=NOW)

    assert two.probabilities == pytest.approx(one.probabilities)
    assert two.grouped_fault_domains == ("runtime",)


def test_one_availability_503_cannot_verify_hostile_action():
    priors = {"runtime_fault": 0.7, "hostile_action": 0.01, "other": 0.29}
    outage = signal("origin-503", {"runtime_fault": 8.0, "hostile_action": 1.0})
    score = score_hypotheses(priors, [outage], now=NOW)

    assert score.probabilities["hostile_action"] / score.probabilities["other"] == pytest.approx(
        priors["hostile_action"] / priors["other"])
    assert hostile_action_verified([outage], minimum_independent_domains=2, now=NOW) is False
    with pytest.raises(ValueError):
        hostile_action_verified([outage], minimum_independent_domains=1, now=NOW)


def test_stale_evidence_does_not_change_posterior():
    priors = {"runtime_fault": 0.2, "other": 0.8}
    stale = signal("old-error", {"runtime_fault": 100.0}, age_s=61, ttl_s=60)
    score = score_hypotheses(priors, [stale], now=NOW)

    assert score.probabilities == pytest.approx(priors)
    assert score.stale_signals == ("old-error",)
    assert not score.used_signals


def test_score_keeps_timestamped_source_provenance_for_each_signal():
    item = signal("mount-error", {"runtime_fault": 10}, domain="mount")
    score = score_hypotheses({"runtime_fault": 0.2, "other": 0.8}, [item], now=NOW)
    assert score.evidence == ({
        "signal_id": "mount-error", "source": "fixture-source",
        "provenance": {"fixture": "mount-error"},
        "observed_at": NOW.isoformat(), "freshness": "fresh",
        "fault_domain": "mount", "category": "availability",
    },)


def test_smallest_reversible_recovery_requires_policy_rollback_and_validation():
    score = score_hypotheses(
        {"runtime_fault": 0.1, "other": 0.9},
        [signal("mount-error", {"runtime_fault": 100.0})], now=NOW,
    )
    candidates = [
        RecoveryCandidate("wide", ("runtime_fault",), 4, 0.2, True,
                          "restore previous runtime", ("current failure confirmed",),
                          ("health", "mcp", "shard operation")),
        RecoveryCandidate("narrow", ("runtime_fault",), 1, 0.4, True,
                          "restore previous mount config", ("mount fault localized",),
                          ("health", "mcp", "shard operation")),
        RecoveryCandidate("unsafe", ("runtime_fault",), 1, 0.0, False,
                          None, ("failure confirmed",), ("health",)),
    ]

    selected = choose_recovery(
        candidates, score, minimum_confidence_by_hypothesis={"runtime_fault": 0.8})
    assert selected is not None and selected.action_id == "narrow"
    assert choose_recovery(candidates, score,
                           minimum_confidence_by_hypothesis={"runtime_fault": 0.99}) is None

    unrelated = score_hypotheses(
        {"runtime_fault": 0.95, "other": 0.05},
        [signal("unrelated", {"other": 2.0})], now=NOW,
    )
    assert choose_recovery(
        candidates, unrelated,
        minimum_confidence_by_hypothesis={"runtime_fault": 0.9},
    ) is None


def test_post_validation_is_unknown_until_every_check_passes():
    assert verify_recovery({}, observed_at=NOW.isoformat(), source="probe",
                           provenance={}, ttl_s=60, now=NOW).state == RouteState.UNKNOWN
    assert verify_recovery({"health": True, "mcp": True},
                           observed_at=NOW.isoformat(), source="probe",
                           provenance={"request_id": "after"}, ttl_s=60,
                           now=NOW).state == RouteState.GREEN
    assert verify_recovery({"health": True, "mcp": False},
                           observed_at=NOW.isoformat(), source="probe",
                           provenance={}, ttl_s=60, now=NOW).state == RouteState.RED


def test_delta_suppresses_unchanged_state_and_reports_transitions():
    prior = resolve_routes([probe("edge-a"), probe("space-b", False, False)],
                           ("edge-a", "space-b"), now=NOW)
    unchanged = resolve_routes([probe("edge-a", age_s=10), probe("space-b", False, False,
                                                              age_s=10)],
                               ("edge-a", "space-b"), now=NOW)
    assert route_delta(prior, unchanged) == {}

    recovered = resolve_routes([probe("edge-a"), probe("space-b")],
                                ("edge-a", "space-b"), now=NOW)
    delta = route_delta(prior, recovered)
    assert [item["route_id"] for item in delta["resolved"]] == ["space-b"]

    disappeared = route_delta(prior, {"edge-a": prior["edge-a"]})
    assert disappeared["disappeared"][0]["route_id"] == "space-b"
    assert disappeared["disappeared"][0]["source"] == "current-sweep"
    assert disappeared["disappeared"][0]["freshness"] == "fresh"


def test_stale_previous_route_is_unknown_and_stale_new_state_never_carries_forward():
    observed_at = (NOW - timedelta(hours=1)).isoformat()
    stale_prior = {"route-z": RouteAssertion(
        "route-z", RouteState.RED, "old failure", observed_at,
        "old-probe", {"record": "expired"}, "stale", 3600, 30,
    )}
    current = resolve_routes([probe("route-z")], ("route-z",), now=NOW)
    assert route_delta(stale_prior, current)["changed"][0]["before"] == RouteState.UNKNOWN

    stale_current = {"route-z": RouteAssertion(
        "route-z", RouteState.RED, "expired failure", observed_at,
        "old-probe", {"record": "expired"}, "stale", 3600, 30,
    )}
    delta = route_delta(None, stale_current)
    assert delta["added"][0]["state"] == RouteState.UNKNOWN
    assert delta["unknown"][0]["state"] == RouteState.UNKNOWN
    assert "unreachable" not in delta


def test_shards_status_adapter_uses_current_payload_provenance_and_ttl():
    payload = {"checked_utc": NOW.isoformat(), "routes": [
        {"route": "route-x", "host": "x.invalid", "health": "ok", "mcp": "ok",
         "status": "GREEN", "checked_utc": NOW.isoformat(),
         "fault_domains": ["region-x"]},
        {"route": "route-y", "host": "y.invalid", "health": "origin_503",
         "mcp": "origin_503", "status": "RED", "checked_utc": NOW.isoformat()},
        {"route": "route-z", "host": "z.invalid", "health": "timeout",
         "mcp": "ok", "status": "YELLOW", "checked_utc": NOW.isoformat()},
    ]}
    probes = route_probes_from_status_payload(payload, ttl_s=120)
    routes = resolve_routes(probes, ("route-x", "route-y", "route-z"), now=NOW)

    assert routes["route-x"].state == RouteState.GREEN
    assert routes["route-x"].fault_domains == ("region-x",)
    assert routes["route-y"].state == RouteState.RED
    assert routes["route-y"].source == "shards_status"
    assert routes["route-y"].observed_at == NOW.isoformat()
    assert routes["route-z"].state == RouteState.RED
    assert "health" in routes["route-z"].reason


def test_provider_resolution_is_per_run_and_failures_stay_unknown():
    class Provider:
        name = "dynamic-source"

        def resolve(self, now):
            return [signal("current", {"runtime_fault": 2}, domain="provider")]

    class BrokenProvider:
        name = "unreachable-source"

        def resolve(self, now):
            raise TimeoutError("details intentionally not copied")

    signals, providers = resolve_live_evidence([Provider(), BrokenProvider()], now=NOW)
    assert [item.signal_id for item in signals] == ["current"]
    assert providers[0].state == RouteState.GREEN
    assert providers[1].state == RouteState.UNKNOWN
    assert providers[1].provenance == {"resolution_error": "TimeoutError"}

    class StaleProvider:
        name = "stale-source"

        def resolve(self, now):
            return [signal("old", {"runtime_fault": 3}, age_s=61, ttl_s=60)]

    _, stale_observation = resolve_live_evidence([StaleProvider()], now=NOW)
    assert stale_observation[0].state == RouteState.UNKNOWN
    assert stale_observation[0].provenance["stale_count"] == 1


def test_capability_graph_discovers_each_run_and_missing_capability_is_unknown():
    class DynamicProvider:
        name = "replaceable-adapter"
        active = True

        def discover(self, now):
            if not self.active:
                return []
            return [CapabilityProbe(
                "arbitrary.capability", True, now.isoformat(), "probe-v1",
                {"request_id": "current"}, 60,
            )]

    provider = DynamicProvider()
    current = resolve_capability_graph([provider], now=NOW)
    assert current.capabilities["arbitrary.capability"].state == RouteState.GREEN
    assert current.capabilities["arbitrary.capability"].callable is True

    provider.active = False
    absent = resolve_capability_graph(
        [provider], expected=("arbitrary.capability",), now=NOW + timedelta(seconds=1))
    assertion = absent.capabilities["arbitrary.capability"]
    assert assertion.state == RouteState.UNKNOWN
    assert assertion.callable is False
    assert assertion.freshness == "missing"


def test_capability_dependencies_gate_callability_and_map_fault_domains():
    graph = resolve_capability_graph([
        type("Provider", (), {"name": "adapter", "discover": lambda self, now: [
            CapabilityProbe("transport", False, now.isoformat(), "probe",
                            {"check": "transport"}, 60, fault_domains=("network",)),
            CapabilityProbe("search", True, now.isoformat(), "probe",
                            {"check": "search"}, 60, requires=("transport",)),
        ]})(),
    ], protocol_version="2", now=NOW)
    assert graph.capabilities["transport"].state == RouteState.RED
    assert graph.capabilities["search"].state == RouteState.RED
    assert graph.capabilities["search"].callable is False
    assert graph.fault_domains["network"] == ("transport",)
    assert graph.normalized_decision_payload()["protocol_version"] == "2"


def test_capability_dependency_failures_propagate_transitively():
    probes = [
        CapabilityProbe("a.entry", True, NOW.isoformat(), "probe", {}, 60,
                        requires=("b.middle",)),
        CapabilityProbe("b.middle", True, NOW.isoformat(), "probe", {}, 60,
                        requires=("z.transport",)),
        CapabilityProbe("z.transport", False, NOW.isoformat(), "probe", {}, 60),
    ]
    provider = type("Provider", (), {
        "name": "adapter", "discover": lambda self, now: probes,
    })()

    graph = resolve_capability_graph([provider], now=NOW)

    assert graph.capabilities["z.transport"].state == RouteState.RED
    assert graph.capabilities["b.middle"].state == RouteState.RED
    assert graph.capabilities["a.entry"].state == RouteState.RED
    assert graph.capabilities["a.entry"].callable is False


def test_equivalent_runtime_graph_is_deterministic_across_adapter_names():
    observation = CapabilityProbe(
        "capability.alpha", True, NOW.isoformat(), "portable-probe",
        {"request_id": "fixture-1"}, 60, requires=(), fault_domains=("domain-x",),
    )

    class Adapter:
        def __init__(self, name):
            self.name = name

        def discover(self, now):
            return [observation]

    graph_a = resolve_capability_graph([Adapter("adapter-a")],
                                       protocol_version="1", now=NOW)
    graph_b = resolve_capability_graph([Adapter("adapter-b")],
                                       protocol_version="1", now=NOW)
    assert graph_a.normalized_decision_payload() == graph_b.normalized_decision_payload()
    assert graph_a.decision_hash == graph_b.decision_hash


def test_capability_graph_rejects_stale_and_conflicting_observations():
    stale_probe = CapabilityProbe(
        "stale.capability", True, (NOW - timedelta(seconds=61)).isoformat(),
        "probe", {"fixture": "stale"}, 60,
    )
    conflict_a = CapabilityProbe(
        "conflict.capability", True, NOW.isoformat(), "probe-a", {"fixture": "a"}, 60,
    )
    conflict_b = CapabilityProbe(
        "conflict.capability", False, NOW.isoformat(), "probe-b", {"fixture": "b"}, 60,
    )
    provider = type("Provider", (), {
        "name": "adapter", "discover": lambda self, now: [stale_probe, conflict_a, conflict_b],
    })()
    graph = resolve_capability_graph([provider], now=NOW)
    assert graph.capabilities["stale.capability"].state == RouteState.UNKNOWN
    assert graph.capabilities["stale.capability"].freshness == "stale"
    assert graph.capabilities["conflict.capability"].state == RouteState.UNKNOWN
    assert graph.capabilities["conflict.capability"].provenance[
        "resolution"] == "conflicting fresh provider observations"


def test_persistence_hooks_are_explicit_isolated_and_tracker_stays_separate():
    class Sink:
        def persist(self, record):
            return True

    class BrokenSink:
        def persist(self, record):
            raise OSError("backend unavailable")

    result = persist_resilience_record(
        {"state": "GREEN"},
        PersistenceHooks(shards=Sink(), relay=BrokenSink(), tracker=None),
        now=NOW, meaningful_change=True,
    )
    assert result["shards"]["state"] == "GREEN"
    assert result["shards"]["observed_at"] == NOW.isoformat()
    assert result["shards"]["freshness"] == "fresh"
    assert result["relay"]["state"] == RouteState.UNKNOWN
    assert result["relay"]["provenance"] == {"adapter_error": "OSError"}
    assert result["nougenmsg"]["state"] == RouteState.UNKNOWN
    assert result["tracker"]["provenance"] == {"adapter": "unconfigured"}


def test_relay_and_message_writes_are_suppressed_without_meaningful_delta():
    class Sink:
        def __init__(self):
            self.calls = 0

        def persist(self, record):
            self.calls += 1
            return True

    relay, message = Sink(), Sink()
    result = persist_resilience_record(
        {"state": "GREEN"}, PersistenceHooks(relay=relay, nougenmsg=message), now=NOW)
    assert relay.calls == 0 and message.calls == 0
    assert result["relay"]["status"] == "suppressed"
    assert result["nougenmsg"]["status"] == "suppressed"


def test_no_route_or_tenant_defaults_are_required():
    routes = resolve_routes([], (), now=NOW)
    assert routes == {}
    arbitrary = resolve_routes([probe("arbitrary-route-17")],
                               ("arbitrary-route-17",), now=NOW)
    assert tuple(arbitrary) == ("arbitrary-route-17",)


def test_equivalent_normalized_inputs_have_same_decision_hash_across_nodes():
    common = {
        "protocol_version": "1", "schema_version": "1",
        "normalized_input": {"capabilities": ["health", "mcp"], "evidence": "fresh"},
        "capability_graph": {"routes": ["route-a"], "providers": ["probe-v1"]},
        "evidence": [{"source": "probe-v1", "freshness": "fresh",
                       "observed_at": NOW.isoformat(), "provenance": {"request": 7}}],
        "policy_version": "p1", "policy": {"minimum": 0.8, "ttl_s": 60},
        "decision": {"state": "GREEN", "action": "none"},
        "observed_at": NOW,
    }
    node_a = build_proof_receipt(**common)
    node_b = build_proof_receipt(**{
        **common,
        "normalized_input": dict(reversed(list(common["normalized_input"].items()))),
        "capability_graph": dict(reversed(list(common["capability_graph"].items()))),
    })
    assert node_a["decision_hash"] == node_b["decision_hash"]
    assert node_a["normalized_input_hash"] == node_b["normalized_input_hash"]
    assert node_a["receipt_hash"] == node_b["receipt_hash"]
    assert len(node_a["receipt_hash"]) == 64
