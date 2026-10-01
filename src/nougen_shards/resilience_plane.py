"""Provider-neutral, evidence-weighted resilience decisions.

This module is deliberately pure: adapters resolve live observations and
persist records through explicit hooks. It never probes, restarts, deploys, or
infers a failed parent from a failed child.
"""
from __future__ import annotations

import math
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence

CLOCK_SKEW_TOLERANCE_S = 5.0


class RouteState(str, Enum):
    GREEN = "GREEN"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


def _parse_time(value: Optional[str | datetime]) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _now(value: Optional[datetime]) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    return current.astimezone(timezone.utc)


def _freshness(observed_at: Optional[str | datetime], ttl_s: float,
               now: datetime) -> tuple[str, Optional[float], float]:
    if not isinstance(ttl_s, (int, float)) or not math.isfinite(ttl_s) or ttl_s <= 0:
        return "unknown", None, 0.0
    parsed = _parse_time(observed_at)
    if parsed is None:
        return "unknown", None, 0.0
    age_s = (now - parsed).total_seconds()
    if age_s < -CLOCK_SKEW_TOLERANCE_S:
        return "unknown", age_s, 0.0
    age_s = max(0.0, age_s)
    if age_s > ttl_s:
        return "stale", age_s, 0.0
    return "fresh", age_s, max(0.0, 1.0 - age_s / ttl_s)


@dataclass(frozen=True)
class RouteProbe:
    route_id: str
    health_ok: Optional[bool]
    mcp_ok: Optional[bool]
    expected: Optional[bool]
    observed_at: Optional[str]
    source: str
    provenance: Mapping[str, Any]
    ttl_s: float
    fault_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouteAssertion:
    route_id: str
    state: str
    reason: str
    observed_at: Optional[str]
    source: str
    provenance: Mapping[str, Any]
    freshness: str
    age_s: Optional[float]
    ttl_s: float
    fault_domains: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_route(probe: RouteProbe, *, now: Optional[datetime] = None) -> RouteAssertion:
    """Classify one expected route using only its fresh direct health and MCP probes."""
    current = _now(now)
    freshness, age_s, _ = _freshness(probe.observed_at, probe.ttl_s, current)
    state, reason = RouteState.UNKNOWN, "insufficient current route evidence"
    if freshness != "fresh":
        reason = f"{freshness} route evidence"
    elif probe.expected is not True:
        reason = "route is not confirmed expected to serve"
    elif probe.health_ok is False or probe.mcp_ok is False:
        failed = [name for name, ok in (("health", probe.health_ok), ("mcp", probe.mcp_ok))
                  if ok is False]
        state, reason = RouteState.RED, f"direct route probe failed: {', '.join(failed)}"
    elif probe.health_ok is True and probe.mcp_ok is True:
        state, reason = RouteState.GREEN, "health and MCP verified"
    return RouteAssertion(
        route_id=probe.route_id, state=state, reason=reason,
        observed_at=probe.observed_at, source=probe.source,
        provenance=dict(probe.provenance), freshness=freshness, age_s=age_s,
        ttl_s=probe.ttl_s, fault_domains=tuple(probe.fault_domains),
    )


def resolve_routes(probes: Iterable[RouteProbe], expected_routes: Sequence[str], *,
                   now: Optional[datetime] = None) -> dict[str, RouteAssertion]:
    """Resolve the newest observation for every expected route; missing stays UNKNOWN."""
    current = _now(now)
    latest: dict[str, tuple[datetime, RouteProbe]] = {}
    for probe in probes:
        observed = _parse_time(probe.observed_at) or datetime.min.replace(tzinfo=timezone.utc)
        prior = latest.get(probe.route_id)
        if prior is None or observed > prior[0]:
            latest[probe.route_id] = (observed, probe)

    expected = tuple(dict.fromkeys(route for route in expected_routes if route))
    result: dict[str, RouteAssertion] = {}
    for route_id in expected:
        entry = latest.get(route_id)
        if entry is None:
            result[route_id] = RouteAssertion(
                route_id=route_id, state=RouteState.UNKNOWN,
                reason="no observation in current sweep", observed_at=None,
                source="current-sweep", provenance={"observation": "missing"},
                freshness="missing", age_s=None, ttl_s=0.0,
            )
        else:
            result[route_id] = classify_route(entry[1], now=current)
    for route_id, (_, probe) in latest.items():
        if route_id not in result:
            result[route_id] = RouteAssertion(
                route_id=route_id, state=RouteState.UNKNOWN,
                reason="route is absent from the current expected-route set",
                observed_at=probe.observed_at, source=probe.source,
                provenance=dict(probe.provenance), freshness="unknown",
                age_s=None, ttl_s=probe.ttl_s,
                fault_domains=tuple(probe.fault_domains),
            )
    return result


