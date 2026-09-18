"""Deterministic building blocks for the Retrieval Engine v2 rollout.

This module is intentionally dependency-free: query planning and rank fusion
can be adopted by existing recall surfaces before optional model lanes exist.
"""
from __future__ import annotations

import re
import unicodedata
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence, get_args
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CanonicalEntity:
    id: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalIntent:
    query_original: str
    query_normalized: str
    intent: str
    scope: str
    metric: str | None
    period: str | None
    year: int | None
    timezone: str
    required_entities: tuple[str, ...] = ()
    canonical_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactCandidate:
    id: str
    lane: str
    rank: int
    payload: Mapping[str, Any] = field(default_factory=dict)


class RecoveryAction(str, Enum):
    CONTINUE_FEDERATION = "CONTINUE_FEDERATION"
    TRACE_PROVENANCE = "TRACE_PROVENANCE"
    REFRESH_CANONICAL = "REFRESH_CANONICAL"
    EXPAND_RETRIEVAL = "EXPAND_RETRIEVAL"
    DRIFT_RECURSE = "DRIFT_RECURSE"
    REPARTITION_QUERY = "REPARTITION_QUERY"
    FAILOVER = "FAILOVER"
    RECONCILE = "RECONCILE"
    FOLLOW_SUPERSESSION = "FOLLOW_SUPERSESSION"
    STOP_WITH_EXPLICIT_STATE = "STOP_WITH_EXPLICIT_STATE"


@dataclass(frozen=True)
class QueryFlags:
    """Orthogonal properties; axes below remain the authoritative state."""

    observed: bool | None = None
    complete: bool | None = None
    canonical: bool | None = None
    validated: bool | None = None
    reconciled: bool | None = None
    estimated: bool | None = None
    stale: bool | None = None
    partial: bool | None = None
    conflicted: bool | None = None
    superseded: bool | None = None
    missing_expected_nodes: bool = False
    missing_expected_entities: bool = False
    missing_expected_dates: bool = False
    provenance_incomplete: bool = False
    retryable: bool = False
    recoverable: bool = False
    traceable: bool = False
    deeper_search_available: bool = False
    failover_available: bool = False
    continuation_available: bool = False
    exact_source_available: bool = False
    exact: bool | None = None
    current: bool | None = None


@dataclass(frozen=True)
class QueryCoverage:
    complete: bool
    expected_nodes: tuple[str, ...] = ()
    observed_nodes: tuple[str, ...] = ()

    @property
    def missing_nodes(self) -> tuple[str, ...]:
        observed = set(self.observed_nodes)
        return tuple(node for node in self.expected_nodes if node not in observed)


