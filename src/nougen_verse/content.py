"""Content layer: the content spine, bar jobs, specificity and genericness signals.

Generic lyrics usually fail on content before they fail on rhyme, so the
planner asks for a content spine first and every bar gets a job. The
analysis side here is lexical and heuristic: word lists, phrase lists and
simple structure checks. It cannot understand meaning, and it says so.
"""

from __future__ import annotations

import copy
import random
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .config import Config, load_data_json, resolve_config

BAR_JOBS = (
    "establish", "specify", "escalate", "contrast", "reveal",
    "misdirect", "punch", "callback", "pivot", "resolve_or_fracture",
)
JOB_DESCRIPTIONS = {
    "establish": "put the listener in a place, time or situation",
    "specify": "add a detail only this speaker would know",
    "escalate": "raise the stakes or the pressure from the bar before",
    "contrast": "set one thing against another",
    "reveal": "show something the listener did not know",
    "misdirect": "lead the listener toward the wrong expectation",
    "punch": "land a line that pays off the setup",
    "callback": "return to an earlier image or phrase with new meaning",
    "pivot": "turn the verse in a new direction",
    "resolve_or_fracture": "close the arc, or break it on purpose",
}
SPINE_QUESTIONS = {
    "what_happened": "What happened?",
    "who_wants_what": "Who wants what?",
    "what_changed": "What changed?",
    "concrete_objects": "What concrete objects exist?",
    "emotional_contradiction": "What is the emotional contradiction?",
    "speaker_only_fact": "What fact can only belong to this speaker?",
    "central_image": "What image carries the central claim?",
    "setup": "What is the setup?",
    "payoff": "What is the payoff?",
    "must_not_say_generically": "What must not be said generically?",
}
NUMBER_WORDS = {
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
    "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty",
    "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
}


@dataclass
class ContentSpine:
    what_happened: str = ""
    who_wants_what: str = ""
    what_changed: str = ""
    concrete_objects: list[str] = field(default_factory=list)
    emotional_contradiction: str = ""
    speaker_only_fact: str = ""
    central_image: str = ""
    setup: str = ""
    payoff: str = ""
    must_not_say_generically: list[str] = field(default_factory=list)

    def missing(self) -> list[str]:
        return [k for k in SPINE_QUESTIONS if not getattr(self, k)]

    def to_dict(self) -> dict:
        return {k: copy.deepcopy(getattr(self, k)) for k in SPINE_QUESTIONS}

    @classmethod
    def from_dict(cls, d: dict | None) -> "ContentSpine":
        d = d or {}
        kwargs = {}
        for k in SPINE_QUESTIONS:
            v = d.get(k)
            if k in ("concrete_objects", "must_not_say_generically"):
                kwargs[k] = list(v or [])
            else:
                kwargs[k] = str(v or "")
        return cls(**kwargs)


class Lexicons:
    """Lexicon lists from data/lexicons.json with config overrides.

    ``content.lexicon_overrides`` replaces a list by name; a key ending in
    ``+`` extends the list instead (for example ``{"cliche_terms+": ["hustle"]}``).
    """

    def __init__(self, config: Config | None = None):
        cfg = resolve_config(config)
        data = copy.deepcopy(load_data_json("lexicons.json"))
        for key, value in (cfg.get("content.lexicon_overrides") or {}).items():
            if key.endswith("+"):
                base = key[:-1]
                if isinstance(data.get(base), list):
                    data[base] = data[base] + list(value)
                elif isinstance(data.get(base), dict):
                    data[base] = {**data[base], **value}
            else:
                data[key] = value
        self.data = data
        self.stopwords = set(data["stopwords"])
        self.generic_verbs = set(data["generic_verbs"])
        self.vivid_verbs = set(data["vivid_verbs"])
        self.concrete = set(data["concrete_nouns"])
        self.people = set(data["people_nouns"])
        self.time_anchors = set(data["time_anchors"])
        self.sensory = set(data["sensory_words"])
        self.abstract = set(data["abstract_nouns"])
        self.abstract_suffixes = tuple(data["abstract_suffixes"])
        self.cliche_terms = set(data["cliche_terms"])
        self.generic_phrases = list(data["generic_phrases"])
        self.empty_victory = list(data["empty_victory"])
        self.unspecified_struggle = list(data["unspecified_struggle"])
        self.fillers = list(data["filler_intensifiers"])
        self.forced_endings = list(data["forced_syntax_endings"])
        self.forced_patterns = [re.compile(p) for p in data["forced_syntax_patterns"]]
        self.self_description = [re.compile(p) for p in data["self_description_patterns"]]
        self.predictable_pairs = {frozenset(p) for p in data["predictable_end_pairs"]}
        self.cues = data["cues"]
        self.emotion = data["emotion_lexicon"]
        self.registers = data["register_lexicons"]
        self.domains = data["metaphor_domains"]

    def is_abstract(self, word: str) -> bool:
        return word in self.abstract or (len(word) > 6 and word.endswith(self.abstract_suffixes))