def route_probes_from_status_payload(payload: Mapping[str, Any], *,
                                     ttl_s: float) -> list[RouteProbe]:
    """Adapt the live ``shards_status`` route schema without keeping old snapshots."""
    routes = payload.get("routes")
    if not isinstance(routes, Sequence) or isinstance(routes, (str, bytes)):
        return []

    def direct_result(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"ok", "healthy", "up", "green"}:
                return True
            if normalized in {"red", "down", "unavailable", "timeout", "error",
                              "failed", "unhealthy", "false", "origin_503"}:
                return False
        return None

    probes: list[RouteProbe] = []
    for route in routes:
        if not isinstance(route, Mapping) or not route.get("route"):
            continue
        checked_at = route.get("checked_utc") or payload.get("checked_utc")
        probes.append(RouteProbe(
            route_id=str(route["route"]),
            health_ok=direct_result(route.get("health")),
            mcp_ok=direct_result(route.get("mcp")),
            expected=route.get("expected", True),
            observed_at=str(checked_at) if checked_at else None,
            source=str(payload.get("source") or "shards_status"),
            provenance={
                "route": str(route["route"]),
                "host": route.get("host"),
                "reported_status": route.get("status"),
            },
            ttl_s=ttl_s,
            fault_domains=tuple(route.get("fault_domains") or ()),
        ))
    return probes


@dataclass(frozen=True)
class FederationAssertion:
    state: str
    redundancy: str
    expected_count: int
    serving_count: int
    red_count: int
    unknown_count: int
    serving_ratio: Optional[float]
    route_states: Mapping[str, str]
    fault_domains: Mapping[str, tuple[str, ...]]
    observed_at: str
    source: str
    freshness: str
    provenance: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_federation(routes: Mapping[str, RouteAssertion],
                         expected_routes: Sequence[str], *,
                         now: Optional[datetime] = None) -> FederationAssertion:
    """A serving child keeps federation GREEN; children alone cannot make it RED."""
    checked = _now(now)
    expected = tuple(dict.fromkeys(route for route in expected_routes if route))
    states = {
        route: (routes[route].state if routes[route].freshness == "fresh"
                else RouteState.UNKNOWN) if route in routes else RouteState.UNKNOWN
        for route in expected
    }
    serving = sum(state == RouteState.GREEN for state in states.values())
    red = sum(state == RouteState.RED for state in states.values())
    unknown = len(expected) - serving - red
    if serving:
        state = RouteState.GREEN
    elif expected and red == len(expected):
        state = RouteState.RED
    else:
        state = RouteState.UNKNOWN
    redundancy = "complete" if expected and serving == len(expected) else (
        "degraded" if serving else "unknown")
    domains: dict[str, list[str]] = {}
    for route in expected:
        assertion = routes.get(route)
        if assertion is None:
            continue
        for domain in assertion.fault_domains:
            domains.setdefault(domain, []).append(route)
    return FederationAssertion(
        state=state, redundancy=redundancy, expected_count=len(expected),
        serving_count=serving, red_count=red, unknown_count=unknown,
        serving_ratio=serving / len(expected) if expected else None,
        route_states=states,
        fault_domains={key: tuple(sorted(values)) for key, values in sorted(domains.items())},
        observed_at=checked.isoformat(), source="resilience-plane", freshness="fresh",
        provenance={"aggregation": "current expected route assertions"},
    )