Availability = Literal[
    "AVAILABLE", "UNAVAILABLE", "UNKNOWN", "UNREACHABLE", "DEGRADED", "INTERMITTENT", "TIMEOUT",
    "RATE_LIMITED", "AUTH_FAILED", "PERMISSION_DENIED", "CIRCUIT_OPEN", "MAINTENANCE",
]
Observation = Literal[
    "OBSERVED", "UNOBSERVED", "UNREAD", "DEFERRED", "SKIPPED", "DISCOVERED", "REQUESTED", "FETCHED",
    "PARSED", "INDEXED",
]
Completeness = Literal[
    "COMPLETE", "PARTIAL", "EMPTY", "TRUNCATED", "PAGINATED", "EXHAUSTED", "INDETERMINATE",
    "COVERAGE_UNKNOWN", "UNKNOWN",
]
Freshness = Literal[
    "LIVE", "CURRENT", "FRESH", "AGING", "STALE", "EXPIRED", "SUPERSEDED", "FUTURE_DATED",
    "LATE_ARRIVING", "UNKNOWN",
]
TruthQuality = Literal[
    "EXACT", "OBSERVED_EXACT", "ESTIMATED", "DERIVED", "INFERRED", "RECONCILED", "PROJECTED",
    "APPROXIMATE", "UNKNOWN", "DISPUTED", "CONTRADICTED",
]
Validation = Literal[
    "VALID", "UNVALIDATED", "VALIDATING", "INVALID", "SCHEMA_MISMATCH", "CHECKSUM_MISMATCH",
    "RANGE_INVALID", "SEMANTICALLY_INVALID", "DUPLICATE", "POSSIBLE_DUPLICATE",
]
Canonicality = Literal[
    "CANONICAL", "NON_CANONICAL", "CANDIDATE", "HISTORICAL", "SUPERSEDED", "AMENDED", "RETRACTED",
    "ORPHANED", "CURRENT", "UNKNOWN",
]
Computation = Literal[
    "RAW", "NORMALIZED", "AGGREGATED", "MATERIALIZED", "CACHED", "RECOMPUTED", "RECONCILED",
    "ESTIMATED", "BACKFILLED",
]
Provenance = Literal[
    "PROVEN", "TRACEABLE", "PARTIALLY_TRACEABLE", "SOURCE_MISSING", "SOURCE_UNAVAILABLE", "UNVERIFIED",
    "ORPHANED",
]
Federation = Literal[
    "FEDERATION_COMPLETE", "FEDERATION_PARTIAL", "NODE_MISSING", "NODE_DEFERRED", "NODE_FAILED",
    "NODE_STALE", "NODE_DIVERGED", "FAILOVER_ACTIVE", "FAILOVER_EXHAUSTED",
]
Retrieval = Literal[
    "EXACT_HIT", "CANONICAL_HIT", "LEXICAL_HIT", "SEMANTIC_HIT", "GRAPH_HIT", "HYBRID_HIT", "RERANKED",
    "RECURSIVE_HIT", "FALLBACK_HIT", "CACHE_HIT", "NO_HIT", "HIT", "ERROR", "NOT_RUN",
]
Conflict = Literal[
    "CONSISTENT", "CONFLICTED", "DIVERGENT", "AMBIGUOUS", "MULTIPLE_CANDIDATES", "RESOLVED_BY_RECENCY",
    "RESOLVED_BY_PROVENANCE", "RESOLVED_BY_CANONICALITY", "UNRESOLVED", "CLEAR", "UNKNOWN",
]
Execution = Literal[
    "PENDING", "RUNNING", "RETRYING", "BACKING_OFF", "FAILING_OVER", "COMPLETE", "FAILED", "CANCELLED",
    "BUDGET_EXHAUSTED",
]
Pagination = Literal[
    "NOT_REQUIRED", "ACTIVE", "CONTINUATION_AVAILABLE", "EXHAUSTED", "STALLED", "LOOP_DETECTED",
    "CURSOR_INVALID", "COMPLETE", "CONTINUING", "NOT_APPLICABLE",
]
Anomaly = Literal[
    "NORMAL", "OUTLIER", "SPIKE", "DROP", "GAP", "COUNTER_RESET", "NEGATIVE_DELTA", "DUPLICATE_COHORT",
    "IDENTITY_DRIFT", "CLOCK_DRIFT", "IMPOSSIBLE_VALUE",
]
Confidence = Literal["CERTAIN", "HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]

_AXIS_VALUES = {
    "availability": set(get_args(Availability)),
    "observation": set(get_args(Observation)),
    "completeness": set(get_args(Completeness)),
    "freshness": set(get_args(Freshness)),
    "truth_quality": set(get_args(TruthQuality)),
    "validation": set(get_args(Validation)),
    "canonicality": set(get_args(Canonicality)),
    "computation": set(get_args(Computation)),
    "provenance": set(get_args(Provenance)),
    "federation": set(get_args(Federation)),
    "retrieval": set(get_args(Retrieval)),
    "conflict": set(get_args(Conflict)),
    "execution": set(get_args(Execution)),
    "pagination": set(get_args(Pagination)),
    "anomaly": set(get_args(Anomaly)),
    "confidence": set(get_args(Confidence)),
}
_REASON_CODES = {
    "EXPECTED_NODE_NOT_QUERIED", "EXPECTED_ENTITY_MISSING", "EXPECTED_DATE_MISSING",
    "SUBREQUEST_BUDGET_EXHAUSTED", "LATENCY_BUDGET_EXHAUSTED", "TOKEN_BUDGET_EXHAUSTED",
    "NODE_TIMEOUT", "NODE_5XX", "AUTH_FAILURE", "RATE_LIMIT", "CURSOR_STALLED", "CURSOR_LOOP",
    "SOURCE_LATE", "SOURCE_STALE", "SOURCE_SUPERSEDED", "SOURCE_CONFLICT", "PROVENANCE_MISSING",
    "SNAPSHOT_STALE", "SNAPSHOT_INCOMPLETE", "CANONICAL_POINTER_MISSING", "CHECKSUM_FAILURE",
    "SCHEMA_VERSION_MISMATCH", "ALIAS_UNRESOLVED", "TEMPORAL_AMBIGUITY", "SCOPE_AMBIGUITY",
    "METRIC_AMBIGUITY", "RETRIEVAL_CONFIDENCE_LOW",
}


@dataclass(frozen=True)
class QueryState:
    """Machine-readable result state; prose is supplementary, never a control input."""

    status: str = "NOT_RUN"
    observation: Observation = "UNOBSERVED"
    completeness: Completeness = "UNKNOWN"
    conflict: Conflict = "UNKNOWN"
    freshness: Freshness = "UNKNOWN"
    retrieval: Retrieval = "NOT_RUN"
    pagination: Pagination = "NOT_APPLICABLE"
    availability: Availability = "UNKNOWN"
    truth_quality: TruthQuality = "UNKNOWN"
    validation: Validation = "UNVALIDATED"
    canonicality: Canonicality = "UNKNOWN"
    computation: Computation = "RAW"
    provenance: Provenance = "UNVERIFIED"
    federation: Federation = "FEDERATION_PARTIAL"
    execution: Execution = "PENDING"
    anomaly: Anomaly = "NORMAL"
    confidence: Confidence = "INSUFFICIENT"
    flags: QueryFlags = field(default_factory=QueryFlags)
    reason_codes: tuple[str, ...] = ()
    evidence: tuple[Mapping[str, Any], ...] = ()
    coverage: QueryCoverage = field(default_factory=lambda: QueryCoverage(False))
    canonical_key: str | None = None

    def __post_init__(self) -> None:
        _check_enum("status", self.status, {"NOT_RUN", "SUCCESS", "DEGRADED", "FAILURE"})
        for name, allowed in _AXIS_VALUES.items():
            _check_enum(name, getattr(self, name), allowed)
        if self.coverage.complete and self.completeness == "PARTIAL":
            raise ValueError("complete coverage conflicts with PARTIAL completeness")
        if self.completeness == "COMPLETE" and not self.coverage.complete:
            raise ValueError("COMPLETE completeness requires complete coverage")
        if self.flags.exact is True and self.truth_quality not in {"EXACT", "OBSERVED_EXACT"}:
            raise ValueError("exact flag requires an exact truth_quality")
        if self.flags.current is True and self.freshness in {"EXPIRED", "STALE", "FUTURE_DATED"}:
            raise ValueError("current flag conflicts with stale or expired freshness")
        if self.coverage.complete and self.coverage.missing_nodes:
            raise ValueError("complete coverage cannot have missing expected nodes")
        if any(
            not isinstance(code, str)
            or (code not in _REASON_CODES and not re.fullmatch(r"[a-z][a-z0-9_-]*\.[a-z][a-z0-9_.-]*", code))
            for code in self.reason_codes
        ):
            raise ValueError("reason_codes must be known machine codes or namespaced legacy codes")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["coverage"]["missing_nodes"] = list(self.coverage.missing_nodes)
        data["recovery"] = next_recovery_action(self).value
        return data


def _check_enum(name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        raise ValueError(f"invalid {name}: {value!r}")


def next_recovery_action(state: QueryState) -> RecoveryAction:
    """Select the first applicable recovery in the relay's fixed precedence."""
    flags = state.flags
    if (state.completeness in {"PARTIAL", "COVERAGE_UNKNOWN", "INDETERMINATE"}
            and (flags.missing_expected_nodes or flags.missing_expected_entities or flags.missing_expected_dates)
            and (flags.retryable or flags.recoverable)):
        return RecoveryAction.CONTINUE_FEDERATION
    if state.conflict in {"CONFLICTED", "DIVERGENT", "AMBIGUOUS", "MULTIPLE_CANDIDATES", "UNRESOLVED"} and flags.traceable:
        return RecoveryAction.TRACE_PROVENANCE
    if state.freshness in {"AGING", "STALE", "EXPIRED", "SUPERSEDED", "LATE_ARRIVING"} and state.canonical_key:
        return RecoveryAction.REFRESH_CANONICAL
    if state.retrieval == "NO_HIT" and not state.coverage.complete:
        return RecoveryAction.EXPAND_RETRIEVAL
    if state.retrieval == "NO_HIT" and state.coverage.complete and flags.deeper_search_available:
        return RecoveryAction.DRIFT_RECURSE
    if state.pagination in {"STALLED", "LOOP_DETECTED", "CURSOR_INVALID"}:
        return RecoveryAction.REPARTITION_QUERY
    if state.availability in {
        "TIMEOUT", "UNAVAILABLE", "UNREACHABLE", "RATE_LIMITED", "AUTH_FAILED", "PERMISSION_DENIED",
        "CIRCUIT_OPEN",
    } and flags.failover_available:
        return RecoveryAction.FAILOVER
    if state.truth_quality in {"ESTIMATED", "DERIVED", "INFERRED", "PROJECTED", "APPROXIMATE", "DISPUTED"} and flags.exact_source_available:
        return RecoveryAction.RECONCILE
    if state.canonicality in {"SUPERSEDED", "AMENDED", "RETRACTED", "ORPHANED"}:
        return RecoveryAction.FOLLOW_SUPERSESSION
    return RecoveryAction.STOP_WITH_EXPLICIT_STATE


@dataclass(frozen=True)
class ParsedTag:
    raw: str
    namespace: str | None
    value: str


_TAG_PART = re.compile(r"^[a-z][a-z0-9_-]*$")


def parse_tag(tag: str) -> ParsedTag:
    """Parse `namespace:value`; legacy/unrecognized free tags remain searchable."""
    value = tag.strip()
    if ":" in value:
        namespace, item = value.split(":", 1)
        if _TAG_PART.fullmatch(namespace) and item.strip():
            return ParsedTag(value, namespace, item.strip())
    return ParsedTag(value, None, value)


def index_tags(tags: Sequence[str]) -> dict[str, tuple[str, ...]]:
    """Build deterministic namespace buckets plus a backward-compatible `free` bucket."""
    result: dict[str, set[str]] = {}
    for raw in tags:
        parsed = parse_tag(raw)
        bucket = parsed.namespace or "free"
        result.setdefault(bucket, set()).add(parsed.value)
    return {key: tuple(sorted(values)) for key, values in sorted(result.items())}


@dataclass(frozen=True)
class StateTransition:
    recorded_at: str
    previous: Mapping[str, Any] | None
    current: Mapping[str, Any]
    recovery: str
    outcome: str | None = None


def append_state_transition(
    path: str | Path,
    current: QueryState,
    *,
    previous: QueryState | None = None,
    outcome: str | None = None,
    recorded_at: str | None = None,
) -> StateTransition:
    """Persist one append-only JSONL transition; parent directories are not created."""
    timestamp = recorded_at or datetime.now().astimezone().isoformat(timespec="milliseconds")
    transition = StateTransition(
        recorded_at=timestamp,
        previous=previous.to_dict() if previous else None,
        current=current.to_dict(),
        recovery=next_recovery_action(current).value,
        outcome=outcome,
    )
    line = json.dumps(asdict(transition), sort_keys=True, separators=(",", ":")) + "\n"
    fd = os.open(Path(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return transition


@dataclass(frozen=True)
class QueryReceipt:
    status: str
    lanes_queried: tuple[str, ...]
    failed_lanes: tuple[str, ...] = ()
    candidate_count: int = 0
    coverage_complete: bool = False
    state: QueryState = field(default_factory=QueryState)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.to_dict()
        return data


def normalize_query(query: str) -> str:
    """NFKC-normalize and collapse whitespace without altering original input."""
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    return " ".join(unicodedata.normalize("NFKC", query).split())


def compile_intent(
    query: str,
    *,
    now: datetime,
    timezone: str = "UTC",
    entities: Sequence[CanonicalEntity] = (),
) -> RetrievalIntent:
    """Compile common high-value language using deterministic rules only."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_now = now.astimezone(ZoneInfo(timezone))
    normalized = normalize_query(query)
    folded = normalized.casefold()

    found = []
    for entity in sorted(entities, key=lambda item: item.id):
        if any(alias and alias.casefold() in folded for alias in (entity.id, *entity.aliases)):
            found.append(entity.id)

    metric = None
    if re.search(r"\b(tokens?|token usage|usage)\b", folded) or (
        {"blade1tb", "phoebus", "whoart"}.issubset(found)
        and re.search(r"\bytd\b|year to date|this year", folded)
    ):
        metric = "token_usage"
    elif re.search(r"\b(cost|spend|price)\b", folded):
        metric = "cost"

    if re.search(r"\b(prove|provenance|sources?|evidence)\b", folded):
        intent_kind = "PROVENANCE"
    elif re.search(r"\b(latest|current|today|now)\b", folded):
        intent_kind = "LATEST"
    elif re.search(r"\b(all|every|fleet|machines?)\b", folded):
        intent_kind = "AGGREGATE"
    else:
        intent_kind = "LOOKUP"

    fleet_cues = ("fleet", "all machine", "all-machine", "all machines", "every machine")
    fleet_scope = any(cue in folded for cue in fleet_cues) or {
        "blade1tb", "phoebus", "whoart"
    }.issubset(found)
    scope = "FLEET" if fleet_scope else ("MACHINE" if found else "LOCAL")
    if re.search(r"\bytd\b|year to date|this year", folded):
        period, year = "YTD", local_now.year
    elif re.search(r"\bmtd\b|month to date|this month", folded):
        period, year = "MTD", local_now.year
    else:
        period, year = None, None

    key = f"{metric}:{scope.casefold()}:{period}:{year}" if metric and period and year else None
    return RetrievalIntent(
        query_original=query,
        query_normalized=normalized,
        intent=intent_kind,
        scope=scope,
        metric=metric,
        period=period,
        year=year,
        timezone=timezone,
        required_entities=tuple(found),
        canonical_key=key,
    )


def reciprocal_rank_fusion(
    lanes: Mapping[str, Sequence[ArtifactCandidate]], *, k: int = 60
) -> list[tuple[str, float]]:
    """Fuse ranked candidate IDs without comparing incomparable raw scores."""
    if k < 1:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    for lane_name in sorted(lanes):
        ordered = sorted(lanes[lane_name], key=lambda item: (item.rank, item.id))
        seen: set[str] = set()
        for rank, candidate in enumerate(ordered, 1):
            if candidate.id in seen:
                continue
            seen.add(candidate.id)
            scores[candidate.id] = scores.get(candidate.id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def derive_followups(
    *,
    missing_entities: Sequence[str] = (),
    missing_current_artifact: bool = False,
    conflicting_ids: Sequence[str] = (),
    budget: int = 5,
) -> list[str]:
    """Generate a stable, bounded recovery plan from explicit evidence gaps."""
    if budget < 0:
        raise ValueError("budget must not be negative")
    queries = [f"current evidence for {entity}" for entity in sorted(set(missing_entities))]
    if missing_current_artifact:
        queries.append("latest current canonical artifact")
    if conflicting_ids:
        ids = ", ".join(sorted(set(conflicting_ids)))
        queries.append(f"provenance and supersession for {ids}")
    return queries[:budget]
