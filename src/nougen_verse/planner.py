"""PLAN mode: turn a VerseRequest into a VerseBlueprint.

The planner does not write lyrics. It produces constraints: a content spine
with open questions, a job for every bar, rhyme family assignments, beat-grid
targets, breath groups, delivery notes, flow switches with causes and
deliberate scheme breaks. Randomness only comes from ``request.seed``, so the
same request always yields the same blueprint.
"""

from __future__ import annotations

import hashlib
import json
import random
from fractions import Fraction

from . import content as C
from .analyzer import _expand_scheme
from .breath import DeliveryAnnotation, breath_profile
from .config import Config, load_data_json, load_data_lines, resolve_config
from .flow import FLOW_SWITCH_CAUSES, FlowGrammar, FlowSwitch, breath_consequence, delivery_for, normalize_cause
from .models import VerseBlueprint, VerseRequest
from .persona import load_persona
from .phonetics import get_dictionary, tokenize
from .rhyme import family_label, find_rhymes
from .rhythm import CELL_LIBRARY, BeatGrid, frac_str

DEFAULT_SWITCH_CAUSES = ("reveal", "emotional_escalation", "time_jump", "new_addressee", "perspective_shift")

PROVENANCE = {
    "content_spine": "content layer: answer the story questions before choosing rhymes (content, flow and delivery kept as separate layers, following the high-level craft structure publicly described in Paul Edwards, How to Rap: The Art and Science of the Hip-Hop MC)",
    "bar_objectives": "content.assign_bar_jobs: deterministic job arc seeded by request.seed; every bar has a job beyond the rhyme",
    "setup_payoff_links": "planner: callbacks and spine setup/payoff mapped to early and late bars",
    "rhyme_family_assignments": "planner: scheme pattern expansion; first family anchored on the stressed vowel of the central image word",
    "stressed_syllable_targets": "rhythm: beat-grid stress targets on the beats of each bar",
    "internal_rhyme_placements": "planner: seeded placements scaled by request.internal_rhyme",
    "end_rhyme_placements": "rhythm: end rhyme landing on the configured landing beat",
    "cadence_cells": "rhythm.CELL_LIBRARY: base cell by tempo (planner.cadence_by_bpm), contrast cell after each flow switch",
    "rest_positions": "breath: a rest at the end of each breath group",
    "breath_groups": "breath: bars grouped under the performer profile limits",
    "delivery_instructions": "breath.DeliveryAnnotation: intensity follows the emotion curve; punch bars get space before the last word",
    "emotion_curve": "planner: linear ramp between the emotional axis ends with a dip before the reveal",
    "flow_switches": "flow.FlowSwitch: each switch carries a narrative cause (advanced flow concepts such as switching flows and breaking patterns are described publicly for Paul Edwards, How to Rap 2: Advanced Flow and Delivery Techniques)",
    "scheme_breaks": "planner: X letters in the scheme mark deliberate breaks",
    "callbacks": "planner: request.callbacks placed late with an early setup bar",
    "specificity_anchors": "planner: required facts, spine objects and persona biography anchors assigned to bars",
    "revision_priorities": "planner: fixed priority list, content first",
}


def _intensity_for(label: str, fallback: float) -> float:
    emo = load_data_json("lexicons.json")["emotion_lexicon"]
    best = None
    for t in tokenize(label or ""):
        if t.norm in emo:
            best = max(best or 0.0, float(emo[t.norm][1]))
    return best if best is not None else fallback


def _switch_specs(req: VerseRequest, rng: random.Random, n: int) -> list[dict]:
    specs = []
    if isinstance(req.flow_switches, int):
        count = max(0, req.flow_switches)
        causes = list(DEFAULT_SWITCH_CAUSES)
        rng.shuffle(causes)
        for k in range(count):
            bar = max(2, min(n, round(n * (k + 1) / (count + 1)) + 1))
            specs.append({"bar": bar, "cause": causes[k % len(causes)], "trigger": ""})
    else:
        for s in req.flow_switches or []:
            bar = int(s["bar"])
            if not 2 <= bar <= n:
                raise ValueError(f"flow switch bar {bar} must be between 2 and {n}")
            specs.append({"bar": bar, "cause": normalize_cause(s.get("cause", "reveal")), "trigger": s.get("trigger", "")})
    seen = set()
    out = []
    for s in sorted(specs, key=lambda x: x["bar"]):
        if s["bar"] not in seen:
            seen.add(s["bar"])
            out.append(s)
    return out