def route_delta(previous: Optional[Mapping[str, RouteAssertion]],
                current: Mapping[str, RouteAssertion], *,
                now: Optional[datetime] = None) -> dict[str, list[dict[str, Any]]]:
    """Emit only route-state changes; repeated identical failures/unknowns are suppressed."""
    categories = {key: [] for key in
                  ("added", "changed", "resolved", "disappeared", "unreachable", "unknown")}
    before = previous or {}
    for route_id in sorted(set(before) | set(current)):
        old, new = before.get(route_id), current.get(route_id)
        if new is None:
            categories["disappeared"].append({
                "route_id": route_id,
                "before": (old.state if old and old.freshness == "fresh"
                           else RouteState.UNKNOWN if old else None),
                "observed_at": _now(now).isoformat(), "source": "current-sweep",
                "provenance": {"observation": "absent_from_current_sweep"},
                "freshness": "fresh",
            })
            continue
        old_state = old.state if old and old.freshness == "fresh" else RouteState.UNKNOWN
        new_state = new.state if new.freshness == "fresh" else RouteState.UNKNOWN
        current_record = new.to_dict()
        current_record["state"] = new_state
        if old is None:
            categories["added"].append(current_record)
        if old is not None and old_state != new_state:
            if old_state == RouteState.RED and new_state == RouteState.GREEN:
                categories["resolved"].append(current_record)
            else:
                categories["changed"].append({"route_id": route_id,
                                               "before": old_state, "after": new_state,
                                               "observed_at": new.observed_at,
                                               "source": new.source,
                                               "provenance": dict(new.provenance),
                                               "freshness": new.freshness})
        if new_state == RouteState.RED and old_state != RouteState.RED:
            categories["unreachable"].append(current_record)
        if new_state == RouteState.UNKNOWN and (old is None or old_state != RouteState.UNKNOWN):
            categories["unknown"].append(current_record)
    return {key: values for key, values in categories.items() if values}


@dataclass(frozen=True)
class EvidenceSignal:
    signal_id: str
    source: str
    provenance: Mapping[str, Any]
    observed_at: Optional[str]
    ttl_s: float
    fault_domain: str
    category: str
    reliability: float
    likelihood_ratios: Mapping[str, float]
    directly_verified: bool = False


@dataclass(frozen=True)
class EvidenceScore:
    probabilities: Mapping[str, float]
    used_signals: tuple[str, ...]
    supported_hypotheses: tuple[str, ...]
    stale_signals: tuple[str, ...]
    unknown_signals: tuple[str, ...]
    grouped_fault_domains: tuple[str, ...]
    observed_at: str
    source: str
    provenance: Mapping[str, Any]
    freshness: str
    evidence: tuple[Mapping[str, Any], ...]
    interpretation: str = "prioritization only; not proof"


