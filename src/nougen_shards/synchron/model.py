"""Evidence model. Everything the engine may use is in these types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class Event:
    event_id: str
    created_at_ms: int
    observed_at_ms: int
    source_type: str
    source_id: str
    actor: str
    topic_vector: Tuple[float, ...] = ()
    entities: Tuple[str, ...] = ()
    concepts: Tuple[str, ...] = ()
    query_lineage: Tuple[str, ...] = ()        # event_ids this one was searched FROM
    explicit_user_intent: Tuple[str, ...] = ()  # the user's literal query terms
    location_scope: Optional[str] = None
    canonical_date: Optional[str] = None      # ISO date the event is ABOUT (premiere, solstice...)
    provenance_hash: str = ""

    def terms(self) -> frozenset:
        return frozenset(t.lower() for t in self.concepts + self.entities)


@dataclass(frozen=True)
class Window:
    """A calendar window worth aligning to (equinox, anniversary...)."""
    name: str
    start: str  # ISO date, inclusive
    end: str    # ISO date, inclusive
    kind: str = "astronomical"  # astronomical | anniversary | release | historical


@dataclass(frozen=True)
class BaseRates:
    """Corpus statistics snapshot. Missing data means UNKNOWN and is scored
    as common (low rarity, full penalty) -- absence is never evidence of rarity."""
    concept_counts: Mapping[str, int] = field(default_factory=dict)
    cooccurrence: Mapping[str, int] = field(default_factory=dict)  # key "a|b", a<b
    seasonal: Mapping[str, float] = field(default_factory=dict)    # P(concept recurs in this window yearly)
    popularity: Mapping[str, float] = field(default_factory=dict)  # 0..1 share of general attention
    revision: str = "unversioned"

    def pair(self, a: str, b: str) -> int:
        x, y = sorted((a.lower(), b.lower()))
        return int(self.cooccurrence.get(f"{x}|{y}", 0))


@dataclass(frozen=True)
class Config:
    weights: Tuple[Tuple[str, float], ...] = (
        ("semantic", 0.18), ("independence", 0.20), ("temporal", 0.16), ("rarity", 0.16),
        ("distance", 0.10), ("usefulness", 0.10), ("provenance", 0.07), ("calendar", 0.03),
    )
    half_life_hours: float = 36.0
    bridge_target: float = 0.62
    bridge_width: float = 0.22
    min_independence: float = 0.60
    min_provenance: float = 0.70
    min_semantic: float = 0.35
    direct_query_threshold: float = 0.5
    hindsight_days: float = 7.0
    model_hash: str = "none"
    embedding_version: str = "none"
    version: str = "synchron-0.1"


@dataclass(frozen=True)
class Snapshot:
    """One frozen view of the evidence. ``as_of_ms`` replaces the wall clock."""
    as_of_ms: int
    events: Tuple[Event, ...]
    windows: Tuple[Window, ...] = ()
    base_rates: BaseRates = field(default_factory=BaseRates)
    timestamp_source: str = "caller"