def plan_verse(request: VerseRequest | dict, config: Config | dict | None = None) -> VerseBlueprint:
    cfg = resolve_config(config)
    req = request if isinstance(request, VerseRequest) else VerseRequest.from_dict(request, cfg)
    issues = req.validate()
    if issues:
        raise ValueError("invalid request: " + "; ".join(issues))
    rng = random.Random(req.seed)
    pl = cfg.planner
    n = int(req.bar_count)
    persona = load_persona(req.persona if req.persona else req.persona_id, cfg) if (req.persona or req.persona_id) else None
    grid = BeatGrid.from_time_signature(req.bpm, req.time_signature, req.subdivisions_per_beat, cfg.rhythm["swing"])
    beats = grid.beats_per_bar
    lex = C.Lexicons(cfg)
    d = get_dictionary(cfg)

    # content spine
    spine = C.ContentSpine.from_dict(req.content_spine)
    for phrase in list(req.forbidden_phrases) + (persona.forbidden_cliches if persona else []):
        if phrase not in spine.must_not_say_generically:
            spine.must_not_say_generically.append(phrase)
    open_questions = [C.SPINE_QUESTIONS[k] for k in spine.missing()]

    # flow switches and jobs
    switch_specs = _switch_specs(req, rng, n)
    switch_bars = [s["bar"] for s in switch_specs]
    callback_bars = [max(2, n - 1 - k) for k in range(len(req.callbacks))] if n >= 3 else []
    punch_bars = [int(p) for p in req.punchline_targets if isinstance(p, int) or str(p).isdigit()]
    jobs = C.assign_bar_jobs(n, req.seed, switch_bars, callback_bars, punch_bars, cfg)

    # scheme and families
    pattern = req.scheme.replace(" ", "").upper()
    labels = _expand_scheme(pattern, n)
    fam_of: dict[str, str] = {}
    bar_fam: list[str | None] = []
    for lab in labels:
        if lab is None:
            bar_fam.append(None)
            continue
        if lab not in fam_of:
            fam_of[lab] = family_label(len(fam_of))
        bar_fam.append(fam_of[lab])
    pool = list(pl["family_vowel_pool"])
    rng.shuffle(pool)
    anchor_text = spine.central_image or req.central_claim or req.topic
    anchor_word = None
    for t in reversed(tokenize(anchor_text)):
        if t.norm not in lex.stopwords:
            anchor_word = t.norm
            break
    families = []
    prev_vowel = None
    vocab = load_data_lines("vocab.txt")
    for k, fam in enumerate(dict.fromkeys(f for f in bar_fam if f)):
        bars_in = [i + 1 for i, f in enumerate(bar_fam) if f == fam]
        if k == 0 and anchor_word:
            pr = d.pronounce(anchor_word)
            tail = pr.tail_syllables()
            vowel = tail[0].nucleus if tail else pool[0]
            word = anchor_word
            options = [c.word for c in find_rhymes(anchor_word, {"slant": True, "max_results": 8}, d, cfg)]
        else:
            choices = [v for v in pool if v != prev_vowel] or pool
            vowel = choices[k % len(choices)]
            word = None
            matches = sorted(w for w in vocab if (lambda t: t and t[0].nucleus == vowel)(d.pronounce(w).tail_syllables()))
            options = rng.sample(matches, min(8, len(matches))) if matches else []
            options.sort()
        prev_vowel = vowel
        families.append({"label": fam, "bars": bars_in, "anchor_vowel": vowel, "anchor_word": word, "suggested_endings": options,
                         "note": "suggestions are starting points; the line's meaning decides the final word"})

    # cadence cells
    base = next(cell for limit, cell in pl["cadence_by_bpm"] if req.bpm <= limit)
    cells, current = [], base
    for i in range(n):
        if (i + 1) in switch_bars:
            current = pl["switch_contrast_cells"].get(current, current)
        cells.append(current)
    landing = Fraction(int(cfg.rhythm["end_landing_beat"]) - 1)
    cadence_cells = [{"bar": i + 1, "cell": c, "tuplet": CELL_LIBRARY[c]["tuplet"], "step": frac_str(CELL_LIBRARY[c]["step"])} for i, c in enumerate(cells)]
    stressed_targets = [{"bar": i + 1, "onsets": [str(b) for b in range(beats)], "count": beats} for i in range(n)]
    end_placements, internal_placements = [], []
    for i in range(n):
        if bar_fam[i]:
            depth = int(pl["multi_depth_syllables"]) if rng.random() < req.multisyllabic else 1
            end_placements.append({"bar": i + 1, "onset": frac_str(landing), "family": bar_fam[i], "syllables": depth})
            if rng.random() < req.internal_rhyme:
                onset = Fraction(rng.choice(list(pl["internal_onset_choices"])))
                internal_placements.append({"bar": i + 1, "onset": frac_str(onset), "family": bar_fam[i]})

    # breath
    prof_name, prof = breath_profile(req.breath_budget if isinstance(req.breath_budget, (str, dict)) else None, cfg)
    max_group = int(pl["max_bars_per_breath_group"])
    groups, cur = [], []
    for i in range(n):
        if cur and (len(cur) >= max_group or (i + 1) in switch_bars):
            groups.append(cur)
            cur = []
        cur.append(i + 1)
    if cur:
        groups.append(cur)
    breath_groups = [{"bars": g, "profile": prof_name, "max_phrase_seconds": prof["max_phrase_seconds"],
                      "note": "leave a usable rest at the end of this group"} for g in groups]
    rest_len = Fraction(str(pl["breath_rest_beats"]))
    punch_space = Fraction(str(pl["punch_space_beats"]))
    rest_positions = [{"bar": g[-1], "onset": frac_str(Fraction(beats) - rest_len), "duration": frac_str(rest_len), "reason": "breath"} for g in groups]
    for i, job in enumerate(jobs):
        if job == "punch" and i > 0:
            rest_positions.append({"bar": i + 1, "onset": frac_str(landing - 2 * punch_space), "duration": frac_str(punch_space), "reason": "space before the punch word"})
    rest_positions.sort(key=lambda r: (r["bar"], Fraction(r["onset"])))

    # emotion and delivery
    axis = req.emotional_axis or {}
    start = _intensity_for(axis.get("from", ""), float(pl["emotion_start_default"]))
    end = _intensity_for(axis.get("to", ""), float(pl["emotion_end_default"]))
    reveal_bars = {i for i, j in enumerate(jobs) if j == "reveal"} | {b - 1 for b in switch_bars}
    curve = []
    for i in range(n):
        v = start + (end - start) * (i / max(1, n - 1))
        if (i + 1) in reveal_bars:
            v -= float(pl["emotion_curve_dip_before_reveal"])
        curve.append(round(max(0.0, min(1.0, v)), 3))
    delivery = []
    for i in range(n):
        inten = curve[i]
        ann = DeliveryAnnotation(bar=i + 1, intensity=inten,
                                 volume="low" if inten < pl["volume_low_below"] else ("high" if inten > pl["volume_high_above"] else "medium"),
                                 pitch_direction="rising" if i + 1 < n and curve[i + 1] > inten else ("falling" if jobs[i] == "resolve_or_fracture" else "level"),
                                 articulation="clipped" if jobs[i] == "punch" else "clear")
        if jobs[i] == "punch":
            ann.silence = ["a half beat before the last word"]
            ann.adlib_slots = ["after the bar line"]
        if jobs[i] == "reveal":
            ann.timbre = "drop the volume a step and let the words carry"
        if i == n - 1 and persona and persona.audience_relationship:
            ann.audience_interaction = persona.audience_relationship
        delivery.append(ann.to_dict())

    # flow switch objects
    flow_switches = []
    for s in switch_specs:
        i = s["bar"] - 1
        prev_c, next_c = cells[i - 1], cells[i]
        prev_g = FlowGrammar(prev_c, CELL_LIBRARY[prev_c]["family"], float(1 / CELL_LIBRARY[prev_c]["step"]), frac_str(landing))
        next_g = FlowGrammar(next_c, CELL_LIBRARY[next_c]["family"], float(1 / CELL_LIBRARY[next_c]["step"]), frac_str(landing))
        fs = FlowSwitch(bar=s["bar"], previous=prev_g, next=next_g, cause=s["cause"],
                        semantic_trigger=s["trigger"] or f"bar {s['bar']} carries the {s['cause'].replace('_', ' ')}",
                        breath_consequence=breath_consequence(prev_g, next_g),
                        rhyme_consequence=f"end family {bar_fam[i - 1]} to {bar_fam[i]}" if bar_fam[i - 1] != bar_fam[i] else f"family {bar_fam[i]} carries across",
                        delivery_instruction=delivery_for(prev_g, next_g, s["cause"]), source="planned")
        flow_switches.append(fs.to_dict())

    # callbacks, anchors, links
    callbacks = []
    for k, phrase in enumerate(req.callbacks):
        cb_bar = callback_bars[k] if k < len(callback_bars) else n
        callbacks.append({"phrase": phrase, "source_bar": min(n, 2 + k), "bar": cb_bar})
    links = [{"setup_bar": c["source_bar"], "payoff_bar": c["bar"], "note": f"introduce {c['phrase']!r} early, return to it with new meaning"} for c in callbacks]
    if spine.setup and spine.payoff:
        payoff_bar = max((i + 1 for i, j in enumerate(jobs) if j in ("punch", "resolve_or_fracture")), default=n)
        links.append({"setup_bar": 2 if n > 1 else 1, "payoff_bar": payoff_bar, "note": f"setup: {spine.setup} / payoff: {spine.payoff}"})
    anchor_sources = [(f, "required_fact") for f in req.required_facts] + [(o, "spine_object") for o in spine.concrete_objects]
    if spine.speaker_only_fact:
        anchor_sources.append((spine.speaker_only_fact, "speaker_only_fact"))
    if persona:
        anchor_sources += [(a, "persona_biography") for a in persona.biography_anchors]
    slots = [i + 1 for i, j in enumerate(jobs) if j in ("specify", "establish", "reveal", "callback", "escalate")] or list(range(1, n + 1))
    anchors = [{"anchor": a, "bar": slots[k % len(slots)], "source": src} for k, (a, src) in enumerate(anchor_sources)]
    by_bar: dict[int, list[str]] = {}
    for a in anchors:
        by_bar.setdefault(a["bar"], []).append(a["anchor"])
    objectives = []
    for i, job in enumerate(jobs):
        obj = C.JOB_DESCRIPTIONS[job]
        if by_bar.get(i + 1):
            obj += "; use: " + ", ".join(by_bar[i + 1])
        objectives.append({"bar": i + 1, "job": job, "objective": obj, "anchors": by_bar.get(i + 1, []),
                           "end_family": bar_fam[i], "cell": cells[i]})
    scheme_breaks = [{"bar": i + 1, "reason": "planned break (X in scheme)"} for i, f in enumerate(bar_fam) if f is None]
    digest = hashlib.sha256(json.dumps(req.to_dict(), sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return VerseBlueprint(
        request_digest=digest, seed=req.seed, grid={**grid.to_dict(), "time_signature": req.time_signature},
        persona=persona.to_dict() if persona else None, content_spine=spine.to_dict(), bar_objectives=objectives,
        setup_payoff_links=links, rhyme_family_assignments=families, stressed_syllable_targets=stressed_targets,
        internal_rhyme_placements=internal_placements, end_rhyme_placements=end_placements, cadence_cells=cadence_cells,
        rest_positions=rest_positions, breath_groups=breath_groups, delivery_instructions=delivery, emotion_curve=curve,
        flow_switches=flow_switches, scheme_breaks=scheme_breaks, callbacks=callbacks, specificity_anchors=anchors,
        revision_priorities=[
            "answer the content spine before choosing rhymes",
            "every bar does its planned job; a bar that only rhymes has failed",
            "required facts and anchors are present and specific",
            "nothing from the forbidden or generic phrase lists",
            "end rhymes land on the planned families; internal rhymes where planned",
            "cadence fits the planned cells and each breath group has a rest",
            "the persona's voice survives every revision",
        ],
        provenance=PROVENANCE, required_facts=list(req.required_facts), forbidden_phrases=list(spine.must_not_say_generically),
        open_questions=open_questions, scheme=req.scheme,
        notes=["This blueprint is a plan of constraints. It does not contain or generate lyrics.",
               "Grid targets are for a text-level plan; real delivery will move against the beat."],
    )