def score_hypotheses(priors: Mapping[str, float], signals: Iterable[EvidenceSignal], *,
                     now: Optional[datetime] = None) -> EvidenceScore:
    """Bayesian ranking with TTL, source reliability and one update per fault domain."""
    checked = _now(now)
    if not priors or any(value < 0 or not math.isfinite(value) for value in priors.values()):
        raise ValueError("priors must contain finite non-negative probabilities")
    prior_total = sum(priors.values())
    if prior_total <= 0:
        raise ValueError("at least one prior must be positive")

    grouped: dict[str, dict[str, tuple[float, str]]] = {}
    used: list[str] = []
    supported: set[str] = set()
    stale: list[str] = []
    unknown: list[str] = []
    evidence_records: list[Mapping[str, Any]] = []
    for signal in signals:
        freshness, _, freshness_weight = _freshness(signal.observed_at, signal.ttl_s, checked)
        if freshness == "stale":
            stale.append(signal.signal_id)
            evidence_records.append(_signal_record(signal, freshness))
            continue
        if freshness != "fresh" or signal.reliability <= 0:
            unknown.append(signal.signal_id)
            evidence_records.append(_signal_record(signal, freshness))
            continue
        if not 0 <= signal.reliability <= 1:
            unknown.append(signal.signal_id)
            evidence_records.append(_signal_record(signal, "unknown"))
            continue
        used.append(signal.signal_id)
        evidence_records.append(_signal_record(signal, freshness))
        group = grouped.setdefault(signal.fault_domain, {})
        weight = signal.reliability * freshness_weight
        for hypothesis in priors:
            ratio = float(signal.likelihood_ratios.get(hypothesis, 1.0))
            if ratio <= 0 or not math.isfinite(ratio):
                continue
            contribution = math.log(ratio) * weight
            if contribution != 0:
                supported.add(hypothesis)
            prior = group.get(hypothesis)
            if prior is None or abs(contribution) > abs(prior[0]):
                group[hypothesis] = (contribution, signal.signal_id)

    log_weights: dict[str, float] = {}
    for hypothesis, prior in priors.items():
        if prior == 0:
            log_weights[hypothesis] = float("-inf")
            continue
        log_weights[hypothesis] = math.log(prior / prior_total) + sum(
            grouped[domain].get(hypothesis, (0.0, ""))[0]
            for domain in sorted(grouped))
    peak = max(log_weights.values())
    weights = {key: math.exp(value - peak) for key, value in log_weights.items()}
    total = sum(weights.values())
    probabilities = {key: value / total for key, value in weights.items()}
    return EvidenceScore(
        probabilities=probabilities, used_signals=tuple(sorted(used)),
        supported_hypotheses=tuple(sorted(supported)),
        stale_signals=tuple(sorted(stale)), unknown_signals=tuple(sorted(unknown)),
        grouped_fault_domains=tuple(sorted(grouped)),
        observed_at=checked.isoformat(), source="resilience-plane", freshness="fresh",
        provenance={"used_signals": sorted(used), "stale_signals": sorted(stale),
                    "unknown_signals": sorted(unknown)},
        evidence=tuple(sorted(evidence_records, key=lambda item: str(item["signal_id"]))),
    )


def _signal_record(signal: EvidenceSignal, freshness: str) -> Mapping[str, Any]:
    return {
        "signal_id": signal.signal_id,
        "source": signal.source,
        "provenance": dict(signal.provenance),
        "observed_at": signal.observed_at,
        "freshness": freshness,
        "fault_domain": signal.fault_domain,
        "category": signal.category,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("proof timestamps must include a timezone")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_jsonable(item) for item in value), key=lambda item: _canonical_json(item))
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("proof values must be finite")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported proof value: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def build_proof_receipt(*, protocol_version: str, schema_version: str,
                        normalized_input: Mapping[str, Any],
                        capability_graph: Mapping[str, Any],
                        evidence: Sequence[Mapping[str, Any]],
                        policy_version: str, policy: Mapping[str, Any],
                        decision: Mapping[str, Any], observed_at: datetime,
                        confidence: Optional[Mapping[str, float]] = None,
                        planned_mutations: Sequence[Mapping[str, Any]] = (),
                        executed_mutations: Sequence[Mapping[str, Any]] = (),
                        validation_results: Sequence[Mapping[str, Any]] = (),
                        previous_receipt_hash: Optional[str] = None) -> dict[str, Any]:
    """Build a portable proof envelope around a deterministic decision payload.

    ``decision_hash`` excludes observation-envelope fields, so equivalent
    normalized inputs and policy remain replayable across heterogeneous nodes.
    """
    when = _now(observed_at).isoformat()
    normalized = _jsonable(normalized_input)
    capabilities = _jsonable(capability_graph)
    normalized_evidence = [_jsonable(item) for item in evidence]
    normalized_policy = _jsonable(policy)
    normalized_decision = _jsonable(decision)
    normalized_confidence = _jsonable(confidence or {})
    decision_payload = {
        "protocol_version": protocol_version,
        "schema_version": schema_version,
        "normalized_input_hash": _digest(normalized),
        "capability_graph_hash": _digest(capabilities),
        "evidence_hashes": sorted(_digest(item) for item in normalized_evidence),
        "policy_version": policy_version,
        "policy_hash": _digest(normalized_policy),
        "decision": normalized_decision,
        "confidence": normalized_confidence,
    }
    receipt = {
        **decision_payload,
        "decision_hash": _digest(decision_payload),
        "evidence": sorted(normalized_evidence,
                            key=lambda item: _canonical_json(item)),
        "planned_mutations": _jsonable(planned_mutations),
        "executed_mutations": _jsonable(executed_mutations),
        "validation_results": _jsonable(validation_results),
        "observed_at": when,
        "previous_receipt_hash": previous_receipt_hash,
    }
    receipt["receipt_hash"] = _digest(receipt)
    return receipt


