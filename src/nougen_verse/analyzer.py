"""ANALYZE mode: deterministic, offline diagnostics for a user-owned draft.

One non-empty line is one bar. Optional tags in square brackets at the start
of a line steer the analysis:

- a cadence cell: ``[triplet]``, ``[eighth]``, ``[sixteenth]``, ``[double-time]``, ``[half-time]``
- a flow switch and its cause: ``[switch:reveal]`` (causes are listed in ``flow.FLOW_SWITCH_CAUSES``)
- a deliberate scheme break: ``[break]``
- a deliberately layered bar (pun, double entendre, acronym, coded reference): ``[wordplay]``
- delivery intensity for breath estimates: ``[intensity:0.8]``
- anything else, such as ``[Verse 1]``, is treated as a section label.

Inline markers: ``word~`` elongates a word or marks a lazy tail, ``>word``
marks emphasis, ``b-b-back`` is a stutter (modeled as a flam).

No network, no model. Every number here is a heuristic estimate.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from . import content as C
from .breath import analyze_breath
from .config import Config, resolve_config
from .flow import detect_flow_switches, normalize_cause
from .models import VerseAnalysis, VerseBlueprint
from .persona import Persona, load_persona, persona_consistency
from .phonetics import (
    PhoneticDictionary,
    Pronunciation,
    get_dictionary,
    phrase_syllables,
    token_pronunciations,
    tokenize,
)
from .rhyme import KIND_RANK, RhymeScorer, family_label
from .rhythm import CELL_ALIASES, CELL_LIBRARY, BarInput, BeatGrid, SyllableSlot, estimate_grid, resolve_cell

BASE_LIMITATIONS = [
    "Cadence is estimated from text only: syllable counts, stress, punctuation and markers. Without audio the grid is a sketch, not a transcription.",
    "Pronunciations may come from spelling heuristics; accents differ and no single pronunciation is treated as correct. Register overrides for names, slang and your own delivery.",
    "Genericness, specificity and persona checks use editable word lists. They flag patterns; they do not understand meaning, irony or subtext.",
    "Scores are heuristics for revision, not a measure of artistic quality.",
    "Intentional versus accidental scheme breaks is a guess from nearby cues and is reported with a confidence.",
]


@dataclass
class ParsedBar:
    index: int
    raw: str
    text: str
    tags: dict = field(default_factory=dict)


_TAG_BLOCK = re.compile(r"^\s*((?:\[[^\]]*\]\s*)+)")

# Tags that mark a bar as deliberately layered: the surface text is thin on purpose.
_WORDPLAY_TAGS = frozenset({"wordplay", "pun", "layered", "coded"})

# Words that have a distinctive homophone. A bar that would otherwise read as filler but contains one
# of these MAY be a double reading ("I no micro" = "I'm no micro" + "I know micro"). This is a hint
# that protects the bar from repair advice, never proof; extend it with your own pairs.
_HOMOPHONE_HINTS = {
    "no": "know", "know": "no", "knows": "nose", "nose": "knows", "hear": "here", "here": "hear",
    "night": "knight", "knight": "night", "sun": "son", "son": "sun", "tale": "tail", "tail": "tale",
    "soul": "sole", "sole": "soul", "sight": "site", "site": "sight", "cite": "site", "peace": "piece",
    "piece": "peace", "real": "reel", "reel": "real", "weak": "week", "week": "weak", "waste": "waist",
    "waist": "waste", "bare": "bear", "bear": "bare", "hi": "high", "high": "hi", "rose": "rows",
    "rows": "rose", "mail": "male", "male": "mail", "wear": "where", "where": "wear", "sea": "see",
    "see": "sea", "mite": "might", "might": "mite", "cell": "sell", "sell": "cell", "bored": "board",
    "board": "bored", "cash": "cache", "cache": "cash",
}
SEMANTIC_DENSITY_LABEL = "LOW SURFACE INFORMATION / HIGH POSSIBLE SEMANTIC DENSITY"


def _semantic_density_evidence(pb_tags: dict, text: str) -> list[str]:
    """Why a surface-weak bar might be carrying meaning the word lists cannot see."""
    if pb_tags.get("wordplay"):
        return ["tagged [wordplay]"]
    words = re.findall(r"[a-z']+", text.lower())
    return [f"homophone hint: {w}~{_HOMOPHONE_HINTS[w]}" for w in dict.fromkeys(words) if w in _HOMOPHONE_HINTS]


def _parse_tags(block: str) -> dict:
    tags: dict[str, Any] = {}
    for inner in re.findall(r"\[([^\]]*)\]", block):
        for raw in re.split(r"[,\s]+", inner.strip()):
            item = raw.strip().lower()
            if not item:
                continue
            key, _, val = item.partition(":")
            if key == "switch":
                tags["switch"] = normalize_cause(val) if val else True
            elif key == "break":
                tags["break"] = True
            elif key in _WORDPLAY_TAGS:
                tags["wordplay"] = True
            elif key == "intensity":
                try:
                    tags["intensity"] = float(val)
                except ValueError:
                    pass
            elif key in CELL_LIBRARY or key in CELL_ALIASES:
                tags["cell"] = resolve_cell(key)
                if key in ("half", "half-time", "half_time"):
                    tags["region"] = "half_time"
                if key in ("double", "double-time", "double_time"):
                    tags["region"] = "double_time"
            else:
                tags.setdefault("section", inner.strip())
    return tags


def parse_lines(text: str) -> list[ParsedBar]:
    bars: list[ParsedBar] = []
    pending: dict = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tags = {}
        m = _TAG_BLOCK.match(line)
        if m:
            tags = _parse_tags(m.group(1))
            line = line[m.end():].strip()
        if not line:
            pending.update(tags)
            continue
        merged = {**pending, **tags}
        pending = {}
        bars.append(ParsedBar(len(bars), raw, line, merged))
    return bars


@dataclass
class AnalysisContext:
    bpm: float | None = None
    beats_per_bar: int | None = None
    subdivisions_per_beat: int | None = None
    time_signature: str | None = None
    swing: float | None = None
    persona: Any = None
    required_facts: list[str] = field(default_factory=list)
    scheme: str | None = None
    blueprint: Any = None
    breath_profile: Any = None
    dialect: Any = None
    pronunciations: dict = field(default_factory=dict)
    dictionary: PhoneticDictionary | None = None
    config: Any = None
    include_grid: bool = True
    forbidden_phrases: list[str] = field(default_factory=list)
    imagery_domains: list[str] = field(default_factory=list)

    @classmethod
    def from_any(cls, ctx: Any) -> "AnalysisContext":
        if ctx is None:
            return cls()
        if isinstance(ctx, AnalysisContext):
            return ctx
        if isinstance(ctx, dict):
            names = set(cls.__dataclass_fields__)
            return cls(**{k: v for k, v in ctx.items() if k in names})
        raise TypeError("context must be an AnalysisContext, a dict, or None")


def _dictionary_for(ctx: AnalysisContext, cfg: Config, persona: Persona | None) -> PhoneticDictionary:
    if ctx.dictionary is not None:
        d = ctx.dictionary
        extra = dict(persona.pronunciation_overrides) if persona else {}
        extra.update(ctx.pronunciations or {})
        for w, ph in extra.items():
            d.register(w, ph)
        return d
    overrides = dict(persona.pronunciation_overrides) if persona else {}
    overrides.update(ctx.pronunciations or {})
    if overrides or ctx.dialect is not None:
        return PhoneticDictionary(cfg, overrides=overrides, dialect=ctx.dialect)
    return get_dictionary(cfg)


def _blueprint_dict(bp: Any) -> dict | None:
    if bp is None:
        return None
    if isinstance(bp, VerseBlueprint):
        return bp.to_dict()
    return dict(bp)


def _expand_scheme(pattern: str, n: int) -> list[str | None]:
    """Expand 'AABB' over n bars into group-scoped labels like '0A','0A','0B','0B','1A',..; X means no expectation."""
    pat = pattern.replace(" ", "").upper()
    out: list[str | None] = []
    for i in range(n):
        ch = pat[i % len(pat)]
        out.append(None if ch == "X" else f"{i // len(pat)}{ch}")
    return out


def _expected_pairs(pattern: str, n: int) -> list[tuple[int, int]]:
    labels = _expand_scheme(pattern, n)
    pairs = []
    for i in range(n):
        if labels[i] is None:
            continue
        for j in range(i + 1, n):
            if labels[j] == labels[i]:
                pairs.append((i, j))
                break
    return pairs


def _empty_analysis(cfg: Config, reason: str) -> VerseAnalysis:
    return VerseAnalysis(
        counts={"lines": 0, "bars": 0, "tokens": 0}, syllables={"total": 0, "per_bar": []}, stress_patterns=[],
        end_rhyme_families=[], internal_rhyme_families=[], multisyllabic_chains=[], compound_and_slant_candidates=[],
        rhyme_density=0.0, rhyme_span={"mean": 0.0, "max": 0}, scheme={"letters": "", "inferred_pattern": "none", "consistency": 0.0, "expected": None},
        pattern_changes=[], scheme_breaks=[], pattern_collapses=[], cadence={"consistency": 0.0, "landing_consistency": 0.0, "syllables_per_beat": [], "cells": []},
        overcrowded_bars=[], breath={"profile": cfg.breath["profile"], "groups": [], "warnings": [], "max_pressure": 0.0, "breath_opportunities": 0, "note": ""},
        lexical_repetition={"content_words": 0, "unique_content_words": 0, "type_token_ratio": 0.0, "repeated": []},
        semantic_repetition=[], generic_flags=[], concrete_noun_density=0.0, sensory_detail_density=0.0,
        named_fact_retention={"facts": [], "retained": 0, "total": 0, "retention": None}, persona_consistency=None,
        emotional_progression={"curve": [], "valence": [], "range": 0.0, "flat": True, "direction": "none"},
        setup_payoff={"links": [], "callbacks": [], "integrity": None}, weak_bars=[], repair_recommendations=[],
        confidence={"pronunciation_mean": 0.0, "heuristic_share": 0.0, "dictionary_backend": "none", "low_confidence_words": []},
        limitations=[reason] + BASE_LIMITATIONS, grid=None,
    )


def analyze_verse(text: str, context: Any = None) -> VerseAnalysis:
    """Analyze a draft. ``context`` may be an AnalysisContext, a dict of its fields, or None."""
    ctx = AnalysisContext.from_any(context)
    cfg = resolve_config(ctx.config)
    bars = parse_lines(text)
    if not bars:
        return _empty_analysis(cfg, "Empty input: there were no bars to analyze.")
    lex = C.Lexicons(cfg)
    persona = load_persona(ctx.persona, cfg) if ctx.persona is not None else None
    bp = _blueprint_dict(ctx.blueprint)
    if persona is None and bp and bp.get("persona"):
        persona = load_persona(bp["persona"], cfg)
    d = _dictionary_for(ctx, cfg, persona)
    scorer = RhymeScorer(cfg)
    demote = lex.stopwords if cfg.phonetics.get("demote_function_words", True) else set()

    # ---- grid ---------------------------------------------------------------
    bp_grid = (bp or {}).get("grid") or {}
    beats = ctx.beats_per_bar or (int(str(ctx.time_signature).split("/")[0]) if ctx.time_signature else None) or bp_grid.get("beats_per_bar") or cfg.rhythm["default_beats_per_bar"]
    grid = BeatGrid(
        float(ctx.bpm or bp_grid.get("bpm") or cfg.rhythm["default_bpm"]), int(beats),
        int(ctx.subdivisions_per_beat or bp_grid.get("subdivisions_per_beat") or cfg.rhythm["default_subdivisions"]),
        float(ctx.swing if ctx.swing is not None else bp_grid.get("swing", cfg.rhythm["swing"])),
    )

    # ---- per bar phonetics ------------------------------------------------
    bar_tokens, bar_prons, bar_sylls, bar_inputs, slot_infos = [], [], [], [], []
    for pb in bars:
        toks = tokenize(pb.text)
        prons = token_pronunciations(toks, d)
        sylls = phrase_syllables(toks, prons, demote)
        bar_tokens.append(toks)
        bar_prons.append(prons)
        bar_sylls.append(sylls)
        slots: list[SyllableSlot] = []
        infos = []
        by_word: dict[int, list] = {}
        for s in sylls:
            by_word.setdefault(s.word_index, []).append(s)
        for wi, tok in enumerate(toks):
            ws = by_word.get(wi, [])
            for _ in range(tok.stutter):
                slots.append(SyllableSlot(tok.norm, wi, -1, bool(ws and ws[0].stressed), False, "", False, False, True, label=tok.norm[:1] + "-"))
                infos.append(None)
            repeat_next = wi + 1 < len(toks) and toks[wi + 1].norm == tok.norm
            for k, s in enumerate(ws):
                final = k == len(ws) - 1
                slots.append(SyllableSlot(
                    tok.norm, wi, s.syllable_in_word, s.stressed, final,
                    tok.punct_after if final else "", final and "elongate" in tok.markers,
                    "emphasis" in tok.markers, final and repeat_next,
                    label=tok.surface if len(ws) == 1 else f"{tok.norm}[{k + 1}]",
                ))
                infos.append(s)
        bar_inputs.append(BarInput(slots, pb.tags.get("cell"), pb.tags.get("region")))
        slot_infos.append(infos)
    rhythm = estimate_grid(bar_inputs, grid, cfg)
    n = len(bars)

    # ---- end rhyme families ---------------------------------------------------
    end_prons: list[Pronunciation | None] = [p[-1] if p else None for p in bar_prons]
    families: list[dict] = []
    bar_family: list[int | None] = [None] * n
    pair_records: list[dict] = []
    join_max = float(cfg.rhyme["family_join_max_distance"])
    fam_window = int(cfg.rhyme["family_window_bars"])
    vowel_gate = float(cfg.rhyme["assonance_vowel_max"])
    # every pronunciation variant of an end word takes part (cost as K AA S T or K AO S T)
    end_variants: list[list[Pronunciation]] = []
    for toks, prons in zip(bar_tokens, bar_prons):
        if toks and len(toks[-1].spoken) == 1:
            end_variants.append(d.pronounce_all(toks[-1].spoken[0]))
        else:
            end_variants.append([prons[-1]] if prons else [])

    def end_match(j: int, i: int):
        """Closest rhyme match between the end words of bars j and i across pronunciation variants."""
        best = None
        for a_ in end_variants[j]:
            for b_ in end_variants[i]:
                m = scorer.compare(a_, b_)
                if best is None or (m.distance, KIND_RANK[m.kind]) < (best.distance, KIND_RANK[best.kind]):
                    best = m
        return best
    for i in range(n):
        if end_prons[i] is None or not end_prons[i].syllables:
            continue
        best = None
        for fi, fam in enumerate(families):
            if i - fam["members"][-1] > fam_window:
                continue
            for j in fam["members"]:
                m = end_match(j, i)
                multi = scorer.multisyllabic(bar_sylls[j], bar_sylls[i])
                ok = (m.is_rhyme and m.distance <= join_max) or (multi.syllables >= 2 and m.vowel_distance <= vowel_gate)
                if ok:
                    key = (m.distance, -j)
                    if best is None or key < best[0]:
                        best = (key, fi, j, m, multi)
        if best:
            _, fi, j, m, multi = best
            families[fi]["members"].append(i)
            bar_family[i] = fi
            pair_records.append({"bars": [j + 1, i + 1], "words": [m.a, m.b], "kind": m.kind, "distance": round(m.distance, 4),
                                 "multi_syllables": multi.syllables, "multi_kind": multi.kind})
        else:
            families.append({"members": [i]})
            bar_family[i] = len(families) - 1
    labels = [family_label(k) for k in range(len(families))]
    end_families_out = []
    for fi, fam in enumerate(families):
        mem = fam["members"]
        recs = [r for r in pair_records if r["bars"][1] - 1 in mem]
        kinds: dict[str, int] = {}
        for r in recs:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        end_families_out.append({
            "label": labels[fi], "bars": [m + 1 for m in mem], "words": [end_prons[m].word for m in mem],
            "rhymed": len(mem) > 1, "kinds": kinds, "tail": " ".join(end_prons[mem[0]].phones[-4:]),
        })
    letters = "".join(labels[bar_family[i]] if bar_family[i] is not None else "-" for i in range(n))
    rhymed = [bar_family[i] is not None and len(families[bar_family[i]]["members"]) > 1 for i in range(n)]
    end_label = [labels[bar_family[i]] if bar_family[i] is not None else None for i in range(n)]

    # ---- multisyllabic chains and compound / slant ---------------------------
    chains, candidates = [], []
    seen_pairs = set()
    for r in pair_records:
        a, b = r["bars"][0] - 1, r["bars"][1] - 1
        seen_pairs.add((a, b))
    for i in range(n - 1):
        seen_pairs.add((i, i + 1))
    for a, b in sorted(seen_pairs):
        multi = scorer.multisyllabic(bar_sylls[a], bar_sylls[b])
        if multi.kind != "none":
            chains.append({"bars": [a + 1, b + 1], **multi.to_dict()})
            if multi.kind in ("compound", "mosaic"):
                candidates.append({"type": multi.kind, "bars": [a + 1, b + 1], "a": " ".join(multi.words_a), "b": " ".join(multi.words_b),
                                   "syllables": multi.syllables, "confidence": round(multi.confidence, 3)})
    for r in pair_records:
        if r["kind"] == "slant":
            candidates.append({"type": "slant", "bars": r["bars"], "a": r["words"][0], "b": r["words"][1], "distance": r["distance"]})

    # ---- internal rhyme --------------------------------------------------------
    internal_max = float(cfg.rhyme["internal_max_distance"])
    window = int(cfg.rhyme["internal_window_bars"])
    internal_hits = []
    hit_keys = set()
    for i in range(n):
        toks, prons = bar_tokens[i], bar_prons[i]
        cand_idx = [k for k in range(len(toks) - 1) if toks[k].norm not in lex.stopwords and prons[k].syllables]
        targets = []
        for k in cand_idx:
            targets.append((i, k, False))
        for j in range(max(0, i - window), min(n, i + window + 1)):
            if bar_prons[j]:
                targets.append((j, len(bar_prons[j]) - 1, True))
        for k in cand_idx:
            for (j, t, is_end) in targets:
                if j == i and t == k:
                    continue
                if not is_end and (j, t) <= (i, k):
                    continue
                w1, w2 = toks[k].norm, bar_tokens[j][t].norm
                if w1 == w2:
                    continue
                m = scorer.compare(prons[k], bar_prons[j][t])
                if m.kind in ("exact", "perfect", "slant") and m.distance <= internal_max:
                    key = (i, k, j, t)
                    if key in hit_keys:
                        continue
                    hit_keys.add(key)
                    internal_hits.append({"bar": i + 1, "word": w1, "position": k, "matched_bar": j + 1, "matched_word": w2,
                                          "matched_position": t, "matched_is_end": is_end, "kind": m.kind,
                                          "distance": round(m.distance, 4),
                                          "end_family": end_label[j] if is_end else None})
    # group internal hits into families with union-find over words
    parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for h in internal_hits:
        a, b = (h["bar"] - 1, h["position"]), (h["matched_bar"] - 1, h["matched_position"])
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for x in list(parent):
        groups.setdefault(find(x), []).append(x)
    internal_families = []
    for gi, (root, members) in enumerate(sorted(groups.items())):
        members = sorted(members)
        internal_families.append({"label": f"i{gi + 1}", "bars": sorted({m[0] + 1 for m in members}),
                                  "words": [bar_tokens[m[0]][m[1]].norm for m in members]})

    # ---- rhyme density and span ----------------------------------------------
    total_sylls = sum(len(s) for s in bar_sylls)
    rhymed_sylls: set[tuple[int, int, int]] = set()
    for i in range(n):
        if rhymed[i] and end_prons[i] is not None:
            wi = len(bar_prons[i]) - 1
            pr = end_prons[i]
            start = pr.stressed_index()
            for si in range(max(0, start), pr.syllable_count):
                rhymed_sylls.add((i, wi, si))
    for h in internal_hits:
        for (b, p) in ((h["bar"] - 1, h["position"]), (h["matched_bar"] - 1, h["matched_position"])):
            pr = bar_prons[b][p]
            for si in range(max(0, pr.stressed_index()), pr.syllable_count):
                rhymed_sylls.add((b, p, si))
    for ch in chains:
        for b_idx, key in ((ch["bars"][0] - 1, "a"), (ch["bars"][1] - 1, "b")):
            sy = bar_sylls[b_idx]
            for s in sy[len(sy) - ch["syllables"]:]:
                rhymed_sylls.add((b_idx, s.word_index, s.syllable_in_word))
    density = len(rhymed_sylls) / total_sylls if total_sylls else 0.0
    spans = []
    for r in pair_records:
        tail = end_prons[r["bars"][1] - 1]
        spans.append(max(r["multi_syllables"], len(tail.tail_syllables()) if tail else 1))
    rhyme_span = {"mean": round(sum(spans) / len(spans), 3) if spans else 0.0, "max": max(spans) if spans else 0}

    # ---- scheme ----------------------------------------------------------------
    patterns = dict(cfg.get("schemes.patterns") or {"couplet": "AABB", "alternate": "ABAB", "mono": "AAAA", "enclosed": "ABBA"})

    tagged_breaks = {i for i, pb in enumerate(bars) if pb.tags.get("break")}

    def pattern_score(p: str, lo: int = 0, hi: int | None = None) -> float:
        hi = n if hi is None else hi
        pairs = [(a, b) for a, b in _expected_pairs(p, n)
                 if lo <= a < hi and b < hi and a not in tagged_breaks and b not in tagged_breaks]
        if not pairs:
            return 0.0
        return sum(1 for a, b in pairs if bar_family[a] is not None and bar_family[a] == bar_family[b]) / len(pairs)

    expected = ctx.scheme or (bp or {}).get("scheme") or None
    if expected:
        inferred = "expected"
        consistency = pattern_score(expected)
        chosen = expected
    else:
        scored = sorted(((pattern_score(p), -len(p), name, p) for name, p in patterns.items()), reverse=True)
        best_score, _, inferred, chosen = scored[0]
        consistency = best_score
        if sum(rhymed) / n < float(cfg.analysis["scheme_min_family_share"]) and best_score < 0.5:
            inferred = "free"
    group = len(chosen.replace(" ", ""))
    pattern_changes = []
    prev_local = None
    for g0 in range(0, n, max(group, 1)):
        local = max(patterns.items(), key=lambda kv: (pattern_score(kv[1], g0, min(n, g0 + group)), -len(kv[1])))[0] if n - g0 >= 2 else prev_local
        if prev_local is not None and local != prev_local:
            pattern_changes.append({"bar": g0 + 1, "from": prev_local, "to": local, "type": "scheme"})
        prev_local = local

    # ---- flow switches -----------------------------------------------------
    bar_contents = [C.bar_content(i, bars[i].text, bar_tokens[i], lex, list(ctx.imagery_domains) + list((persona.biography_anchors if persona else [])), cfg) for i in range(n)]
    switches = detect_flow_switches(rhythm.bars, [bc.norms for bc in bar_contents], [bc.cue_hits for bc in bar_contents],
                                    [pb.tags for pb in bars], end_label, cfg)
    for sw in switches:
        pattern_changes.append({"bar": sw.bar, "from": sw.previous.cell, "to": sw.next.cell, "type": "flow", "cause": sw.cause})
    pattern_changes.sort(key=lambda x: (x["bar"], x["type"]))
    switch_bars = {sw.bar - 1 for sw in switches}

    internal_per_bar = [0] * n
    for h in internal_hits:
        internal_per_bar[h["bar"] - 1] += 1

    # ---- cadence -------------------------------------------------------------
    spb = [b.syllables_per_beat for b in rhythm.bars]
    seg_bounds = [0] + sorted(switch_bars) + [n]
    cvs = []
    for lo, hi in zip(seg_bounds, seg_bounds[1:]):
        seg = spb[lo:hi]
        if len(seg) >= 2 and statistics.mean(seg) > 0:
            cvs.append(statistics.pstdev(seg) / statistics.mean(seg))
    cadence_consistency = max(0.0, 1.0 - (sum(cvs) / len(cvs) if cvs else 0.0))
    landings = [b.landing_onset for b in rhythm.bars if b.landing_onset is not None]
    mode_landing = statistics.mode(landings) if landings else None
    landing_consistency = sum(1 for landing in landings if landing == mode_landing) / len(landings) if landings else 0.0
    cadence = {"consistency": round(cadence_consistency, 3), "landing_consistency": round(landing_consistency, 3),
               "syllables_per_beat": [round(x, 3) for x in spb], "cells": [b.cell for b in rhythm.bars],
               "segments": [[lo + 1, hi] for lo, hi in zip(seg_bounds, seg_bounds[1:]) if hi > lo],
               "note": "Consistency is measured inside each flow segment so a planned switch is not counted against it."}
    overcrowded = [b.bar + 1 for b in rhythm.bars if b.overcrowded]

    # rhyme landings on the grid
    internal_words = {(h["bar"] - 1, h["position"]) for h in internal_hits} | {(h["matched_bar"] - 1, h["matched_position"]) for h in internal_hits}
    for b in rhythm.bars:
        i = b.bar
        end_wi = len(bar_tokens[i]) - 1
        for ev in b.events:
            if ev.kind != "syllable":
                continue
            if ev.word_index == end_wi and rhymed[i] and ev.stressed:
                ev.rhyme_landing, ev.rhyme_family = True, end_label[i]
            elif (i, ev.word_index) in internal_words and ev.stressed:
                ev.rhyme_landing = True

    # ---- breath ------------------------------------------------------------
    intensities = []
    bp_delivery = {d_["bar"]: d_ for d_ in (bp or {}).get("delivery_instructions", [])}
    for i, pb in enumerate(bars):
        if "intensity" in pb.tags:
            intensities.append(float(pb.tags["intensity"]))
        elif i + 1 in bp_delivery and "intensity" in bp_delivery[i + 1]:
            intensities.append(float(bp_delivery[i + 1]["intensity"]))
        else:
            intensities.append(float(cfg.breath["default_intensity"]))
    breath = analyze_breath(rhythm, slot_infos, intensities, ctx.breath_profile, cfg)

    # ---- content -------------------------------------------------------------
    generic: list[dict] = []
    per_bar_flags: list[list[dict]] = []
    for bc in bar_contents:
        flags = C.generic_flags(bc, lex, cfg)
        for p in C.phrase_hits(bc.norms, [f.lower() for f in (list(ctx.forbidden_phrases) + list((bp or {}).get("forbidden_phrases", [])))]):
            flags.append({"rule": "forbidden_phrase", "evidence": p, "penalized": True})
        per_bar_flags.append(flags)
        for f in flags:
            generic.append({"bar": bc.index + 1, **f})
    selfdesc = C.self_description_bars(bar_contents, lex)
    max_self = int(cfg.content["self_description_max"])
    if len(selfdesc) > max_self:
        for b in selfdesc[max_self:]:
            generic.append({"bar": b + 1, "rule": "redundant_self_description", "evidence": bars[b].text, "penalized": True})
            per_bar_flags[b].append({"rule": "redundant_self_description", "penalized": True})
    templates = C.repeated_templates(bar_contents, cfg)
    for grp in templates:
        for b in grp[1:]:
            generic.append({"bar": b + 1, "rule": "repeated_template", "evidence": f"same sentence frame as bar {grp[0] + 1}", "penalized": True})
            per_bar_flags[b].append({"rule": "repeated_template", "penalized": True})
    for r in pair_records:
        pair = frozenset(w.lower() for w in r["words"])
        if pair in lex.predictable_pairs:
            generic.append({"bar": r["bars"][1], "rule": "predictable_pair", "evidence": " / ".join(r["words"]), "penalized": True})
            per_bar_flags[r["bars"][1] - 1].append({"rule": "predictable_pair", "penalized": True})
    strict_pairs = sum(1 for r in pair_records if r["kind"] in ("exact", "perfect", "identity"))
    if pair_records and strict_pairs / len(pair_records) >= float(cfg.content["perfect_end_share"]) and len(internal_hits) / n < float(cfg.content["internal_floor_per_bar"]):
        generic.append({"bar": None, "rule": "perfect_end_without_internal", "penalized": True,
                        "evidence": f"{strict_pairs} of {len(pair_records)} end rhymes are exact with {len(internal_hits)} internal rhymes"})
    semantic = C.semantic_repetition(bar_contents, cfg)
    restated = {p["bars"][1] - 1 for p in semantic}
    for p in semantic:
        generic.append({"bar": p["bars"][1], "rule": "semantic_restatement", "evidence": f"repeats {', '.join(p['shared'])} from bar {p['bars'][0]}", "penalized": True})
    facts = list(ctx.required_facts) or list((bp or {}).get("required_facts", []))
    fact_ret = C.required_fact_retention(bar_contents, facts, lex, cfg)
    persona_rep = persona_consistency([bc.norms for bc in bar_contents], persona, lex, cfg) if persona else None
    if persona_rep:
        for fl in persona_rep.bar_flags:
            for iss in fl["issues"]:
                generic.append({"bar": fl["bar"], "rule": "voice_inconsistent", "evidence": iss, "penalized": True})
    emo = C.emotional_progression(bar_contents, cfg)
    cbs = C.callbacks(bar_contents, cfg)
    links = []
    for link in (bp or {}).get("setup_payoff_links", []):
        s_bar, p_bar = link.get("setup_bar", 0) - 1, link.get("payoff_bar", 0) - 1
        if 0 <= s_bar < n and 0 <= p_bar < n:
            shared = sorted({C.light_stem(w) for w in bar_contents[s_bar].content} & {C.light_stem(w) for w in bar_contents[p_bar].content})
            links.append({**link, "satisfied": bool(shared), "shared": shared})
    integrity = (sum(1 for link in links if link["satisfied"]) / len(links)) if links else (1.0 if cbs else None)
    jobs = C.infer_bar_jobs(bar_contents, rhymed, [sw.bar for sw in switches], cfg)
    planned_jobs = {o["bar"]: o["job"] for o in (bp or {}).get("bar_objectives", [])}
    syntax = {"template_groups": [[b + 1 for b in g] for g in templates],
              "variety": round(len({bc.template_key for bc in bar_contents}) / n, 3)}

    # ---- weak bars -----------------------------------------------------------
    ww = cfg.analysis["weak_bar_weights"]
    sat = float(cfg.scorer["genericness_saturation_per_bar"])
    gw = cfg.scorer["genericness_weights"]
    min_words = int(cfg.content["min_content_words_without_end"])
    drift = set(persona_rep.drift_bars) if persona_rep else set()
    weak, bar_details, recs, weakness, protected = [], [], [], [], []
    for i, bc in enumerate(bar_contents):
        pen = [f for f in per_bar_flags[i] if f.get("penalized")]
        gscore = min(1.0, sum(gw.get(f["rule"], 1.0) for f in pen) / sat) if pen else 0.0
        reasons, score = [], 0.0
        if gscore > 0:
            score += ww["generic"] * gscore
            reasons.append("generic language: " + ", ".join(sorted({f["rule"] for f in pen})))
        if not bc.anchors() and not bc.sensory:
            score += ww["no_anchor"]
            reasons.append("no concrete or sensory anchor")
        if any(f["rule"] == "forced_syntax" for f in pen):
            score += ww["forced_syntax"]
            reasons.append("word order bent to reach the rhyme")
        non_end = [w for w in bc.content if w != (bc.norms[-1] if bc.norms else None)]
        if rhymed[i] and len(non_end) < min_words:
            score += ww["rhyme_only"]
            reasons.append("the rhyme may be the main reason this line exists")
        if i in restated:
            score += ww["restatement"]
            reasons.append("restates an earlier bar without escalating")
        if (i + 1) in drift:
            score += ww["persona_drift"]
            reasons.append("drifts from the persona contract")
        if (i + 1) in overcrowded:
            score += ww["overcrowded"]
            reasons.append("more syllables than the bar comfortably holds")
        if jobs[i]["job"] == "unclear":
            score += ww["no_clear_job"]
            reasons.append("no clear bar job")
        score = min(1.0, score)
        weakness.append(score)
        is_weak = score >= float(cfg.analysis["weak_bar_threshold"])
        density_evidence = _semantic_density_evidence(bars[i].tags, bars[i].text) if is_weak else []
        if is_weak and density_evidence:
            # The word lists see a thin line; the evidence says it may be layered. Flag it, do not advise repairing it.
            protected.append({"bar": i + 1, "score": round(score, 3), "label": SEMANTIC_DENSITY_LABEL, "evidence": density_evidence,
                              "surface_reasons": reasons, "text": bars[i].text})
        elif is_weak:
            weak.append({"bar": i + 1, "score": round(score, 3), "reasons": reasons, "job": jobs[i]["job"], "text": bars[i].text})
            recs.append({"bar": i + 1, "recommendations": _recommend(reasons, bc, planned_jobs.get(i + 1) or jobs[i]["job"])})
        bar_details.append({
            "bar": i + 1, "text": bars[i].text, "tags": bars[i].tags, "tokens": len(bar_tokens[i]),
            "syllables": len(bar_sylls[i]), "stress": "".join("1" if s.stressed else "0" for s in bar_sylls[i]),
            "end_word": end_prons[i].word if end_prons[i] else None, "end_family": end_label[i], "rhymed": rhymed[i],
            "internal_hits": internal_per_bar[i], "cell": rhythm.bars[i].cell,
            "syllables_per_beat": round(rhythm.bars[i].syllables_per_beat, 3),
            "job": jobs[i], "planned_job": planned_jobs.get(i + 1), "content": bc.to_dict(),
            "content_beyond_end": len(non_end), "generic_flags": per_bar_flags[i], "weakness": round(score, 3),
        })

    # ---- scheme breaks (after weak bars: bar weakness is part of the evidence) ----
    group_len = max(1, len(chosen.replace(" ", "")))
    raw_pairs = _expected_pairs(chosen, n)
    all_pairs = [(a, b) for a, b in raw_pairs if a not in tagged_breaks and b not in tagged_breaks]
    bconf = cfg.analysis["break_confidence"]
    first_pairs = [(a, b) for a, b in all_pairs if b < group_len]
    first_ok = bool(first_pairs) and all(bar_family[a] is not None and bar_family[a] == bar_family[b] for a, b in first_pairs)
    established = expected is not None or first_ok or consistency >= float(cfg.analysis["scheme_established_min"])
    scheme_state = "established" if established else ("loose" if any(rhymed) else "free")
    broken_pairs = [(a, b) for a, b in all_pairs if not (bar_family[a] is not None and bar_family[a] == bar_family[b])] if established else []
    runs: list[list[tuple[int, int]]] = []
    for pair in broken_pairs:
        if runs and pair[0] - runs[-1][-1][1] <= 1 and pair[0] > runs[-1][-1][0]:
            runs[-1].append(pair)
        else:
            runs.append([pair])
    collapse_min = int(cfg.analysis["collapse_min_run"])
    comp_hits = int(cfg.analysis["break_compensation_internal_hits"])
    weak_thr = float(cfg.analysis["weak_bar_threshold"])
    voice_bars: set[int] = set()
    if persona_rep:
        for hit_bars in persona_rep.domain_hits.values():
            voice_bars |= {int(x) for x in hit_bars}
    scheme_breaks, collapses = [], []
    x_bars = {i for i, lab in enumerate(_expand_scheme(chosen, n)) if lab is None}
    for run in runs:
        is_run = len(run) >= collapse_min
        run_bars = sorted({b for pair in run for b in pair})
        results = []
        for b in run_bars:
            if b in x_bars:
                continue
            intent, accident = [], []
            tagged = bool(bars[b].tags.get("break"))
            if tagged:
                intent.append("tagged [break]")
            partners = {q for pair in run for q in pair if b in pair and q != b}
            if any(bars[q].tags.get("break") for q in partners):
                intent.append("its expected partner is a tagged break")
            if b in switch_bars or (b + 1) in switch_bars:
                intent.append("flow switch at or right after this bar")
            if b == n - 1:
                intent.append("final bar")
            bc = bar_contents[b]
            if bc.cue_hits.get("reveal") or bc.cue_hits.get("contrast"):
                intent.append("reveal or contrast cue")
            if internal_per_bar[b] >= comp_hits:
                intent.append("internal rhyme compensates")
            if (b + 1) in voice_bars and (b + 1) not in drift:
                intent.append("the persona's voice holds in this bar")
            if is_run:
                accident.append(f"part of a run of {len(run)} missing expected rhymes")
            if bar_details[b]["end_word"] in lex.stopwords:
                accident.append("line ends on a function word")
            if weakness[b] >= weak_thr:
                accident.append("the bar is weak on its own")
            if not intent:
                accident.append("no cue explains the missing rhyme")
            likely_intent = tagged or len(intent) > len(accident)
            cls = "likely_intentional" if likely_intent else "likely_accidental"
            conf = bconf["tagged"] if tagged else min(bconf["max"], bconf["base"] + bconf["per_evidence"] * abs(len(intent) - len(accident)))
            rec = {"bar": b + 1, "expected_partner_bars": sorted({q + 1 for pair in run for q in pair if b in pair and q != b}),
                   "classification": cls, "confidence": round(conf, 3), "evidence": intent if likely_intent else accident,
                   "counter_evidence": accident if likely_intent else intent}
            results.append(rec)
            scheme_breaks.append(rec)
        accidental_share = sum(1 for r in results if r["classification"] == "likely_accidental") / len(results) if results else 0.0
        if is_run and accidental_share > 0.5:
            collapses.append({"bars": [r["bar"] for r in results], "pairs": [[a + 1, b + 1] for a, b in run],
                              "accidental_share": round(accidental_share, 3),
                              "note": "an established scheme drops for several expected rhymes in a row without a cue"})
    for a_, b_ in raw_pairs:
        if (a_ in tagged_breaks or b_ in tagged_breaks) and not (bar_family[a_] is not None and bar_family[a_] == bar_family[b_]):
            for q, partner in ((a_, b_), (b_, a_)):
                if any(sb["bar"] == q + 1 for sb in scheme_breaks):
                    continue
                own = q in tagged_breaks
                scheme_breaks.append({"bar": q + 1, "expected_partner_bars": [partner + 1], "classification": "likely_intentional",
                                      "confidence": bconf["tagged"] if own else bconf["partner_of_tagged"],
                                      "evidence": ["tagged [break]"] if own else ["its expected partner is a tagged break"],
                                      "counter_evidence": []})
    for q in sorted(tagged_breaks):
        if not rhymed[q] and not any(sb["bar"] == q + 1 for sb in scheme_breaks):
            scheme_breaks.append({"bar": q + 1, "expected_partner_bars": [], "classification": "likely_intentional",
                                  "confidence": bconf["tagged"], "evidence": ["tagged [break]"], "counter_evidence": []})
    for b in sorted(x_bars):
        if not any(sb["bar"] == b + 1 for sb in scheme_breaks):
            scheme_breaks.append({"bar": b + 1, "expected_partner_bars": [], "classification": "planned_break", "confidence": bconf["planned"],
                                  "evidence": ["scheme marks this bar X"], "counter_evidence": []})
    scheme_breaks.sort(key=lambda x: x["bar"])

    # ---- confidence ---------------------------------------------------------------
    all_prons = [p for ps in bar_prons for p in ps]
    confs = [p.confidence for p in all_prons]
    heur = [p for p in all_prons if p.source == "heuristic"]
    low = sorted({p.word for p in all_prons if p.confidence < 0.6})
    limitations = list(BASE_LIMITATIONS)
    if d.backend_name == "none":
        limitations.insert(0, "No pronunciation dictionary is installed, so most pronunciations are spelling-based guesses (install the optional 'cmu' extra for better coverage).")
    if not persona:
        limitations.append("No persona was supplied, so voice consistency was not checked.")
    analysis = VerseAnalysis(
        counts={"lines": len([line for line in (text or '').splitlines() if line.strip()]), "bars": n, "tokens": sum(len(t) for t in bar_tokens)},
        syllables={"total": total_sylls, "per_bar": [len(s) for s in bar_sylls]},
        stress_patterns=[bd["stress"] for bd in bar_details],
        end_rhyme_families=end_families_out,
        internal_rhyme_families=internal_families,
        multisyllabic_chains=chains,
        compound_and_slant_candidates=candidates,
        rhyme_density=round(density, 4),
        rhyme_span=rhyme_span,
        scheme={"letters": letters, "inferred_pattern": inferred, "pattern": chosen, "consistency": round(consistency, 3),
                "expected": expected, "state": scheme_state},
        pattern_changes=pattern_changes,
        scheme_breaks=scheme_breaks,
        pattern_collapses=collapses,
        cadence=cadence,
        overcrowded_bars=overcrowded,
        breath=breath.to_dict(),
        lexical_repetition=C.lexical_repetition(bar_contents),
        semantic_repetition=semantic,
        generic_flags=generic,
        concrete_noun_density=round(sum(len(bc.concrete) for bc in bar_contents) / n, 4),
        sensory_detail_density=round(sum(len(bc.sensory) for bc in bar_contents) / n, 4),
        named_fact_retention=fact_ret,
        persona_consistency=persona_rep.to_dict() if persona_rep else None,
        emotional_progression=emo,
        setup_payoff={"links": links, "callbacks": cbs, "integrity": None if integrity is None else round(integrity, 3),
                      "progression_rate": round(C.progression_rate(bar_contents), 3)},
        weak_bars=weak,
        protected_bars=protected,
        repair_recommendations=recs,
        confidence={"pronunciation_mean": round(sum(confs) / len(confs), 3) if confs else 0.0,
                    "heuristic_share": round(len(heur) / len(all_prons), 3) if all_prons else 0.0,
                    "dictionary_backend": d.backend_name, "dialect": d.dialect, "low_confidence_words": low[:40],
                    "cadence": "estimate", "scores": "heuristic"},
        limitations=limitations,
        flow_switches=[sw.to_dict() for sw in switches],
        rhyme_stats={"rhymed_pairs": len(pair_records), "identity_pairs": sum(1 for r in pair_records if r["kind"] == "identity"),
                     "strict_pairs": strict_pairs, "slant_pairs": sum(1 for r in pair_records if r["kind"] == "slant"),
                     "multi_pairs": sum(1 for r in pair_records if r["multi_syllables"] >= 2),
                     "internal_hits": len(internal_hits), "families_spanning_3plus": sum(1 for f in families if len(f["members"]) >= 3),
                     "internal_hit_list": internal_hits},
        syntax=syntax,
        bars=bar_details,
        grid=rhythm.to_dict() if ctx.include_grid else None,
    )
    analysis.rhythm = rhythm  # live RhythmGrid for the ASCII view; not part of the JSON output
    return analysis


def _recommend(reasons: list[str], bc: C.BarContent, job: str) -> list[str]:
    out = []
    for r in reasons:
        if r.startswith("generic language"):
            out.append("Swap the stock phrase for something only this speaker saw, touched or owns.")
        elif r.startswith("no concrete"):
            out.append("Add one physical object, place, number or name the listener can picture.")
        elif r.startswith("word order"):
            out.append("Say the line in natural word order first, then look for a different end word that fits it.")
        elif r.startswith("the rhyme may"):
            out.append("Give the line a job beyond the rhyme: new information, a turn, or a consequence.")
        elif r.startswith("restates"):
            out.append("Escalate instead of repeating: raise the stakes or change the image.")
        elif r.startswith("drifts"):
            out.append("Pull the vocabulary back inside the persona's range and metaphor domains.")
        elif r.startswith("more syllables"):
            out.append("Cut syllables or move part of the thought into the next bar.")
        elif r.startswith("no clear bar job"):
            out.append(f"Decide what this bar does ({C.JOB_DESCRIPTIONS.get(job, 'pick a job')}) and rewrite toward it.")
    return out
