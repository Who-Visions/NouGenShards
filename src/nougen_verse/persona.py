"""Persona contracts: the voice a verse has to keep.

A persona is a structured contract (worldview, biography anchors, vocabulary
range, taboo language, metaphor domains, pronunciation overrides and so on).
The analyzer checks a draft against it, and repair ranks candidate edits by
how much of the voice they keep. A cleaner bar that erases the speaker should
score lower than a rougher bar that sounds like them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .config import ENV_PERSONA_PATH, Config, resolve_config

PERSONA_FIELDS = (
    "worldview", "biography_anchors", "language_boundaries", "vocabulary_range", "sentence_length",
    "humor_mode", "aggression", "vulnerability", "directness", "metaphor_domains", "taboo_language",
    "code_switch_rules", "signature_moves", "forbidden_cliches", "vocal_energy_curve",
    "narrative_reliability", "audience_relationship", "pronunciation_overrides",
)


@dataclass
class Persona:
    id: str = "anonymous"
    name: str = ""
    worldview: str = ""
    biography_anchors: list[str] = field(default_factory=list)
    language_boundaries: dict = field(default_factory=dict)
    vocabulary_range: dict = field(default_factory=dict)
    sentence_length: dict = field(default_factory=dict)
    humor_mode: str = ""
    aggression: float = 0.5
    vulnerability: float = 0.5
    directness: float = 0.5
    metaphor_domains: list[str] = field(default_factory=list)
    taboo_language: list[str] = field(default_factory=list)
    code_switch_rules: list[str] = field(default_factory=list)
    signature_moves: list[str] = field(default_factory=list)
    forbidden_cliches: list[str] = field(default_factory=list)
    vocal_energy_curve: list[float] = field(default_factory=list)
    narrative_reliability: str = "reliable"
    audience_relationship: str = ""
    pronunciation_overrides: dict[str, str] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Persona":
        known = set(PERSONA_FIELDS) | {"id", "name"}
        kwargs = {k: v for k, v in d.items() if k in known}
        extra = {k: v for k, v in d.items() if k not in known}
        p = cls(**kwargs)
        p.extra = extra
        return p

    def to_dict(self) -> dict:
        out = {"id": self.id, "name": self.name}
        for k in PERSONA_FIELDS:
            out[k] = getattr(self, k)
        return out

    def validate(self) -> list[str]:
        issues = []
        for k in ("aggression", "vulnerability", "directness"):
            v = getattr(self, k)
            if not isinstance(v, (int, float)) or not 0.0 <= float(v) <= 1.0:
                issues.append(f"{k} should be a number from 0 to 1")
        sl = self.sentence_length or {}
        if sl and sl.get("min_words", 0) > sl.get("max_words", 10 ** 6):
            issues.append("sentence_length.min_words is larger than max_words")
        return issues

    # convenience views
    @property
    def register(self) -> str:
        return str((self.vocabulary_range or {}).get("register", "")).lower()

    @property
    def preferred(self) -> set[str]:
        return {w.lower() for w in (self.vocabulary_range or {}).get("preferred", [])}

    @property
    def avoided(self) -> set[str]:
        return {w.lower() for w in (self.vocabulary_range or {}).get("avoided", [])}


def load_persona(ref: "str | dict | Persona | None", config: Config | None = None) -> Persona | None:
    """Accept a Persona, a dict, a path to JSON, or an id looked up on the persona search path."""
    if ref is None or isinstance(ref, Persona):
        return ref
    if isinstance(ref, dict):
        return Persona.from_dict(ref)
    path = Path(ref)
    if path.suffix.lower() == ".json" and path.exists():
        return Persona.from_dict(json.loads(path.read_text(encoding="utf-8")))
    cfg = resolve_config(config)
    dirs = [d for d in os.environ.get(ENV_PERSONA_PATH, "").split(os.pathsep) if d] + list(cfg.persona.get("search_paths") or [])
    for d in dirs:
        cand = Path(d) / f"{ref}.json"
        if cand.exists():
            return Persona.from_dict(json.loads(cand.read_text(encoding="utf-8")))
    raise FileNotFoundError(f"persona {ref!r} not found as a file or on the persona search path {dirs}")


@dataclass
class PersonaReport:
    persona_id: str
    consistency: float
    bar_flags: list[dict]
    drift_bars: list[int]
    anchors_found: list[str]
    domain_hits: dict[str, list[str]]
    notes: list[str]

    def to_dict(self) -> dict:
        return {"persona_id": self.persona_id, "consistency": round(self.consistency, 3), "bar_flags": self.bar_flags,
                "drift_bars": self.drift_bars, "anchors_found": self.anchors_found, "domain_hits": self.domain_hits,
                "notes": self.notes}


def _terms(items: Sequence[str]) -> set[str]:
    out = set()
    for it in items:
        for w in str(it).lower().replace("'", " ").split():
            if len(w) > 2:
                out.add(w)
    return out


def domain_terms(persona: Persona, lex) -> set[str]:
    terms = set(persona.preferred)
    for d in persona.metaphor_domains:
        terms |= set(lex.domains.get(d, [d]))
    return terms


def bar_issues(norms: Sequence[str], persona: Persona, lex, config: Config | None = None) -> list[str]:
    cfg = resolve_config(config)
    issues = []
    joined = " " + " ".join(norms) + " "
    for t in persona.taboo_language:
        if f" {t.lower()} " in joined:
            issues.append(f"taboo: {t}")
    for c in persona.forbidden_cliches:
        if f" {c.lower()} " in joined:
            issues.append(f"forbidden cliche: {c}")
    for w in norms:
        if w in persona.avoided:
            issues.append(f"avoided word: {w}")
    for a in (persona.language_boundaries or {}).get("avoid", []):
        if f" {a.lower()} " in joined:
            issues.append(f"outside language boundary: {a}")
    own = persona.register
    for reg, words in lex.registers.items():
        if reg == own:
            continue
        hits = [w for w in norms if w in set(words) and w not in persona.preferred]
        if hits:
            issues.append(f"register drift ({reg}): {', '.join(sorted(set(hits)))}")
    sl = persona.sentence_length or {}
    tol = int(cfg.persona["sentence_length_tolerance_words"])
    if sl and norms:
        n = len(norms)
        if "max_words" in sl and n > int(sl["max_words"]) + tol:
            issues.append(f"line length {n} words is longer than this voice usually runs")
        if "min_words" in sl and n < int(sl["min_words"]) - tol:
            issues.append(f"line length {n} words is shorter than this voice usually runs")
    return issues


def persona_consistency(bar_norms: Sequence[Sequence[str]], persona: Persona, lex, config: Config | None = None) -> PersonaReport:
    cfg = resolve_config(config)
    pc = cfg.persona
    flags = []
    drift = []
    bar_scores = []
    terms = domain_terms(persona, lex)
    anchor_terms = _terms(persona.biography_anchors)
    domain_hits: dict[str, list[str]] = {}
    anchors_found: set[str] = set()
    bars_with_voice = 0
    for i, norms in enumerate(bar_norms):
        issues = bar_issues(norms, persona, lex, cfg)
        score = max(0.0, 1.0 - float(pc["issue_penalty"]) * len(issues))
        bar_scores.append(score)
        if issues:
            flags.append({"bar": i + 1, "issues": issues})
            if score < 1.0 - float(pc["drift_warn"]) or issues:
                drift.append(i + 1)
        voice_hit = False
        for w in norms:
            if w in terms:
                domain_hits.setdefault(w, []).append(str(i + 1))
                voice_hit = True
            if w in anchor_terms:
                anchors_found.add(w)
                voice_hit = True
        bars_with_voice += 1 if voice_hit else 0
    n = max(1, len(bar_norms))
    positive = min(1.0, (bars_with_voice / n) / float(pc["positive_target_share"]))
    share = float(pc["positive_share"])
    consistency = (1 - share) * (sum(bar_scores) / n if bar_scores else 0.0) + share * positive
    notes = ["Persona checks use word lists from the persona contract; they cannot judge tone, only vocabulary and shape."]
    return PersonaReport(persona.id, consistency, flags, drift, sorted(anchors_found),
                         {k: v for k, v in sorted(domain_hits.items())}, notes)


def voice_similarity(original_norms: Sequence[str], candidate_norms: Sequence[str], persona: Persona | None, lex, config: Config | None = None) -> float:
    """How much of the original bar's voice a candidate keeps (0 to 1).

    Voice anchors are persona domain words, preferred vocabulary, biography
    anchor words, concrete nouns and numbers in the original bar. The score
    mixes the share of anchors kept with overall content-word overlap, then
    subtracts persona issues the candidate introduces.
    """
    cfg = resolve_config(config)
    pc = cfg.persona
    stop = lex.stopwords
    orig = [w for w in original_norms if w not in stop]
    cand = set(w for w in candidate_norms if w not in stop)
    anchors = set()
    if persona:
        anchors |= domain_terms(persona, lex) & set(orig)
        anchors |= _terms(persona.biography_anchors) & set(orig)
    anchors |= {w for w in orig if w in lex.concrete or w in lex.people or w.isdigit()}
    kept = len(anchors & cand) / len(anchors) if anchors else 1.0
    so = set(orig)
    overlap = len(so & cand) / len(so | cand) if (so or cand) else 1.0
    score = float(pc["voice_anchor_weight"]) * kept + float(pc["voice_vocab_weight"]) * overlap
    if persona:
        new_issues = len(bar_issues(list(candidate_norms), persona, lex, cfg)) - len(bar_issues(list(original_norms), persona, lex, cfg))
        if new_issues > 0:
            score -= float(pc["issue_penalty"]) * new_issues
    return max(0.0, min(1.0, score))