def hostile_action_verified(signals: Iterable[EvidenceSignal], *,
                            minimum_independent_domains: int,
                            now: Optional[datetime] = None) -> bool:
    """Require multiple fresh, direct security indicators from distinct domains."""
    if minimum_independent_domains < 2:
        raise ValueError("hostile-action verification requires at least two independent domains")
    checked = _now(now)
    domains = {
        signal.fault_domain for signal in signals
        if signal.category == "security" and signal.directly_verified
        and 0 < signal.reliability <= 1
        and float(signal.likelihood_ratios.get("hostile_action", 1.0)) > 1.0
        and _freshness(signal.observed_at, signal.ttl_s, checked)[0] == "fresh"
    }
    return len(domains) >= minimum_independent_domains


@dataclass(frozen=True)
class RecoveryCandidate:
    action_id: str
    hypotheses: tuple[str, ...]
    affected_units: int
    risk: float
    reversible: bool
    rollback: Optional[str]
    preconditions: tuple[str, ...]
    post_validation: tuple[str, ...]


def choose_recovery(candidates: Iterable[RecoveryCandidate], score: EvidenceScore, *,
                    minimum_confidence_by_hypothesis: Mapping[str, float]) -> Optional[RecoveryCandidate]:
    """Propose the narrowest reversible action only when current evidence meets policy."""
    eligible: list[RecoveryCandidate] = []
    if not score.used_signals or not score.supported_hypotheses:
        return None
    for candidate in candidates:
        if (not candidate.reversible or not candidate.rollback
                or not candidate.preconditions or not candidate.post_validation
                or candidate.affected_units < 1 or not 0 <= candidate.risk <= 1):
            continue
        if any(hypothesis in score.supported_hypotheses
               and
            score.probabilities.get(hypothesis, 0.0)
            >= minimum_confidence_by_hypothesis.get(hypothesis, 2.0)
            for hypothesis in candidate.hypotheses
        ):
            eligible.append(candidate)
    return min(eligible, key=lambda c: (c.affected_units, c.risk, c.action_id),
               default=None)


@dataclass(frozen=True)
class RecoveryVerification:
    state: str
    checks: Mapping[str, Optional[bool]]
    observed_at: str
    source: str
    provenance: Mapping[str, Any]
    freshness: str
    age_s: Optional[float]


def verify_recovery(checks: Mapping[str, Optional[bool]], *, observed_at: str,
                    source: str, provenance: Mapping[str, Any], ttl_s: float,
                    now: Optional[datetime] = None) -> RecoveryVerification:
    """Record post-validation; missing checks remain UNKNOWN, never success."""
    checked = _now(now)
    freshness, age_s, _ = _freshness(observed_at, ttl_s, checked)
    if freshness != "fresh":
        state = RouteState.UNKNOWN
    elif checks and all(result is True for result in checks.values()):
        state = RouteState.GREEN
    elif any(result is False for result in checks.values()):
        state = RouteState.RED
    else:
        state = RouteState.UNKNOWN
    return RecoveryVerification(state, dict(checks), observed_at, source,
                                dict(provenance), freshness, age_s)