def phrase_hits(norms: Sequence[str], phrases: Iterable[str]) -> list[str]:
    joined = " " + " ".join(norms) + " "
    return [p for p in phrases if f" {p} " in joined]


def light_stem(word: str) -> str:
    for suf in ("'s", "ies", "es", "s"):
        if word.endswith(suf) and len(word) > len(suf) + 2:
            return word[: -len(suf)] + ("y" if suf == "ies" else "")
    return word


def content_words(norms: Sequence[str], lex: Lexicons) -> list[str]:
    return [w for w in norms if w not in lex.stopwords and not w.isdigit() and len(w) > 1]


@dataclass
class BarContent:
    index: int
    text: str
    norms: list[str]
    surfaces: list[str]
    is_number: list[bool]
    content: list[str]
    concrete: list[str]
    sensory: list[str]
    abstract: list[str]
    proper: list[str]
    numbers: list[str]
    vivid: list[str]
    emotion_intensity: float
    emotion_valence: float
    cue_hits: dict[str, list[str]]
    template_key: tuple

    def anchors(self) -> list[str]:
        return sorted(set(self.concrete + self.proper + self.numbers))

    def to_dict(self) -> dict:
        return {"concrete": self.concrete, "sensory": self.sensory, "abstract": self.abstract, "proper": self.proper,
                "numbers": self.numbers, "vivid_verbs": self.vivid, "emotion_intensity": round(self.emotion_intensity, 3),
                "emotion_valence": round(self.emotion_valence, 3), "cues": self.cue_hits}


def template_key(norms: Sequence[str], lex: Lexicons, prefix: int) -> tuple:
    skel = []
    for w in norms:
        tok = w if w in lex.stopwords else "_"
        if skel and tok == "_" and skel[-1] == "_":
            continue
        skel.append(tok)
    pronouns = {"i", "we", "you", "he", "she", "they"}
    conj = None
    for a, b in zip(norms, norms[1:]):
        if a in ("and", "but", "so", "then") and b in pronouns:
            conj = (a, b)
            break
    return (tuple(skel[:prefix]), conj)


def bar_content(index: int, text: str, tokens: Sequence, lex: Lexicons, extra_concrete: Iterable[str] = (), config: Config | None = None) -> BarContent:
    cfg = resolve_config(config)
    norms = [t.norm for t in tokens]
    surfaces = [t.surface for t in tokens]
    extra = {light_stem(w.lower()) for w in extra_concrete}
    content = content_words(norms, lex)
    concrete, sensory, abstract, proper, numbers, vivid = [], [], [], [], [], []
    for k, t in enumerate(tokens):
        w = t.norm
        stem = light_stem(w)
        if t.is_number or w in NUMBER_WORDS:
            numbers.append(w)
        if w in lex.concrete or stem in lex.concrete or w in lex.people or stem in lex.people or w in lex.time_anchors or stem in extra:
            concrete.append(w)
        if w in lex.sensory or stem in lex.sensory:
            sensory.append(w)
        if lex.is_abstract(w):
            abstract.append(w)
        if w in lex.vivid_verbs or (w.endswith("ed") and len(w) > 4 and w not in lex.generic_verbs and w not in lex.stopwords):
            vivid.append(w)
        if k > 0 and t.surface[:1].isupper() and w not in lex.stopwords and w != "i" and not t.is_number:
            proper.append(t.surface)
    inten, val = 0.0, 0.0
    for w in norms:
        if w in lex.emotion:
            v, i = lex.emotion[w]
            if i > inten:
                inten, val = float(i), float(v)
    cues = {kind: phrase_hits(norms, phrases) for kind, phrases in lex.cues.items()}
    cues = {k: v for k, v in cues.items() if v}
    return BarContent(index, text, norms, surfaces, [t.is_number for t in tokens], content, concrete, sensory, abstract,
                      proper, numbers, vivid, inten, val, cues,
                      template_key(norms, lex, int(cfg.content["template_similarity_prefix"])))


