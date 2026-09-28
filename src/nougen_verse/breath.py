"""Breath pressure and delivery annotations.

Breath pressure is a performance heuristic built from syllable rate, phrase
length without a rest, consonant clusters, vowel openness, delivery intensity
and repeated attacks, weighed against a performer profile. It produces
warnings, not medical or physiological claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Sequence

from .config import Config, resolve_config
from .phonetics import PhraseSyllable
from .rhythm import CELL_LIBRARY, RhythmGrid

BREATH_NOTE = "Breath pressure is estimated from text and a performer profile. It is a rehearsal hint, not a physiological or medical measure."

DELIVERY_FIELDS = (
    "volume", "intensity", "pitch_direction", "timbre", "articulation", "elongation", "stutter",
    "half_sung", "emphasis_words", "adlib_slots", "silence", "audience_interaction",
)


@dataclass
class DeliveryAnnotation:
    bar: int
    volume: str = "medium"
    intensity: float = 0.5
    pitch_direction: str = "level"
    timbre: str = ""
    articulation: str = "clear"
    elongation: list[str] = field(default_factory=list)
    stutter: list[str] = field(default_factory=list)
    half_sung: bool = False
    emphasis_words: list[str] = field(default_factory=list)
    adlib_slots: list[str] = field(default_factory=list)
    silence: list[str] = field(default_factory=list)
    audience_interaction: str = ""

    def to_dict(self) -> dict:
        return {"bar": self.bar, "volume": self.volume, "intensity": round(self.intensity, 3),
                "pitch_direction": self.pitch_direction, "timbre": self.timbre, "articulation": self.articulation,
                "elongation": self.elongation, "stutter": self.stutter, "half_sung": self.half_sung,
                "emphasis_words": self.emphasis_words, "adlib_slots": self.adlib_slots, "silence": self.silence,
                "audience_interaction": self.audience_interaction}


@dataclass
class BreathGroup:
    index: int
    start_bar: int
    end_bar: int
    syllables: int
    seconds: float
    syllables_per_second: float
    components: dict
    pressure: float
    level: str

    def to_dict(self) -> dict:
        return {"index": self.index, "start_bar": self.start_bar, "end_bar": self.end_bar, "syllables": self.syllables,
                "seconds": round(self.seconds, 3), "syllables_per_second": round(self.syllables_per_second, 3),
                "components": {k: round(v, 3) for k, v in self.components.items()},
                "pressure": round(self.pressure, 3), "level": self.level}


@dataclass
class BreathReport:
    profile: str
    groups: list[BreathGroup]
    warnings: list[str]
    max_pressure: float
    breath_opportunities: int
    note: str = BREATH_NOTE

    def to_dict(self) -> dict:
        return {"profile": self.profile, "groups": [g.to_dict() for g in self.groups], "warnings": self.warnings,
                "max_pressure": round(self.max_pressure, 3), "breath_opportunities": self.breath_opportunities,
                "note": self.note}


def breath_profile(name: str | dict | None, config: Config | None = None) -> tuple[str, dict]:
    cfg = resolve_config(config)
    if isinstance(name, dict):
        base = dict(cfg.breath["profiles"]["default"])
        base.update(name)
        return name.get("name", "custom"), base
    key = name or cfg.breath["profile"]
    profiles = cfg.breath["profiles"]
    if key not in profiles:
        raise ValueError(f"unknown breath profile {key!r}; known: {sorted(profiles)}")
    return key, profiles[key]


def analyze_breath(
    rhythm: RhythmGrid,
    bar_syllables: Sequence[Sequence[PhraseSyllable]],
    intensities: Sequence[float] | None = None,
    profile: str | dict | None = None,
    config: Config | None = None,
) -> BreathReport:
    """Split the syllable stream at rests long enough to breathe and score each group."""
    cfg = resolve_config(config)
    b = cfg.breath
    name, prof = breath_profile(profile, cfg)
    weights = b["weights"]
    open_vowels = set(b["open_vowels"])
    beats = rhythm.grid.beats_per_bar
    spb = rhythm.grid.seconds_per_beat
    min_rest = Fraction(b["min_breath_rest_beats"]).limit_denominator(96)
    default_intensity = float(b["default_intensity"])
    # flatten syllable events with their phonetic info
    stream = []
    for bar in rhythm.bars:
        sylls = bar_syllables[bar.bar] if bar.bar < len(bar_syllables) else []
        k = 0
        for ev in bar.events:
            if ev.kind != "syllable":
                continue
            info = sylls[k] if k < len(sylls) else None
            k += 1
            stream.append((ev, info))
    groups_raw: list[list] = []
    current: list = []
    opportunities = 0
    for idx, (ev, info) in enumerate(stream):
        if current:
            prev_ev = current[-1][0]
            prev_end = prev_ev.absolute(beats) + CELL_LIBRARY[prev_ev.cell]["step"]
            gap = ev.absolute(beats) - prev_end
            if gap >= min_rest:
                groups_raw.append(current)
                current = []
                opportunities += 1
        current.append((ev, info))
    if current:
        groups_raw.append(current)
    groups: list[BreathGroup] = []
    warnings: list[str] = []
    for gi, grp in enumerate(groups_raw):
        first, last = grp[0][0], grp[-1][0]
        span_beats = (last.absolute(beats) + CELL_LIBRARY[last.cell]["step"]) - first.absolute(beats)
        seconds = max(float(span_beats) * spb, 1e-6)
        n = len(grp)
        rate = n / seconds
        infos = [info for _, info in grp if info is not None]
        cluster = sum(1 for i in infos if len(i.syllable.onset) >= 2 or len(i.syllable.coda) >= 2) / len(infos) if infos else 0.0
        closed = sum(1 for i in infos if i.syllable.nucleus not in open_vowels) / len(infos) if infos else 0.0
        bars_in = sorted({ev.bar for ev, _ in grp})
        if intensities:
            inten = sum(intensities[bi] if bi < len(intensities) else default_intensity for bi in bars_in) / len(bars_in)
        else:
            inten = default_intensity
        attacks = sum(1 for ev, _ in grp if ev.flam) / n
        def ramp(x: float, lo: float, hi: float) -> float:
            return max(0.0, min(1.0, (x - lo) / (hi - lo))) if hi > lo else float(x >= hi)

        comps = {
            "rate": ramp(rate, float(prof["relaxed_syllables_per_second"]), float(prof["max_syllables_per_second"])),
            "length": ramp(seconds, float(prof["relaxed_phrase_seconds"]), float(prof["max_phrase_seconds"])),
            "clusters": cluster,
            "closed_vowels": closed,
            "intensity": max(0.0, min(1.0, inten)),
            "attacks": min(1.0, attacks),
        }
        total_w = sum(weights.values()) or 1.0
        pressure = sum(weights[k] * comps[k] for k in weights) / total_w
        level = "severe" if pressure >= prof["severe_pressure"] else ("warn" if pressure >= prof["warn_pressure"] else "ok")
        g = BreathGroup(gi, bars_in[0] + 1, bars_in[-1] + 1, n, seconds, rate, comps, pressure, level)
        groups.append(g)
        if level != "ok":
            where = f"bar {g.start_bar}" if g.start_bar == g.end_bar else f"bars {g.start_bar}-{g.end_bar}"
            warnings.append(
                f"{where}: estimated breath pressure {pressure:.2f} ({level}); about {seconds:.1f} s and {n} syllables "
                f"before a usable rest. Consider a rest, a pickup breath or fewer syllables. {BREATH_NOTE}"
            )
    return BreathReport(name, groups, warnings, max((g.pressure for g in groups), default=0.0), opportunities)