class EvidenceProvider(Protocol):
    name: str

    def resolve(self, now: datetime) -> Sequence[EvidenceSignal]: ...


@dataclass(frozen=True)
class ProviderObservation:
    provider: str
    state: str
    observed_at: str
    provenance: Mapping[str, Any]
    freshness: str


@dataclass(frozen=True)
class CapabilityProbe:
    """One provider's current observation about one declared capability."""

    capability_id: str
    available: Optional[bool]
    observed_at: Optional[str]
    source: str
    provenance: Mapping[str, Any]
    ttl_s: float
    requires: tuple[str, ...] = ()
    fault_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityAssertion:
    capability_id: str
    state: str
    callable: bool
    requires: tuple[str, ...]
    observed_at: Optional[str]
    source: str
    provenance: Mapping[str, Any]
    freshness: str
    age_s: Optional[float]
    ttl_s: float
    fault_domains: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityGraphSnapshot:
    """Transient per-sweep decision view; it is not a persisted capability registry."""
    protocol_version: str
    observed_at: str
    capabilities: Mapping[str, CapabilityAssertion]
    providers: tuple[ProviderObservation, ...]
    expected: tuple[str, ...]
    fault_domains: Mapping[str, tuple[str, ...]]

    def normalized_decision_payload(self) -> dict[str, Any]:
        """Portable state-machine input with host/provider metadata removed."""
        return {
            "protocol_version": self.protocol_version,
            "capabilities": [
                {
                    "capability_id": capability_id,
                    "state": assertion.state,
                    "callable": assertion.callable,
                    "requires": list(assertion.requires),
                    "fault_domains": list(assertion.fault_domains),
                }
                for capability_id, assertion in sorted(self.capabilities.items())
            ],
        }

    @property
    def decision_hash(self) -> str:
        return _digest(self.normalized_decision_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.normalized_decision_payload(),
            "observed_at": self.observed_at,
            "expected": list(self.expected),
            "providers": [asdict(provider) for provider in self.providers],
            "fault_domains": {key: list(value)
                              for key, value in sorted(self.fault_domains.items())},
            "evidence": {key: assertion.to_dict()
                         for key, assertion in sorted(self.capabilities.items())},
        }


class CapabilityProvider(Protocol):
    name: str

    def discover(self, now: datetime) -> Sequence[CapabilityProbe]: ...