# ----------------------------------------------------------------------------
# generic phrase and cliche flags


def generic_flags(bar: BarContent, lex: Lexicons, config: Config | None = None) -> list[dict]:
    """Per-bar genericness flags. Each flag names its rule and the words that triggered it."""
    cfg = resolve_config(config)
    flags: list[dict] = []
    has_anchor = bool(bar.anchors())
    for term in sorted(set(w for w in bar.norms if w in lex.cliche_terms)):
        if has_anchor:
            flags.append({"rule": "supported_cliche", "evidence": term, "penalized": False,
                          "note": "cliche word with concrete support in the same bar"})
        else:
            flags.append({"rule": "unsupported_cliche", "evidence": term, "penalized": True})
    for p in phrase_hits(bar.norms, lex.generic_phrases):
        flags.append({"rule": "generic_phrase", "evidence": p, "penalized": True})
    for p in phrase_hits(bar.norms, lex.empty_victory):
        flags.append({"rule": "empty_victory", "evidence": p, "penalized": True})
    for p in phrase_hits(bar.norms, lex.unspecified_struggle):
        if not has_anchor:
            flags.append({"rule": "unspecified_struggle", "evidence": p, "penalized": True})
    for p in phrase_hits(bar.norms, lex.fillers):
        flags.append({"rule": "filler_intensifier", "evidence": p, "penalized": True})
    if len(bar.abstract) >= int(cfg.content["abstract_stack_min"]) and not bar.concrete:
        flags.append({"rule": "abstract_stack", "evidence": " ".join(bar.abstract), "penalized": True})
    joined = " ".join(bar.norms)
    ending = " ".join(bar.norms[-3:])
    for e in lex.forced_endings:
        if ending.endswith(e):
            flags.append({"rule": "forced_syntax", "evidence": f"rhyme filler ending {e!r}", "penalized": True})
            break
    for pat in lex.forced_patterns:
        m = pat.search(joined)
        if m:
            flags.append({"rule": "forced_syntax", "evidence": f"inverted word order {m.group(0)!r}", "penalized": True})
            break
    return flags


def self_description_bars(bars: Sequence[BarContent], lex: Lexicons) -> list[int]:
    out = []
    for b in bars:
        joined = " ".join(b.norms)
        if any(p.search(joined) for p in lex.self_description):
            out.append(b.index)
    return out


def repeated_templates(bars: Sequence[BarContent], config: Config | None = None) -> list[list[int]]:
    cfg = resolve_config(config)
    groups: dict[tuple, list[int]] = {}
    for b in bars:
        if len(b.norms) >= 3:
            groups.setdefault(b.template_key, []).append(b.index)
    min_rep = int(cfg.content["template_repeat_min"])
    return sorted([idx for idx in groups.values() if len(idx) >= min_rep], key=lambda g: g[0])


def semantic_repetition(bars: Sequence[BarContent], config: Config | None = None, window: int | None = None) -> list[dict]:
    """Bar pairs whose content words overlap heavily (a stand-in for restating the same idea).

    ``window`` is how many following bars each bar is compared against; it
    defaults to ``content.semantic_repeat_window_bars`` in the config.
    """
    cfg = resolve_config(config)
    limit = float(cfg.content["semantic_repeat_jaccard"])
    if window is None:
        window = int(cfg.content["semantic_repeat_window_bars"])
    out = []
    for i, a in enumerate(bars):
        sa = {light_stem(w) for w in a.content}
        if len(sa) < 2:
            continue
        for b in bars[i + 1:i + 1 + window]:
            sb = {light_stem(w) for w in b.content}
            if len(sb) < 2:
                continue
            j = len(sa & sb) / len(sa | sb)
            if j >= limit:
                out.append({"bars": [a.index + 1, b.index + 1], "jaccard": round(j, 3), "shared": sorted(sa & sb)})
    return out


