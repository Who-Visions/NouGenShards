"""COMPILE mode: turn a blueprint into a provider-neutral prompt and constraint packet.

The compiled prompt asks a model to return candidates and diagnostics as
separate fields and never to count a bar as done just because it rhymes. The
output is plain text and JSON; nothing here talks to a network or names a
vendor.
"""

from __future__ import annotations

import json

from .config import Config, resolve_config
from .models import CompiledPrompt, VerseBlueprint

PROVIDER_FORMATS = {"generic": "text", "chat": "messages", "json": "json"}

GENERATION_SEQUENCE = [
    "Write an unrhymed content skeleton: one plain sentence per bar that does the bar's job.",
    "Check each bar against its assigned job.",
    "Pick words for the assigned rhyme families.",
    "Draft the stressed phrase endings for each bar.",
    "Add internal rhymes at the planned positions.",
    "Fit the cadence to the planned cells and rests.",
    "Check each breath group for a usable rest.",
    "Restore natural word order wherever the rhyme bent it.",
    "Test every bar against the persona contract.",
    "Remove generic phrases and cliches without concrete support.",
    "Repair the weakest bars without flattening the voice.",
    "Audit setups and payoffs, callbacks and required facts one last time.",
]

SELF_CHECK = [
    "For each bar, name the job it performs. A bar whose only achievement is rhyming has failed.",
    "List every required fact and the bar it appears in.",
    "Quote any phrase from the forbidden list that you used. The expected answer is none.",
    "For each planned flow switch, say what in the story causes it.",
    "For each breath group, point to the rest where a breath fits.",
    "Name any bar where the persona's voice may have slipped, and why.",
    "Do not copy lines from existing songs. Write new lines only.",
]

REVISION_LOOP = [
    "Score your own draft against the self-check list.",
    "Rewrite only the bars that fail, keeping the words listed as voice anchors.",
    "Return the revised candidates and a fresh diagnostics list.",
]


def output_schema() -> dict:
    return {
        "type": "object",
        "required": ["candidates", "diagnostics"],
        "properties": {
            "candidates": {
                "type": "array",
                "items": {"type": "object", "required": ["bar", "text"], "properties": {
                    "bar": {"type": "integer", "minimum": 1}, "text": {"type": "string"},
                    "job": {"type": "string"}, "rhyme_family": {"type": ["string", "null"]}}},
            },
            "diagnostics": {
                "type": "array",
                "items": {"type": "object", "required": ["bar", "job_fulfilled", "how"], "properties": {
                    "bar": {"type": "integer", "minimum": 1}, "job_fulfilled": {"type": "boolean"}, "how": {"type": "string"},
                    "facts_used": {"type": "array", "items": {"type": "string"}},
                    "forbidden_used": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}}}},
            },
        },
        "additionalProperties": False,
    }


def _packet(bp: dict) -> dict:
    return {
        "persona_contract": bp.get("persona"),
        "content_spine": bp.get("content_spine"),
        "open_questions": bp.get("open_questions", []),
        "bar_objectives": bp.get("bar_objectives", []),
        "rhyme_families": bp.get("rhyme_family_assignments", []),
        "beat_grid": {
            "grid": bp.get("grid"),
            "cadence_cells": bp.get("cadence_cells", []),
            "stressed_syllable_targets": bp.get("stressed_syllable_targets", []),
            "end_rhyme_placements": bp.get("end_rhyme_placements", []),
            "internal_rhyme_placements": bp.get("internal_rhyme_placements", []),
            "rest_positions": bp.get("rest_positions", []),
        },
        "breath_constraints": bp.get("breath_groups", []),
        "required_facts": bp.get("required_facts", []),
        "forbidden_cliches": bp.get("forbidden_phrases", []),
        "flow_switch_rationale": bp.get("flow_switches", []),
        "scheme_breaks": bp.get("scheme_breaks", []),
        "callbacks": bp.get("callbacks", []),
        "setup_payoff_links": bp.get("setup_payoff_links", []),
        "specificity_anchors": bp.get("specificity_anchors", []),
        "delivery": bp.get("delivery_instructions", []),
        "emotion_curve": bp.get("emotion_curve", []),
        "revision_priorities": bp.get("revision_priorities", []),
    }