def resolve_capability_graph(providers: Iterable[CapabilityProvider], *,
                             expected: Sequence[str] = (),
                             protocol_version: str = "1",
                             now: Optional[datetime] = None) -> CapabilityGraphSnapshot:
    """Discover capabilities on each run and derive a deterministic usable graph.

    Provider identity is retained only in the evidence envelope. State decisions
    use normalized capability ids, current observations, TTL, and declared
    dependencies; expected topology is supplied by the caller.
    """
    checked = _now(now)
    probes: dict[str, list[CapabilityProbe]] = {}
    observations: list[ProviderObservation] = []
    for provider in sorted(providers, key=lambda item: str(item.name)):
        try:
            current = list(provider.discover(checked))
        except Exception as exc:
            observations.append(ProviderObservation(
                provider=str(provider.name), state=RouteState.UNKNOWN,
                observed_at=checked.isoformat(),
                provenance={"resolution_error": type(exc).__name__}, freshness="fresh",
            ))
            continue
        provider_fresh = any(
            probe.available is True
            and _freshness(probe.observed_at, probe.ttl_s, checked)[0] == "fresh"
            for probe in current
        )
        observations.append(ProviderObservation(
            provider=str(provider.name),
            state=RouteState.GREEN if provider_fresh else RouteState.UNKNOWN,
            observed_at=checked.isoformat(),
            provenance={"capability_count": len(current)}, freshness="fresh",
        ))
        for probe in current:
            if probe.capability_id:
                probes.setdefault(probe.capability_id, []).append(probe)

    expected_set = set(filter(None, expected)) | set(probes)
    for candidates in probes.values():
        for probe in candidates:
            expected_set.update(filter(None, probe.requires))
    expected_ids = tuple(sorted(expected_set))
    assertions: dict[str, CapabilityAssertion] = {}
    direct_states: dict[str, RouteState] = {}
    for capability_id in expected_ids:
        candidates = probes.get(capability_id, [])
        if not candidates:
            assertions[capability_id] = CapabilityAssertion(
                capability_id, RouteState.UNKNOWN, False, (), None,
                "current-sweep", {"observation": "missing"}, "missing", None, 0.0,
            )
            direct_states[capability_id] = RouteState.UNKNOWN
            continue

        classified = [(probe, *_freshness(probe.observed_at, probe.ttl_s, checked))
                      for probe in candidates]
        fresh = [(probe, age) for probe, freshness, age, _ in classified
                 if freshness == "fresh"]
        if not fresh:
            probe, freshness, age, _ = max(
                classified,
                key=lambda item: (_parse_time(item[0].observed_at)
                                  or datetime.min.replace(tzinfo=timezone.utc),
                                  item[0].source),
            )
            assertions[capability_id] = CapabilityAssertion(
                capability_id, RouteState.UNKNOWN, False,
                tuple(sorted(set(probe.requires))), probe.observed_at,
                probe.source, dict(probe.provenance), freshness, age, probe.ttl_s,
                tuple(sorted(set(probe.fault_domains))),
            )
            direct_states[capability_id] = RouteState.UNKNOWN
            continue

        availability = {probe.available for probe, _ in fresh}
        requirements = {tuple(sorted(set(probe.requires))) for probe, _ in fresh}
        if len(availability) != 1 or len(requirements) != 1:
            state = RouteState.UNKNOWN
            reason = "conflicting fresh provider observations"
            required = tuple(sorted(set().union(*(set(item) for item in requirements))))
        else:
            available = next(iter(availability))
            state = (RouteState.GREEN if available is True else
                     RouteState.RED if available is False else RouteState.UNKNOWN)
            reason = "current provider observations agree"
            required = next(iter(requirements))
        latest_probe, _ = max(
            fresh,
            key=lambda item: (_parse_time(item[0].observed_at)
                              or datetime.min.replace(tzinfo=timezone.utc),
                              item[0].source),
        )
        evidence = sorted(({
            "source": probe.source, "observed_at": probe.observed_at,
            "provenance": dict(probe.provenance), "freshness": "fresh",
        } for probe, _ in fresh), key=_canonical_json)
        assertions[capability_id] = CapabilityAssertion(
            capability_id, state, state == RouteState.GREEN, required,
            latest_probe.observed_at, latest_probe.source,
            {"resolution": reason, "observations": evidence}, "fresh",
            max(age for _, age in fresh if age is not None),
            min(probe.ttl_s for probe, _ in fresh),
            tuple(sorted({domain for probe, _ in fresh
                          for domain in probe.fault_domains})),
        )
        direct_states[capability_id] = state

    # Propagate dependency state through the graph. A single pass would miss
    # transitive failures when a dependent appears earlier in sorted order.
    resolved_states = dict(direct_states)
    for _ in range(len(expected_ids) + 1):
        changed = False
        for capability_id in expected_ids:
            if direct_states[capability_id] != RouteState.GREEN:
                continue
            dependencies = [resolved_states.get(required, RouteState.UNKNOWN)
                            for required in assertions[capability_id].requires]
            if any(state == RouteState.RED for state in dependencies):
                state = RouteState.RED
            elif any(state != RouteState.GREEN for state in dependencies):
                state = RouteState.UNKNOWN
            else:
                state = RouteState.GREEN
            if resolved_states[capability_id] != state:
                resolved_states[capability_id] = state
                changed = True
        if not changed:
            break

    for capability_id, assertion in assertions.items():
        state = resolved_states[capability_id]
        assertions[capability_id] = CapabilityAssertion(
            **{**assertion.to_dict(), "state": state,
               "callable": state == RouteState.GREEN}
        )

    domains: dict[str, list[str]] = {}
    for capability_id, assertion in assertions.items():
        for domain in assertion.fault_domains:
            domains.setdefault(domain, []).append(capability_id)
    return CapabilityGraphSnapshot(
        protocol_version=protocol_version, observed_at=checked.isoformat(),
        capabilities=assertions,
        providers=tuple(sorted(observations, key=lambda item: item.provider)),
        expected=expected_ids,
        fault_domains={key: tuple(sorted(values)) for key, values in sorted(domains.items())},
    )


