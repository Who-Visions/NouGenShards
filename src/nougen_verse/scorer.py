"""Score an analysis along separate craft dimensions.

Each dimension is a weighted mean of named components between 0 and 1, and
every component is reported with its value, weight and evidence. There is no
single ranking by default: a verse can be strong on specificity and loose on
scheme at the same time, and the report should show that. Weights live in the
``scorer`` config section and can be overridden per call.

These are heuristics for revision. They do not measure artistic quality.
"""

from __future__ import annotations

import copy
from typing import Any

from .config import Config, deep_merge, resolve_config
from .models import ScoreReport, VerseAnalysis

SCORE_NOTE = (
    "Scores are transparent heuristics meant to point at revision targets. They are not an objective measure of "
    "artistic quality, and a low score on one dimension can be a deliberate choice."
)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _comp(value: float | None, evidence: str) -> dict:
    return {"value": None if value is None else round(_clamp(value), 4), "evidence": evidence}


def score_verse(analysis: VerseAnalysis | dict, weights: dict | None = None, config: Config | dict | None = None) -> ScoreReport:
    cfg = resolve_config(config)
    s = cfg.scorer
    w_all = deep_merge(copy.deepcopy(s["weights"]), weights or {})
    a: dict[str, Any] = analysis.to_dict() if isinstance(analysis, VerseAnalysis) else dict(analysis)
    n = a["counts"]["bars"]
    if n == 0:
        dims = {k: {"score": None, "components": {}, "note": "insufficient input"} for k in w_all}
        return ScoreReport(dims, {"score": None, "components": {}}, [], None, ["Empty input: nothing to score.", SCORE_NOTE], w_all)
    stats = a.get("rhyme_stats", {})
    rhymed_pairs = max(1, stats.get("rhymed_pairs", 0))
    comps: dict[str, dict[str, dict]] = {}

    comps["rhyme_craft"] = {
        "rhyme_density": _comp(a["rhyme_density"] / s["rhyme_density_target"], f"rhyme density {a['rhyme_density']:.2f} of syllables"),
        "multisyllabic": _comp((stats.get("multi_pairs", 0) / rhymed_pairs) / s["multi_target_share"] if stats.get("rhymed_pairs") else 0.0,
                               f"{stats.get('multi_pairs', 0)} of {stats.get('rhymed_pairs', 0)} end rhymes span 2+ syllables"),
        "internal": _comp((stats.get("internal_hits", 0) / n) / s["internal_target_per_bar"], f"{stats.get('internal_hits', 0)} internal rhymes over {n} bars"),
        "span": _comp(a["rhyme_span"]["mean"] / s["span_target_syllables"], f"mean rhyme span {a['rhyme_span']['mean']} syllables"),
        "identity_restraint": _comp(1.0 - max(0.0, (stats.get("identity_pairs", 0) / rhymed_pairs) - cfg.rhyme["identity_overuse_ratio"]) / max(1e-9, cfg.rhyme["identity_overuse_ratio"]),
                                    f"{stats.get('identity_pairs', 0)} identity rhymes"),
    }
    switches = a.get("flow_switches", [])
    explained = [sw for sw in switches if sw["cause"] != "unexplained"]
    comps["rhythm_control"] = {
        "cadence_consistency": _comp(a["cadence"]["consistency"], "syllable density steadiness inside each flow segment (estimate)"),
        "no_overcrowding": _comp(1.0 - len(a["overcrowded_bars"]) / n, f"overcrowded bars: {a['overcrowded_bars'] or 'none'}"),
        "purposeful_switches": _comp(len(explained) / len(switches) if switches else s["no_switch_neutral"],
                                     f"{len(explained)} of {len(switches)} flow switches have a narrative cause" if switches else "no flow switch; neutral value"),
    }
    br = a["breath"]
    groups_expected = max(1.0, n / cfg.planner["max_bars_per_breath_group"])
    comps["breath_feasibility"] = {
        "pressure_headroom": _comp(1.0 - br["max_pressure"], f"highest estimated breath pressure {br['max_pressure']:.2f}"),
        "breath_opportunities": _comp(br["breath_opportunities"] / groups_expected, f"{br['breath_opportunities']} usable rests"),
    }
    bars = a.get("bars", [])
    named = sum(1 for b in bars if b["content"]["numbers"] or b["content"]["proper"])
    anchored = sum(1 for b in bars if b["content"]["concrete"] or b["content"]["numbers"] or b["content"]["proper"])
    facts = a["named_fact_retention"]
    persona = a.get("persona_consistency")
    anchored_share = (anchored / n) / s["anchored_bar_target_share"]
    if persona:
        share = float(s["persona_anchor_share"])
        persona_part = _clamp(len(persona["anchors_found"]) / max(1, int(s["persona_anchor_target"])))
        speaker_value = share * persona_part + (1 - share) * _clamp(anchored_share)
    else:
        speaker_value = anchored_share
    comps["specificity"] = {
        "concrete_nouns": _comp(a["concrete_noun_density"] / s["concrete_target_per_bar"], f"{a['concrete_noun_density']:.2f} concrete nouns per bar"),
        "sensory_detail": _comp(a["sensory_detail_density"] / s["sensory_target_per_bar"], f"{a['sensory_detail_density']:.2f} sensory words per bar"),
        "named_facts": _comp(facts["retention"] if facts.get("retention") is not None else (named / n) / s["named_anchor_target_share"],
                             f"{facts['retained']} of {facts['total']} required facts kept" if facts.get("total") else f"{named} bars with a number or name"),
        "speaker_facts": _comp(speaker_value, f"{anchored} of {n} bars carry an anchor" + (f"; persona anchors found: {persona['anchors_found']}" if persona else "")),
    }
    accidental = sum(1 for b in a["scheme_breaks"] if b["classification"] == "likely_accidental")
    sp = a["setup_payoff"]
    comps["structure"] = {
        "scheme_consistency": _comp(a["scheme"]["consistency"], f"scheme {a['scheme']['letters']} vs {a['scheme']['pattern']}"),
        "break_control": _comp(1.0 - (accidental / n) / s["accidental_break_tolerance_share"], f"{accidental} likely accidental scheme breaks"),
        "setup_payoff": _comp(sp["integrity"] if sp.get("integrity") is not None else 0.0, f"{len(sp['callbacks'])} callbacks, {len(sp['links'])} planned links"),
    }
    emo = a["emotional_progression"]
    min_words = int(cfg.content["min_content_words_without_end"])
    meaning = sum(1 for b in bars if b.get("content_beyond_end", 0) >= min_words)
    comps["narrative"] = {
        "progression": _comp(sp.get("progression_rate", 0.0) / s["progression_target"], f"new information per bar {sp.get('progression_rate', 0.0):.2f}"),
        "emotional_movement": _comp(emo["range"] / s["emotion_movement_target"], f"emotion range {emo['range']} ({emo['direction']})"),
        "callbacks": _comp(len(sp["callbacks"]) / s["callbacks_target"], f"{len(sp['callbacks'])} callbacks"),
        "meaning_without_rhyme": _comp(meaning / n, f"{meaning} of {n} bars carry content beyond the end word"),
    }
    # genericness
    gw = s["genericness_weights"]
    counts: dict[str, int] = {}
    for f in a["generic_flags"]:
        if f.get("penalized"):
            counts[f["rule"]] = counts.get(f["rule"], 0) + 1
    raw = sum(gw.get(rule, 1.0) * c for rule, c in counts.items())
    gscore = _clamp(raw / (n * s["genericness_saturation_per_bar"]))
    genericness = {"score": round(gscore, 4), "components": {rule: {"count": c, "weight": gw.get(rule, 1.0)} for rule, c in sorted(counts.items())},
                   "note": "Higher means more generic. Cliche words with concrete support in the same bar are noted but not penalized."}
    comps["originality"] = {
        "low_genericness": _comp(1.0 - gscore, f"genericness {gscore:.2f}"),
        "varied_syntax": _comp(a.get("syntax", {}).get("variety", 0.0), f"sentence frame variety {a.get('syntax', {}).get('variety', 0.0)}"),
    }
    comps["persona_fit"] = {"consistency": _comp(persona["consistency"] if persona else None, "persona contract checks" if persona else "no persona supplied")}

    dims = {}
    for dim, cs in comps.items():
        weights_d = w_all.get(dim, {})
        num = den = 0.0
        for name, c in cs.items():
            wt = float(weights_d.get(name, 0.0))
            c["weight"] = wt
            if c["value"] is None:
                continue
            num += wt * c["value"]
            den += wt
        dims[dim] = {"score": round(num / den, 4) if den else None, "components": cs}
    rewards = [
        {"signal": "concrete_nouns", "value": sum(len(b["content"]["concrete"]) for b in bars)},
        {"signal": "specific_verbs", "value": sum(len(b["content"]["vivid_verbs"]) for b in bars)},
        {"signal": "sensory_detail", "value": sum(len(b["content"]["sensory"]) for b in bars)},
        {"signal": "character_facts", "value": named},
        {"signal": "narrative_progression", "value": sp.get("progression_rate", 0.0)},
        {"signal": "image_transformation", "value": len(sp["callbacks"]), "note": "concrete images that return later"},
        {"signal": "layered_meaning", "value": None, "note": "not measurable with word lists in v0"},
        {"signal": "setup_and_payoff", "value": sp.get("integrity")},
        {"signal": "controlled_callbacks", "value": len(sp["callbacks"])},
        {"signal": "varied_syntax", "value": a.get("syntax", {}).get("variety", 0.0)},
        {"signal": "families_spanning_bars", "value": stats.get("families_spanning_3plus", 0)},
        {"signal": "purposeful_pattern_breaks", "value": sum(1 for b in a["scheme_breaks"] if b["classification"] in ("likely_intentional", "planned_break"))},
        {"signal": "emotional_consequence", "value": emo["range"]},
        {"signal": "meaning_survives_without_rhyme", "value": meaning},
    ]
    composite = None
    if s.get("emit_composite"):
        vals = [d["score"] for d in dims.values() if d["score"] is not None]
        composite = round(sum(vals) / len(vals), 4) if vals else None
    notes = [SCORE_NOTE]
    if a["confidence"].get("dictionary_backend") == "none":
        notes.append("Rhyme numbers rest on spelling-based pronunciations; expect some misses.")
    return ScoreReport(dims, genericness, rewards, composite, notes, w_all)
