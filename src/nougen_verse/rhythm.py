"""Beat-grid rhythm model.

A verse is placed on a grid of bars, beats and subdivisions. Positions are
exact fractions of a beat (``fractions.Fraction``), so triplets (thirds of a
beat) and sixteenths (quarters of a beat) are both represented without
rounding. JSON output writes them as strings such as ``"7/3"``.

When onsets are estimated from text they are an estimate: the estimator
knows syllable counts, stress, punctuation and a few markers, never the beat
itself. Every grid carries ``estimate_note`` saying so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Sequence

from .config import Config, resolve_config

ESTIMATE_NOTE = (
    "Text-only estimate. Onsets are inferred from syllable counts, stress, punctuation and markers, "
    "not from audio or beat analysis. Treat positions as a starting sketch, not a transcription."
)

CELL_LIBRARY: dict[str, dict] = {
    "quarter": {"step": Fraction(1), "tuplet": None, "family": "binary"},
    "eighth": {"step": Fraction(1, 2), "tuplet": None, "family": "binary"},
    "triplet": {"step": Fraction(1, 3), "tuplet": "3:2", "family": "ternary"},
    "sixteenth": {"step": Fraction(1, 4), "tuplet": None, "family": "binary"},
    "sextuplet": {"step": Fraction(1, 6), "tuplet": "6:4", "family": "ternary"},
    "thirty_second": {"step": Fraction(1, 8), "tuplet": None, "family": "binary"},
}
FINER_CELL = {"quarter": "eighth", "eighth": "sixteenth", "triplet": "sextuplet",
              "sixteenth": "thirty_second", "sextuplet": "thirty_second", "thirty_second": None}
CELL_ALIASES = {"straight": "eighth", "8ths": "eighth", "16ths": "sixteenth", "triplets": "triplet",
                "double": "thirty_second", "double-time": "thirty_second", "double_time": "thirty_second",
                "half": "quarter", "half-time": "quarter", "half_time": "quarter"}


def register_cell(name: str, step: Fraction, tuplet: str | None = None, family: str = "binary", finer: str | None = None) -> None:
    """Add a custom cadence cell (for example a quintuplet) to the library."""
    CELL_LIBRARY[name] = {"step": Fraction(step), "tuplet": tuplet, "family": family}
    FINER_CELL.setdefault(name, finer)


def resolve_cell(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    key = CELL_ALIASES.get(key, key)
    if key not in CELL_LIBRARY:
        raise ValueError(f"unknown cadence cell {name!r}; known: {sorted(CELL_LIBRARY)}")
    return key


def frac_str(x: Fraction | None) -> str | None:
    return None if x is None else str(Fraction(x))


def parse_frac(x: str | int | float | Fraction) -> Fraction:
    return Fraction(x).limit_denominator(96) if not isinstance(x, str) else Fraction(x)


@dataclass
class BeatGrid:
    bpm: float = 90.0
    beats_per_bar: int = 4
    subdivisions_per_beat: int = 4
    swing: float = 0.5

    @classmethod
    def from_time_signature(cls, bpm: float, time_signature: str = "4/4", subdivisions: int = 4, swing: float = 0.5) -> "BeatGrid":
        top = int(str(time_signature).split("/")[0])
        return cls(float(bpm), top, int(subdivisions), float(swing))

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.bpm

    def time_of(self, bar: int, onset: Fraction) -> float:
        """Seconds from the start of bar 1, applying swing to off-beat eighths."""
        whole = math.floor(onset)
        frac = onset - whole
        pos = float(whole) + (self.swing * 2 * float(frac) if frac == Fraction(1, 2) else float(frac))
        return (bar * self.beats_per_bar + pos) * self.seconds_per_beat

    def to_dict(self) -> dict:
        return {"bpm": self.bpm, "beats_per_bar": self.beats_per_bar,
                "subdivisions_per_beat": self.subdivisions_per_beat, "swing": self.swing}


@dataclass
class RhythmEvent:
    bar: int
    onset: Fraction
    duration: Fraction
    kind: str = "syllable"
    text: str = ""
    word: str = ""
    word_index: int = -1
    syllable_index: int = -1
    stressed: bool = False
    tuplet: str | None = None
    cell: str = ""
    syncopated: bool = False
    flam: bool = False
    lazy_tail: bool = False
    held: bool = False
    pickup: bool = False
    crosses_barline: bool = False
    rhyme_landing: bool = False
    rhyme_family: str | None = None
    breath: bool = False
    emphasis: bool = False
    region: str = "normal"
    time_s: float = 0.0

    def absolute(self, beats_per_bar: int) -> Fraction:
        return self.bar * beats_per_bar + self.onset

    def to_dict(self) -> dict:
        return {
            "bar": self.bar + 1, "onset": frac_str(self.onset), "onset_beats": round(float(self.onset), 4),
            "duration": frac_str(self.duration), "kind": self.kind, "text": self.text, "word": self.word,
            "stressed": self.stressed, "tuplet": self.tuplet, "cell": self.cell, "syncopated": self.syncopated,
            "flam": self.flam, "lazy_tail": self.lazy_tail, "held": self.held, "pickup": self.pickup,
            "crosses_barline": self.crosses_barline, "rhyme_landing": self.rhyme_landing,
            "rhyme_family": self.rhyme_family, "breath": self.breath, "emphasis": self.emphasis,
            "region": self.region, "time_s": round(self.time_s, 3),
        }


@dataclass
class SyllableSlot:
    """One syllable waiting to be placed on the grid."""

    word: str
    word_index: int
    syllable_index: int
    stressed: bool
    is_word_final: bool = False
    punct_after: str = ""
    elongate: bool = False
    emphasis: bool = False
    flam_with_next: bool = False
    label: str = ""


@dataclass
class BarInput:
    slots: list[SyllableSlot]
    cell: str | None = None
    region: str | None = None


@dataclass
class BarRhythm:
    bar: int
    cell: str
    family: str
    region: str
    syllables: int
    syllables_per_beat: float
    events: list[RhythmEvent]
    landing_onset: Fraction | None
    syncopation_ratio: float
    overcrowded: bool
    explicit_cell: bool
    notes: list[str] = field(default_factory=list)

    def grammar(self) -> dict:
        return {"cell": self.cell, "family": self.family, "density": round(self.syllables_per_beat, 3),
                "landing": frac_str(self.landing_onset), "syncopation": round(self.syncopation_ratio, 3),
                "region": self.region}

    def to_dict(self) -> dict:
        return {
            "bar": self.bar + 1, "cell": self.cell, "family": self.family, "region": self.region,
            "syllables": self.syllables, "syllables_per_beat": round(self.syllables_per_beat, 3),
            "landing_onset": frac_str(self.landing_onset), "syncopation_ratio": round(self.syncopation_ratio, 3),
            "overcrowded": self.overcrowded, "explicit_cell": self.explicit_cell, "notes": self.notes,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class RhythmGrid:
    grid: BeatGrid
    bars: list[BarRhythm]
    estimate_note: str = ESTIMATE_NOTE

    @property
    def events(self) -> list[RhythmEvent]:
        return [e for b in self.bars for e in b.events]

    def to_dict(self) -> dict:
        return {"grid": self.grid.to_dict(), "estimate_note": self.estimate_note, "bars": [b.to_dict() for b in self.bars]}

    def ascii(self) -> str:
        """Human view: one row per bar, x = stressed onset, o = unstressed, . = empty, | = beat line."""
        lines = [f"# {self.estimate_note}", f"# bpm {self.grid.bpm:g}, {self.grid.beats_per_bar} beats per bar"]
        for b in self.bars:
            step = CELL_LIBRARY[b.cell]["step"]
            per_beat = int(1 / step) if step <= 1 else 1
            cells = ["."] * (self.grid.beats_per_bar * per_beat)
            for e in b.events:
                if e.kind != "syllable" or e.onset < 0 or e.onset >= self.grid.beats_per_bar:
                    continue
                idx = int(e.onset / step)
                if 0 <= idx < len(cells):
                    cells[idx] = "x" if e.stressed else ("o" if cells[idx] == "." else cells[idx])
            row = "|".join("".join(cells[i:i + per_beat]) for i in range(0, len(cells), per_beat))
            flags = []
            if any(e.pickup for e in b.events):
                flags.append("pickup")
            if any(e.lazy_tail for e in b.events):
                flags.append("lazy tail")
            if any(e.flam for e in b.events):
                flags.append("flam")
            if b.overcrowded:
                flags.append("OVERCROWDED")
            words = " ".join(e.text for e in b.events if e.kind == "syllable")
            lines.append(f"{b.bar + 1:>3} {b.cell:<13} |{row}|  {words}" + (f"  [{', '.join(flags)}]" if flags else ""))
        return "\n".join(lines)


def metrical_weight(onset: Fraction, beats_per_bar: int, config: Config | None = None) -> float:
    """Strength of a grid position: downbeat strongest, fine subdivisions weakest."""
    w = resolve_config(config).rhythm["metrical_weights"]
    pos = Fraction(onset) % beats_per_bar
    if pos == 0:
        return w["downbeat"]
    if pos.denominator == 1:
        if beats_per_bar % 2 == 0 and pos == beats_per_bar // 2:
            return w["midbar"]
        return w["backbeat"]
    frac = pos - math.floor(pos)
    if frac == Fraction(1, 2):
        return w["half"]
    if frac.denominator == 3:
        return w["triplet"]
    if frac.denominator == 4:
        return w["quarter"]
    return w["finer"]


def is_syncopated(onset: Fraction, stressed: bool, beats_per_bar: int, config: Config | None = None) -> bool:
    cfg = resolve_config(config)
    return stressed and metrical_weight(onset, beats_per_bar, cfg) < cfg.rhythm["syncopation_max_weight"]


def _choose_cell(inp: BarInput, beats: int, cfg: Config) -> str:
    r = cfg.rhythm
    n = len(inp.slots)
    density = n / beats if beats else 0.0
    stressed_idx = [i for i, s in enumerate(inp.slots) if s.stressed]
    gaps = [b - a for a, b in zip(stressed_idx, stressed_idx[1:])]
    ternary = bool(gaps) and sum(1 for g in gaps if g == 3) / len(gaps) >= r["triplet_stress_ratio"]
    if r["triplet_density_min"] <= density <= r["triplet_density_max"] and ternary:
        return "triplet"
    for name, limit in r["density_bands"]:
        if density <= limit:
            return name
    return "thirty_second"


def estimate_bar(bar_index: int, inp: BarInput, grid: BeatGrid, config: Config | None = None) -> BarRhythm:
    cfg = resolve_config(config)
    r = cfg.rhythm
    beats = grid.beats_per_bar
    slots = inp.slots
    explicit = resolve_cell(inp.cell)
    cell = explicit or _choose_cell(inp, beats, cfg)
    notes: list[str] = []
    overcrowded = False
    landing = Fraction(int(r["end_landing_beat"]) - 1)
    max_pickup = Fraction(r["max_pickup_beats"]).limit_denominator(96)
    positions: list[Fraction] = []
    step = CELL_LIBRARY[cell]["step"]
    while True:
        step = CELL_LIBRARY[cell]["step"]
        units: list[Fraction] = []  # gap in steps before each slot
        prev_flam = False
        for k, s in enumerate(slots):
            if k == 0:
                units.append(Fraction(0))
                continue
            prev = slots[k - 1]
            gap = Fraction(1)
            if prev_flam:
                gap = Fraction(r["flam_offset_ratio"]).limit_denominator(96)
            elif prev.punct_after:
                rest = r["rest_steps_at_sentence_end"] if prev.punct_after in ".!?" else r["rest_steps_at_punctuation"]
                gap += int(rest)
            if prev.flam_with_next:
                gap = Fraction(r["flam_offset_ratio"]).limit_denominator(96)
            units.append(gap)
            prev_flam = False
        # cumulative offsets in steps from the first slot
        cum = []
        total = Fraction(0)
        for u in units:
            total += u
            cum.append(total)
        anchor = max((i for i, s in enumerate(slots) if s.stressed), default=len(slots) - 1) if slots else 0
        if slots:
            base = landing - cum[anchor] * step
            positions = [base + c * step for c in cum]
        earliest = positions[0] if positions else Fraction(0)
        if earliest < -max_pickup and not explicit and FINER_CELL.get(cell):
            notes.append(f"{cell} left {float(-earliest):.2f} beats of pickup; tried {FINER_CELL[cell]}")
            cell = FINER_CELL[cell]
            continue
        if earliest < -max_pickup:
            overcrowded = True
            notes.append("more syllables than the grid holds before the landing; delivery would need to rush")
        break
    density = len(slots) / beats if beats else 0.0
    if density > r["overcrowded_syllables_per_beat"]:
        overcrowded = True
    family = CELL_LIBRARY[cell]["family"]
    tuplet = CELL_LIBRARY[cell]["tuplet"]
    if inp.region:
        region = inp.region
    elif cell == "thirty_second" or cell == "sextuplet":
        region = "double_time"
    elif density <= r["half_time_max_density"]:
        region = "half_time"
    else:
        region = "normal"
    events: list[RhythmEvent] = []
    for k, (s, pos) in enumerate(zip(slots, positions)):
        ev = RhythmEvent(
            bar=bar_index, onset=pos, duration=step, kind="syllable", text=s.label or s.word, word=s.word,
            word_index=s.word_index, syllable_index=s.syllable_index, stressed=s.stressed, tuplet=tuplet,
            cell=cell, emphasis=s.emphasis, region=region,
        )
        if s.flam_with_next or (k > 0 and slots[k - 1].flam_with_next):
            ev.flam = True
        if pos < 0:
            ev.pickup = True
            ev.crosses_barline = True
        if pos >= beats:
            ev.crosses_barline = True
            ev.lazy_tail = True
        if s.elongate and s.is_word_final:
            ev.onset = pos + int(r["lazy_tail_delay_steps"]) * step
            ev.lazy_tail = True
            ev.held = True
        events.append(ev)
    # durations run to the next onset; the last syllable rings to the bar end
    for k, ev in enumerate(events):
        nxt = events[k + 1].onset if k + 1 < len(events) else max(Fraction(beats), ev.onset + step)
        ev.duration = max(step / 2, nxt - ev.onset)
        if ev.duration >= int(r["hold_min_steps"]) * step and k + 1 < len(events):
            ev.held = True
        ev.syncopated = is_syncopated(ev.onset, ev.stressed, beats, cfg)
    # explicit rest events for gaps
    rests: list[RhythmEvent] = []
    min_breath = Fraction(cfg.breath["min_breath_rest_beats"]).limit_denominator(96)
    cursor = Fraction(0)
    for k, ev in enumerate(events):
        if ev.onset > cursor and not ev.pickup:
            gap = ev.onset - cursor
            rests.append(RhythmEvent(bar=bar_index, onset=cursor, duration=gap, kind="rest", cell=cell, region=region,
                                     breath=gap >= min_breath, text="(rest)"))
        if k + 1 < len(events):
            natural_end = ev.onset + step
            if events[k + 1].onset - natural_end >= step:
                gap = events[k + 1].onset - natural_end
                ev.duration = step
                rests.append(RhythmEvent(bar=bar_index, onset=natural_end, duration=gap, kind="rest", cell=cell,
                                         region=region, breath=gap >= min_breath, text="(rest)"))
        cursor = max(cursor, ev.onset + ev.duration)
    if events:
        last = events[-1]
        end = last.onset + step
        if end < beats:
            last.duration = step
            rests.append(RhythmEvent(bar=bar_index, onset=end, duration=Fraction(beats) - end, kind="rest",
                                     cell=cell, region=region, breath=Fraction(beats) - end >= min_breath, text="(rest)"))
    all_events = sorted(events + rests, key=lambda e: (e.onset, 0 if e.kind == "rest" else 1))
    for ev in all_events:
        ev.time_s = grid.time_of(bar_index, ev.onset)
    stressed = [e for e in events if e.stressed]
    sync = sum(1 for e in stressed if e.syncopated) / len(stressed) if stressed else 0.0
    anchor_ev = next((e for e in reversed(events) if e.stressed), events[-1] if events else None)
    return BarRhythm(
        bar=bar_index, cell=cell, family=family, region=region, syllables=len(slots),
        syllables_per_beat=density, events=all_events, landing_onset=anchor_ev.onset if anchor_ev else None,
        syncopation_ratio=sync, overcrowded=overcrowded, explicit_cell=bool(explicit), notes=notes,
    )


def estimate_grid(bars: Sequence[BarInput], grid: BeatGrid | None = None, config: Config | None = None) -> RhythmGrid:
    cfg = resolve_config(config)
    grid = grid or BeatGrid(cfg.rhythm["default_bpm"], cfg.rhythm["default_beats_per_bar"], cfg.rhythm["default_subdivisions"], cfg.rhythm["swing"])
    return RhythmGrid(grid, [estimate_bar(i, b, grid, cfg) for i, b in enumerate(bars)])


def grid_from_cells(cells: Sequence[tuple[str, Sequence[bool]]], grid: BeatGrid | None = None, config: Config | None = None) -> RhythmGrid:
    """Build a grid directly from cells: [(cell_name, [stressed flags per step]), ...] one entry per bar.

    Useful for planning and for tests: each flag is one attack placed on the
    cell's step from the downbeat. ``None`` in the flag list is a rest.
    """
    cfg = resolve_config(config)
    grid = grid or BeatGrid()
    bars = []
    for bi, (cell_name, flags) in enumerate(cells):
        cell = resolve_cell(cell_name)
        step = CELL_LIBRARY[cell]["step"]
        events = []
        for k, flag in enumerate(flags):
            onset = k * step
            if flag is None:
                events.append(RhythmEvent(bi, onset, step, kind="rest", cell=cell, text="(rest)"))
                continue
            ev = RhythmEvent(bi, onset, step, text=f"s{k}", stressed=bool(flag), tuplet=CELL_LIBRARY[cell]["tuplet"], cell=cell)
            ev.syncopated = is_syncopated(onset, ev.stressed, grid.beats_per_bar, cfg)
            ev.time_s = grid.time_of(bi, onset)
            events.append(ev)
        syl = [e for e in events if e.kind == "syllable"]
        st = [e for e in syl if e.stressed]
        bars.append(BarRhythm(bi, cell, CELL_LIBRARY[cell]["family"], "normal", len(syl), len(syl) / grid.beats_per_bar,
                              events, st[-1].onset if st else None,
                              sum(1 for e in st if e.syncopated) / len(st) if st else 0.0, False, True))
    return RhythmGrid(grid, bars)
