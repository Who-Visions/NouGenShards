"""Deterministic building blocks for the Retrieval Engine v2 rollout.

This module is intentionally dependency-free: query planning and rank fusion
can be adopted by existing recall surfaces before optional model lanes exist.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence
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


@dataclass(frozen=True)
class QueryReceipt:
    status: str
    lanes_queried: tuple[str, ...]
    failed_lanes: tuple[str, ...] = ()
    candidate_count: int = 0
    coverage_complete: bool = False


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
