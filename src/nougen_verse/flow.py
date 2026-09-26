"""Flow grammar, flow switches and their narrative causes.

A flow switch is a sustained change in rhythmic grammar (cell family,
density, landing). This module insists that a switch has a narrative cause.
Detected switches without a cue are reported as ``unexplained`` so a writer
can decide whether the change was on purpose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Sequence

from .config import Config, resolve_config
from .rhythm import BarRhythm

FLOW_SWITCH_CAUSES = (
    "emotional_escalation",
    "new_addressee",
    "reveal",
    "beat_change",
    "time_jump",
    "perspective_shift",
    "punchline_run",
    "internal_argument",
    "loss_of_control",
    "regained_control",
)
UNEXPLAINED = "unexplained"
CUE_TO_CAUSE = {
    "reveal": "reveal",
    "time_jump": "time_jump",
    "new_addressee": "new_addressee",
    "escalation": "emotional_escalation",
    "loss_of_control": "loss_of_control",
    "regained_control": "regained_control",
    "internal_argument": "internal_argument",
    "punchline_run": "punchline_run",
}
CAUSE_ALIASES = {c.replace("_", "-"): c for c in FLOW_SWITCH_CAUSES}
CAUSE_ALIASES.update({"escalation": "emotional_escalation", "addressee": "new_addressee", "perspective": "perspective_shift",
                      "punchline": "punchline_run", "argument": "internal_argument", "beat": "beat_change"})


def normalize_cause(cause: str) -> str:
    key = cause.strip().lower()
    key = CAUSE_ALIASES.get(key, key).replace("-", "_")
    if key not in FLOW_SWITCH_CAUSES and key != UNEXPLAINED:
        raise ValueError(f"unknown flow switch cause {cause!r}; supported: {', '.join(FLOW_SWITCH_CAUSES)}")
    return key


@dataclass
class FlowGrammar:
    cell: str
    family: str = "binary"
    density: float = 0.0
    landing: str | None = None
    syncopation: float = 0.0
    region: str = "normal"

    @classmethod
    def from_bar(cls, bar: BarRhythm) -> "FlowGrammar":
        g = bar.grammar()
        return cls(g["cell"], g["family"], g["density"], g["landing"], g["syncopation"], g["region"])

    def to_dict(self) -> dict:
        return {"cell": self.cell, "family": self.family, "density": self.density, "landing": self.landing,
                "syncopation": self.syncopation, "region": self.region}

    @classmethod
    def from_dict(cls, d: dict) -> "FlowGrammar":
        return cls(d.get("cell", "eighth"), d.get("family", "binary"), float(d.get("density", 0.0)),
                   d.get("landing"), float(d.get("syncopation", 0.0)), d.get("region", "normal"))


@dataclass
class FlowSwitch:
    """A change of rhythmic grammar at a coordinate, tied to a narrative cause."""

    bar: int
    previous: FlowGrammar
    next: FlowGrammar
    cause: str
    semantic_trigger: str = ""
    breath_consequence: str = ""
    rhyme_consequence: str = ""
    delivery_instruction: str = ""
    beat: str = "0"
    confidence: float = 1.0
    source: str = "planned"

    def __post_init__(self) -> None:
        self.cause = normalize_cause(self.cause)
        if self.bar < 1:
            raise ValueError("flow switch bar numbers start at 1")

    @property
    def has_narrative_cause(self) -> bool:
        return self.cause != UNEXPLAINED

    def to_dict(self) -> dict:
        return {
            "coordinate": {"bar": self.bar, "beat": self.beat},
            "previous_grammar": self.previous.to_dict(),
            "next_grammar": self.next.to_dict(),
            "cause": self.cause,
            "semantic_trigger": self.semantic_trigger,
            "breath_consequence": self.breath_consequence,
            "rhyme_consequence": self.rhyme_consequence,
            "delivery_instruction": self.delivery_instruction,
            "confidence": round(self.confidence, 3),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FlowSwitch":
        coord = d.get("coordinate", {})
        return cls(
            bar=int(coord.get("bar", d.get("bar", 1))),
            previous=FlowGrammar.from_dict(d.get("previous_grammar", {})),
            next=FlowGrammar.from_dict(d.get("next_grammar", {})),
            cause=d["cause"],
            semantic_trigger=d.get("semantic_trigger", ""),
            breath_consequence=d.get("breath_consequence", ""),
            rhyme_consequence=d.get("rhyme_consequence", ""),
            delivery_instruction=d.get("delivery_instruction", ""),
            beat=str(coord.get("beat", d.get("beat", "0"))),
            confidence=float(d.get("confidence", 1.0)),
            source=d.get("source", "planned"),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "FlowSwitch":
        return cls.from_dict(json.loads(text))


def breath_consequence(prev: FlowGrammar, nxt: FlowGrammar) -> str:
    if nxt.density > prev.density:
        return "denser delivery after the switch; plan a breath right before it"
    if nxt.density < prev.density:
        return "more space after the switch; breaths can move to the new rests"
    return "density unchanged; breath plan can stay"


def rhyme_consequence(prev_family: str | None, next_family: str | None) -> str:
    if prev_family and next_family and prev_family != next_family:
        return f"end rhyme family changes from {prev_family} to {next_family}"
    if prev_family and next_family:
        return f"end rhyme family {next_family} carries across the switch"
    return "no end rhyme family recorded at the switch"


def delivery_for(prev: FlowGrammar, nxt: FlowGrammar, cause: str) -> str:
    return f"move from {prev.cell} to {nxt.cell} feel; let the {cause.replace('_', ' ')} drive the change, not the beat alone"


def _pronoun_class(norms: Sequence[str]) -> str | None:
    first = sum(1 for w in norms if w in ("i", "me", "my", "i'm", "we", "us", "our"))
    second = sum(1 for w in norms if w in ("you", "your", "you're", "y'all"))
    third = sum(1 for w in norms if w in ("he", "she", "they", "him", "her", "them", "his", "their"))
    counts = {"first": first, "second": second, "third": third}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] else None


def guess_cause(bar_norms: Sequence[str], prev_norms: Sequence[Sequence[str]], cue_hits: dict[str, list[str]]) -> tuple[str, str]:
    """Return (cause, trigger text) from cue lexicon hits and pronoun shifts."""
    for cue_kind, cause in CUE_TO_CAUSE.items():
        if cue_hits.get(cue_kind):
            return cause, f"{cue_kind} cue: {cue_hits[cue_kind][0]!r}"
    now = _pronoun_class(bar_norms)
    before = _pronoun_class([w for bar in prev_norms for w in bar])
    if now and before and now != before:
        return "perspective_shift", f"pronoun focus moves from {before} person to {now} person"
    return UNEXPLAINED, ""


def detect_flow_switches(
    bars: Sequence[BarRhythm],
    bar_norms: Sequence[Sequence[str]],
    cue_hits: Sequence[dict[str, list[str]]],
    tags: Sequence[dict] | None = None,
    end_families: Sequence[str | None] | None = None,
    config: Config | None = None,
) -> list[FlowSwitch]:
    """Find sustained grammar changes and attach a cause (tagged, cued, or unexplained)."""
    cfg = resolve_config(config)
    f = cfg.flow
    n = len(bars)
    tags = list(tags or [{} for _ in bars])
    end_families = list(end_families or [None] * n)
    ratio_limit = float(f["density_change_ratio"])
    m = max(1, int(f["min_bars_after_switch"]))
    dens = [max(b.syllables_per_beat, 1e-6) for b in bars]
    switches: list[FlowSwitch] = []
    seg_start = 0
    i = 1
    while i < n:
        tag = tags[i] if i < len(tags) else {}
        tagged_cause = tag.get("switch")
        explicit_cell = bool(tag.get("cell")) and bars[i].cell != bars[i - 1].cell
        before = dens[max(seg_start, i - m):i]
        after = dens[i:i + m]
        changed = False
        if before and len(after) == m:
            b_mean, a_mean = sum(before) / len(before), sum(after) / len(after)
            lo, hi = sorted((b_mean, a_mean))
            same_side = all(d > b_mean for d in after) if a_mean > b_mean else all(d < b_mean for d in after)
            changed = hi / lo >= ratio_limit and same_side
        if tagged_cause or changed or explicit_cell:
            prev_bar, next_bar = bars[i - 1], bars[i]
            prev_g, next_g = FlowGrammar.from_bar(prev_bar), FlowGrammar.from_bar(next_bar)
            if before:
                prev_g.density = round(sum(before) / len(before), 3)
            if after:
                next_g.density = round(sum(after) / len(after), 3)
            if tagged_cause and tagged_cause is not True:
                cause, trigger, conf, source = normalize_cause(str(tagged_cause)), f"tagged [switch:{tagged_cause}]", f["tag_confidence"], "tagged"
            else:
                cause, trigger = guess_cause(bar_norms[i], bar_norms[max(0, i - 2):i], cue_hits[i] if i < len(cue_hits) else {})
                conf = f["cue_confidence"] if cause != UNEXPLAINED else f["unexplained_confidence"]
                source = "cue" if cause != UNEXPLAINED else "inferred"
            switches.append(FlowSwitch(
                bar=i + 1, previous=prev_g, next=next_g, cause=cause, semantic_trigger=trigger,
                breath_consequence=breath_consequence(prev_g, next_g),
                rhyme_consequence=rhyme_consequence(end_families[i - 1], end_families[i]),
                delivery_instruction=delivery_for(prev_g, next_g, cause), confidence=float(conf), source=source,
            ))
            seg_start = i
            i += m
            continue
        i += 1
    return switches
