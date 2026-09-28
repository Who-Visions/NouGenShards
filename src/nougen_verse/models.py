"""Typed models for requests, blueprints, analyses, scores, repairs and prompts.

Everything serializes to plain JSON through ``to_dict()``. Bar numbers in
JSON output are 1-based everywhere. Fractions are written as strings.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from .config import Config, resolve_config

SCHEMA_VERSION = "0.1.0"


def to_plain(obj: Any) -> Any:
    """Convert dataclasses, fractions, tuples and sets into JSON-safe values."""
    if hasattr(obj, "to_dict") and not isinstance(obj, type):
        return to_plain(obj.to_dict())
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Fraction):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_plain(v) for v in obj]
    if isinstance(obj, set):
        return sorted(to_plain(v) for v in obj)
    if isinstance(obj, float):
        return round(obj, 6)
    return obj


def to_json(obj: Any, indent: int | None = 2) -> str:
    return json.dumps(to_plain(obj), indent=indent, sort_keys=False, ensure_ascii=False)


@dataclass
class VerseRequest:
    topic: str = ""
    central_claim: str = ""
    emotional_axis: dict = field(default_factory=lambda: {"from": "", "to": ""})
    narrative_perspective: str = "first"
    persona_id: str | None = None
    persona: dict | None = None
    audience: str = ""
    bar_count: int = 16
    bpm: float = 90.0
    time_signature: str = "4/4"
    subdivisions_per_beat: int = 4
    rhyme_density: float = 0.5
    multisyllabic: float = 0.3
    internal_rhyme: float = 0.3
    scheme: str = "AABB"
    flow_switches: Any = 0
    breath_budget: Any = "default"
    explicitness: str = "clean"
    vocabulary_register: str = "plain"
    imagery_domains: list[str] = field(default_factory=list)
    forbidden_phrases: list[str] = field(default_factory=list)
    required_facts: list[str] = field(default_factory=list)
    callbacks: list[str] = field(default_factory=list)
    punchline_targets: list = field(default_factory=list)
    provider_constraints: dict = field(default_factory=dict)
    seed: int = 0
    content_spine: dict | None = None
    scheme_breaks: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict, config: Config | None = None) -> "VerseRequest":
        cfg = resolve_config(config)
        names = {f.name for f in dataclasses.fields(cls)}
        kwargs = {k: v for k, v in d.items() if k in names}
        if isinstance(kwargs.get("emotional_axis"), str):
            parts = [p.strip() for p in kwargs["emotional_axis"].replace("->", ">").split(">")]
            kwargs["emotional_axis"] = {"from": parts[0], "to": parts[-1] if len(parts) > 1 else parts[0]}
        kwargs.setdefault("bar_count", cfg.planner["default_bar_count"])
        kwargs.setdefault("bpm", cfg.rhythm["default_bpm"])
        kwargs.setdefault("subdivisions_per_beat", cfg.rhythm["default_subdivisions"])
        kwargs.setdefault("scheme", cfg.planner["default_scheme"])
        return cls(**kwargs)

    def validate(self) -> list[str]:
        issues = []
        if not isinstance(self.bar_count, int) or self.bar_count < 1:
            issues.append("bar_count must be a positive integer")
        if not self.bpm or float(self.bpm) <= 0:
            issues.append("bpm must be positive")
        for k in ("rhyme_density", "multisyllabic", "internal_rhyme"):
            v = getattr(self, k)
            if not isinstance(v, (int, float)) or not 0 <= float(v) <= 1:
                issues.append(f"{k} must be between 0 and 1")
        if not self.scheme or not all(c.isalpha() for c in self.scheme.replace(" ", "")):
            issues.append("scheme must be letters such as AABB (X marks a deliberate break)")
        if "/" not in str(self.time_signature):
            issues.append("time_signature must look like 4/4")
        return issues

    def to_dict(self) -> dict:
        return {f.name: to_plain(getattr(self, f.name)) for f in dataclasses.fields(self)}


@dataclass
class VerseBlueprint:
    request_digest: str
    seed: int
    grid: dict
    persona: dict | None
    content_spine: dict
    bar_objectives: list[dict]
    setup_payoff_links: list[dict]
    rhyme_family_assignments: list[dict]
    stressed_syllable_targets: list[dict]
    internal_rhyme_placements: list[dict]
    end_rhyme_placements: list[dict]
    cadence_cells: list[dict]
    rest_positions: list[dict]
    breath_groups: list[dict]
    delivery_instructions: list[dict]
    emotion_curve: list[float]
    flow_switches: list[dict]
    scheme_breaks: list[dict]
    callbacks: list[dict]
    specificity_anchors: list[dict]
    revision_priorities: list[str]
    provenance: dict
    required_facts: list[str] = field(default_factory=list)
    forbidden_phrases: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    scheme: str = ""
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {f.name: to_plain(getattr(self, f.name)) for f in dataclasses.fields(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "VerseBlueprint":
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class VerseAnalysis:
    counts: dict
    syllables: dict
    stress_patterns: list[str]
    end_rhyme_families: list[dict]
    internal_rhyme_families: list[dict]
    multisyllabic_chains: list[dict]
    compound_and_slant_candidates: list[dict]
    rhyme_density: float
    rhyme_span: dict
    scheme: dict
    pattern_changes: list[dict]
    scheme_breaks: list[dict]
    pattern_collapses: list[dict]
    cadence: dict
    overcrowded_bars: list[int]
    breath: dict
    lexical_repetition: dict
    semantic_repetition: list[dict]
    generic_flags: list[dict]
    concrete_noun_density: float
    sensory_detail_density: float
    named_fact_retention: dict
    persona_consistency: dict | None
    emotional_progression: dict
    setup_payoff: dict
    weak_bars: list[dict]
    repair_recommendations: list[dict]
    confidence: dict
    limitations: list[str]
    flow_switches: list[dict] = field(default_factory=list)
    protected_bars: list[dict] = field(default_factory=list)
    rhyme_stats: dict = field(default_factory=dict)
    syntax: dict = field(default_factory=dict)
    bars: list[dict] = field(default_factory=list)
    grid: dict | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {f.name: to_plain(getattr(self, f.name)) for f in dataclasses.fields(self)}


@dataclass
class ScoreReport:
    dimensions: dict
    genericness: dict
    rewards: list[dict]
    composite: float | None
    notes: list[str]
    weights: dict
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {f.name: to_plain(getattr(self, f.name)) for f in dataclasses.fields(self)}

    def score(self, dimension: str) -> float | None:
        return self.dimensions.get(dimension, {}).get("score")


@dataclass
class RepairPlan:
    actions: list[dict]
    llm_instructions: str
    preserved_voice: dict
    notes: list[str]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {f.name: to_plain(getattr(self, f.name)) for f in dataclasses.fields(self)}


@dataclass
class CompiledPrompt:
    provider: str
    format: str
    system: str
    user: str
    messages: list[dict]
    constraint_packet: dict
    output_schema: dict
    generation_sequence: list[str]
    self_check: list[str]
    revision_loop: list[str]
    notes: list[str]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {f.name: to_plain(getattr(self, f.name)) for f in dataclasses.fields(self)}