def lexical_repetition(bars: Sequence[BarContent]) -> dict:
    words = [light_stem(w) for b in bars for w in b.content]
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    repeated = sorted(((w, c) for w, c in counts.items() if c > 1), key=lambda x: (-x[1], x[0]))
    ttr = len(counts) / len(words) if words else 0.0
    return {"content_words": len(words), "unique_content_words": len(counts), "type_token_ratio": round(ttr, 3),
            "repeated": [{"word": w, "count": c} for w, c in repeated[:20]]}


def required_fact_retention(bars: Sequence[BarContent], facts: Sequence[str], lex: Lexicons, config: Config | None = None) -> dict:
    cfg = resolve_config(config)
    need = float(cfg.content["fact_match_min_fraction"])
    from .phonetics import tokenize  # local import keeps module import light

    results = []
    for fact in facts:
        fwords = [light_stem(t.norm) for t in tokenize(fact) if t.norm not in lex.stopwords] or [light_stem(t.norm) for t in tokenize(fact)]
        found_bars = []
        present = set()
        for b in bars:
            stems = {light_stem(w) for w in b.norms}
            hit = [w for w in fwords if w in stems]
            if hit:
                found_bars.append(b.index + 1)
                present.update(hit)
        frac = len(present) / len(fwords) if fwords else 0.0
        results.append({"fact": fact, "retained": frac >= need, "coverage": round(frac, 3), "bars": found_bars,
                        "missing_words": sorted(set(fwords) - present)})
    retained = sum(1 for r in results if r["retained"])
    return {"facts": results, "retained": retained, "total": len(results),
            "retention": round(retained / len(results), 3) if results else None}