def _render_user(packet: dict) -> str:
    lines = ["Write a verse under the plan below. Return JSON matching the output schema, with candidates and diagnostics in separate fields.", ""]
    spine = packet["content_spine"] or {}
    lines.append("CONTENT SPINE")
    for k, v in spine.items():
        if v:
            lines.append(f"- {k.replace('_', ' ')}: {v if isinstance(v, str) else ', '.join(map(str, v))}")
    if packet["open_questions"]:
        lines.append("Unanswered (decide these first, and say what you decided): " + " ".join(packet["open_questions"]))
    lines += ["", "BARS"]
    fam_by_bar = {p["bar"]: p for p in packet["beat_grid"]["end_rhyme_placements"]}
    for o in packet["bar_objectives"]:
        fam = fam_by_bar.get(o["bar"])
        rhyme = f"end family {fam['family']} ({fam['syllables']} syllable match)" if fam else "no end rhyme expected"
        lines.append(f"- bar {o['bar']}: {o['job']} ({o['objective']}); {rhyme}; cell {o.get('cell')}")
    lines += ["", "RHYME FAMILIES"]
    for f in packet["rhyme_families"]:
        lines.append(f"- {f['label']}: stressed vowel {f['anchor_vowel']}, bars {f['bars']}, options to consider: {', '.join(f['suggested_endings'][:6])}")
    if packet["flow_switch_rationale"]:
        lines += ["", "FLOW SWITCHES"]
        for s in packet["flow_switch_rationale"]:
            lines.append(f"- bar {s['coordinate']['bar']}: {s['previous_grammar']['cell']} to {s['next_grammar']['cell']}, cause {s['cause']} ({s['semantic_trigger']}). {s['delivery_instruction']}")
    lines += ["", "BREATH", *[f"- bars {g['bars']}: leave a rest you can breathe in" for g in packet["breath_constraints"]]]
    if packet["required_facts"]:
        lines += ["", "REQUIRED FACTS", *[f"- {f}" for f in packet["required_facts"]]]
    if packet["forbidden_cliches"]:
        lines += ["", "DO NOT USE", *[f"- {f}" for f in packet["forbidden_cliches"]]]
    persona = packet["persona_contract"]
    if persona:
        lines += ["", "PERSONA", f"- {persona.get('name') or persona.get('id')}: {persona.get('worldview', '')}"]
        vr = persona.get("vocabulary_range") or {}
        if vr:
            lines.append(f"- register {vr.get('register', '')}; prefer {', '.join(vr.get('preferred', []))}; avoid {', '.join(vr.get('avoided', []))}")
        if persona.get("metaphor_domains"):
            lines.append(f"- metaphor domains: {', '.join(persona['metaphor_domains'])}")
    lines += ["", "FULL CONSTRAINT PACKET (JSON)", json.dumps(packet, sort_keys=True)]
    return "\n".join(lines)


SYSTEM_TEXT = (
    "You are drafting rap lyrics under an explicit compositional plan. Content comes first: every bar must do its "
    "assigned job, and rhyme can never be the only reason a line exists. Keep the persona's voice. Use concrete, "
    "specific detail instead of stock phrases. Write only new, original lines; do not reuse or imitate lines from "
    "existing songs. Report candidates and diagnostics separately and be honest in the diagnostics."
)


def compile_prompt(blueprint: VerseBlueprint | dict, provider: str | None = None, config: Config | dict | None = None) -> CompiledPrompt:
    resolve_config(config)
    bp = blueprint.to_dict() if isinstance(blueprint, VerseBlueprint) else dict(blueprint)
    name = (provider or "generic").lower()
    if name not in PROVIDER_FORMATS:
        raise ValueError(f"unknown provider format {provider!r}; use one of {sorted(PROVIDER_FORMATS)}")
    packet = _packet(bp)
    fmt = PROVIDER_FORMATS[name]
    user = json.dumps({"constraint_packet": packet, "output_schema": output_schema()}, sort_keys=True) if fmt == "json" else _render_user(packet)
    messages = [{"role": "system", "content": SYSTEM_TEXT}, {"role": "user", "content": user}] if fmt != "json" else []
    return CompiledPrompt(
        provider=name, format=fmt, system=SYSTEM_TEXT, user=user, messages=messages, constraint_packet=packet,
        output_schema=output_schema(), generation_sequence=list(GENERATION_SEQUENCE), self_check=list(SELF_CHECK),
        revision_loop=list(REVISION_LOOP),
        notes=["Provider-neutral: send system and user text to any chat-style model, or use the JSON packet directly.",
               "Check the returned verse with analyze_verse before trusting its diagnostics."],
    )