def resolve_live_evidence(providers: Iterable[EvidenceProvider], *,
                          now: Optional[datetime] = None
                          ) -> tuple[list[EvidenceSignal], list[ProviderObservation]]:
    """Ask each injected source on every call and isolate failures as UNKNOWN."""
    checked = _now(now)
    signals: list[EvidenceSignal] = []
    observations: list[ProviderObservation] = []
    for provider in providers:
        try:
            current = list(provider.resolve(checked))
        except Exception as exc:
            observations.append(ProviderObservation(
                provider=provider.name, state=RouteState.UNKNOWN,
                observed_at=checked.isoformat(),
                provenance={"resolution_error": type(exc).__name__}, freshness="fresh",
            ))
            continue
        signals.extend(current)
        current_states = [
            _freshness(signal.observed_at, signal.ttl_s, checked)[0]
            for signal in current
        ]
        fresh_count = current_states.count("fresh")
        observations.append(ProviderObservation(
            provider=provider.name,
            state=RouteState.GREEN if fresh_count else RouteState.UNKNOWN,
            observed_at=checked.isoformat(),
            provenance={"signal_count": len(current), "fresh_count": fresh_count,
                        "stale_count": current_states.count("stale"),
                        "unknown_count": current_states.count("unknown")},
            freshness="fresh",
        ))
    return signals, observations


class PersistenceHook(Protocol):
    def persist(self, record: Mapping[str, Any]) -> bool: ...


@dataclass(frozen=True)
class PersistenceHooks:
    shards: Optional[PersistenceHook] = None
    relay: Optional[PersistenceHook] = None
    nougenmsg: Optional[PersistenceHook] = None
    tracker: Optional[PersistenceHook] = None


def persist_resilience_record(record: Mapping[str, Any], hooks: PersistenceHooks, *,
                              now: Optional[datetime] = None,
                              meaningful_change: bool = False,
                              ) -> dict[str, dict[str, Any]]:
    """Persist through explicit adapters; relay/message writes require a real delta."""
    checked = _now(now).isoformat()
    results: dict[str, dict[str, Any]] = {}
    for name in ("shards", "relay", "nougenmsg", "tracker"):
        hook = getattr(hooks, name)
        if name in {"relay", "nougenmsg"} and not meaningful_change:
            results[name] = {"state": RouteState.UNKNOWN, "status": "suppressed",
                             "observed_at": checked, "source": name,
                             "provenance": {"reason": "no meaningful delta or action"},
                             "freshness": "unknown"}
            continue
        if hook is None:
            results[name] = {"state": RouteState.UNKNOWN, "observed_at": checked,
                             "source": name, "provenance": {"adapter": "unconfigured"},
                             "freshness": "unknown"}
            continue
        try:
            succeeded = hook.persist(record)
            results[name] = {
                "state": "GREEN" if succeeded else RouteState.UNKNOWN,
                "observed_at": checked, "source": name,
                "provenance": {"adapter": "explicit_plugin",
                               "confirmed": bool(succeeded)},
                "freshness": "fresh" if succeeded else "unknown",
            }
        except Exception as exc:
            results[name] = {"state": RouteState.UNKNOWN, "observed_at": checked,
                             "source": name,
                             "provenance": {"adapter_error": type(exc).__name__},
                             "freshness": "unknown"}
    return results