def emotional_progression(bars: Sequence[BarContent], config: Config | None = None) -> dict:
    cfg = resolve_config(config)
    curve = [b.emotion_intensity for b in bars]
    valence = [b.emotion_valence for b in bars]
    if not curve:
        return {"curve": [], "valence": [], "range": 0.0, "flat": True, "direction": "none"}
    rng = max(curve) - min(curve)
    half = max(1, len(curve) // 2)
    first, second = sum(curve[:half]) / half, sum(curve[half:]) / max(1, len(curve) - half)
    delta = float(cfg.content["emotion_direction_delta"])
    direction = "rising" if second - first > delta else ("falling" if first - second > delta else "level")
    return {"curve": [round(c, 3) for c in curve], "valence": [round(v, 3) for v in valence], "range": round(rng, 3),
            "flat": rng < float(cfg.content["emotion_flat_range"]), "direction": direction,
            "note": "Estimated from an emotion word list; it cannot hear tone or read subtext."}


def callbacks(bars: Sequence[BarContent], config: Config | None = None) -> list[dict]:
    """Concrete words that return after a gap: evidence of setup and payoff or image transformation."""
    cfg = resolve_config(config)
    gap = int(cfg.content["callback_min_distance"])
    out = []
    seen: dict[str, int] = {}
    for b in bars:
        for w in sorted(set(light_stem(x) for x in b.concrete + b.proper)):
            if w in seen and b.index - seen[w] >= gap:
                out.append({"word": w, "setup_bar": seen[w] + 1, "payoff_bar": b.index + 1})
            seen.setdefault(w, b.index)
    return out


def progression_rate(bars: Sequence[BarContent]) -> float:
    """Share of each bar's content words not seen earlier, averaged (new information per bar)."""
    seen: set[str] = set()
    rates = []
    for b in bars:
        words = {light_stem(w) for w in b.content}
        if not words:
            rates.append(0.0)
            continue
        new = words - seen
        rates.append(len(new) / len(words))
        seen |= words
    return sum(rates) / len(rates) if rates else 0.0


# ----------------------------------------------------------------------------
# bar jobs


def infer_bar_jobs(
    bars: Sequence[BarContent],
    rhymed: Sequence[bool],
    switch_bars: Iterable[int] = (),
    config: Config | None = None,
) -> list[dict]:
    """Guess a job per bar from position, cues and anchors. Low confidence by design."""
    cfg = resolve_config(config)
    conf = cfg.content["job_confidence"]
    punch_every = int(cfg.planner["punch_every_bars"])
    delta = float(cfg.content["emotion_escalation_delta"])
    switch_set = {b - 1 for b in switch_bars}
    cb = {c["payoff_bar"] - 1 for c in callbacks(bars, cfg)}
    out = []
    n = len(bars)
    for b in bars:
        i = b.index
        job, c, why = None, conf["fallback"], "no clear signal"
        if i == 0:
            job, c, why = "establish", conf["position"], "first bar"
        elif i == n - 1:
            job, c, why = "resolve_or_fracture", conf["position"], "last bar"
        elif i in switch_set:
            job, c, why = "pivot", conf["cue"], "flow switch lands here"
        elif b.cue_hits.get("reveal"):
            job, c, why = "reveal", conf["cue"], f"reveal cue {b.cue_hits['reveal'][0]!r}"
        elif i in cb:
            job, c, why = "callback", conf["cue"], "returns to an earlier concrete image"
        elif b.cue_hits.get("contrast") and b.norms and b.norms[0] in b.cue_hits["contrast"]:
            job, c, why = "contrast", conf["cue"], f"opens with {b.norms[0]!r}"
        elif i > 0 and b.emotion_intensity - bars[i - 1].emotion_intensity >= delta:
            job, c, why = "escalate", conf["cue"], "emotional intensity rises"
        elif (i + 1) % punch_every == 0 and rhymed[i] and b.anchors():
            job, c, why = "punch", conf["rhyme_position"], "end of a four-bar group with a rhymed, anchored line"
        elif b.anchors():
            job, c, why = "specify", conf["anchor"], "carries concrete anchors: " + ", ".join(b.anchors()[:3])
        elif b.cue_hits.get("contrast"):
            job, c, why = "contrast", conf["weak_cue"], f"contrast cue {b.cue_hits['contrast'][0]!r}"
        out.append({"bar": i + 1, "job": job or "unclear", "confidence": round(float(c), 3), "evidence": why})
    return out


def assign_bar_jobs(
    bar_count: int,
    seed: int = 0,
    switch_bars: Iterable[int] = (),
    callback_bars: Iterable[int] = (),
    punch_bars: Iterable[int] = (),
    config: Config | None = None,
) -> list[str]:
    """Deterministic job plan for ``bar_count`` bars (bar numbers in the iterables are 1-based)."""
    cfg = resolve_config(config)
    rng = random.Random(seed)
    punch_every = int(cfg.planner["punch_every_bars"])
    switch_set = {b - 1 for b in switch_bars}
    callback_set = {b - 1 for b in callback_bars}
    punch_set = {b - 1 for b in punch_bars}
    jobs: list[str] = []
    reveal_at = max(1, round(bar_count * float(cfg.planner["reveal_position"])) - 1) if bar_count >= punch_every else -1
    misdirect_p = float(cfg.planner["misdirect_probability"])
    middle_pool = ["specify", "escalate", "contrast", "specify", "escalate"]
    for i in range(bar_count):
        if i == 0:
            job = "establish"
        elif i == bar_count - 1:
            job = "resolve_or_fracture"
        elif i in switch_set:
            job = "pivot"
        elif i in callback_set:
            job = "callback"
        elif i in punch_set or ((i + 1) % punch_every == 0):
            job = "punch"
        elif i == reveal_at:
            job = "reveal"
        elif (i + 2) % punch_every == 0 and i + 1 < bar_count - 1 and rng.random() < misdirect_p:
            job = "misdirect"
        elif i == 1:
            job = "specify"
        else:
            job = middle_pool[rng.randrange(len(middle_pool))]
        jobs.append(job)
    return jobs
