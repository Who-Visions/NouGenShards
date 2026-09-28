"""REPAIR mode: targeted revision instructions that keep the voice.

Repair never rewrites a verse wholesale. For each weak bar it names the
problems, lists the words that carry the speaker's voice (which must be kept),
and offers a few deterministic edit candidates: filler removed, stock phrases
turned into slots the writer fills with a real detail, and ending options in
the same rhyme family. Candidates are ranked by how much voice they keep, so
a technically cleaner bar that erases the speaker ranks lower.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from . import content as C
from .analyzer import analyze_verse, parse_lines
from .config import Config, resolve_config
from .models import RepairPlan, VerseAnalysis
from .persona import Persona, domain_terms, load_persona, voice_similarity
from .phonetics import tokenize
from .rhyme import find_rhymes
from .scorer import score_verse

_WORD_RE = re.compile(r"[A-Za-z']+")


def _norms(text: str) -> list[str]:
    return [t.norm for t in tokenize(text)]


def _generic_count(text: str, lex: C.Lexicons, cfg: Config) -> int:
    toks = tokenize(text)
    bc = C.bar_content(0, text, toks, lex, config=cfg)
    return sum(1 for f in C.generic_flags(bc, lex, cfg) if f.get("penalized"))


def rank_candidates(original: str, candidates: Sequence[dict], persona: Persona | None, config: Config | None = None) -> list[dict]:
    """Attach voice_similarity and generic_delta to each candidate and sort best first."""
    cfg = resolve_config(config)
    lex = C.Lexicons(cfg)
    base_generic = _generic_count(original, lex, cfg)
    out = []
    for c in candidates:
        c = dict(c)
        c["voice_similarity"] = round(voice_similarity(_norms(original), _norms(c["text"]), persona, lex, cfg), 3)
        c["generic_delta"] = _generic_count(c["text"], lex, cfg) - base_generic
        out.append(c)
    out.sort(key=lambda c: (-c["voice_similarity"], c["generic_delta"], c["text"]))
    return out


def _strip_phrases(text: str, phrases: Sequence[str]) -> str:
    toks = tokenize(text)
    norms = [t.norm for t in toks]
    drop = set()
    for p in phrases:
        pw = p.split()
        for i in range(len(norms) - len(pw) + 1):
            if norms[i:i + len(pw)] == pw:
                drop.update(range(i, i + len(pw)))
    kept = [t.surface + (t.punct_after if t.punct_after and t.punct_after != "-" else "") for i, t in enumerate(toks) if i not in drop]
    return " ".join(kept).strip(" ,")


def _slot_generic(text: str, phrases: Sequence[str], hint: str) -> str:
    out = text
    low = out.lower()
    for p in sorted(phrases, key=len, reverse=True):
        idx = low.find(p)
        if idx >= 0:
            out = out[:idx] + f"<{hint}>" + out[idx + len(p):]
            low = out.lower()
    return out


def suggest_repairs(
    text: str,
    analysis: VerseAnalysis | dict | None = None,
    persona: Any = None,
    weak_bars: Sequence[int] | None = None,
    config: Config | dict | None = None,
    context: dict | None = None,
) -> RepairPlan:
    cfg = resolve_config(config)
    lex = C.Lexicons(cfg)
    p = load_persona(persona, cfg) if persona is not None else None
    if analysis is None:
        ctx = dict(context or {})
        if p is not None:
            ctx.setdefault("persona", p)
        analysis = analyze_verse(text, ctx)
    a = analysis.to_dict() if isinstance(analysis, VerseAnalysis) else dict(analysis)
    bars = parse_lines(text)
    n = len(bars)
    weak_by_bar = {w["bar"]: w for w in a.get("weak_bars", [])}
    protected_by_bar = {w["bar"]: w for w in a.get("protected_bars", [])}
    targets = [b for b in (weak_bars or sorted(weak_by_bar)) if 1 <= b <= n and b not in protected_by_bar]
    facts_words = {C.light_stem(t.norm) for f in a.get("named_fact_retention", {}).get("facts", []) for t in tokenize(f["fact"])}
    persona_terms = domain_terms(p, lex) if p else set()
    actions = []
    preserved: dict[str, list[str]] = {}
    for b in targets:
        bd = a["bars"][b - 1]
        line = bd["text"]
        norms = _norms(line)
        flags = bd.get("generic_flags", [])
        reasons = weak_by_bar.get(b, {}).get("reasons") or [f["rule"] for f in flags if f.get("penalized")] or ["requested by user"]
        keep = sorted(set(bd["content"]["concrete"] + bd["content"]["numbers"] + [w.lower() for w in bd["content"]["proper"]]
                          + [w for w in norms if w in persona_terms or C.light_stem(w) in facts_words]))
        anchors = set(keep)
        if bd.get("rhymed") and bd.get("end_word"):
            keep.append(bd["end_word"])
        keep = sorted(set(keep))
        preserved[str(b)] = keep
        candidates = []
        fillers = [f["evidence"] for f in flags if f["rule"] == "filler_intensifier"]
        endings = [e for e in lex.forced_endings if " ".join(norms).endswith(e)]
        if fillers or endings:
            stripped = _strip_phrases(line, fillers + endings)
            if stripped and stripped != line:
                candidates.append({"type": "remove_filler", "text": stripped, "note": "filler and rhyme-padding removed; the bar may need a new ending"})
        stock = [f["evidence"] for f in flags if f["rule"] in ("generic_phrase", "empty_victory", "unspecified_struggle", "unsupported_cliche", "forbidden_phrase")]
        if stock:
            candidates.append({"type": "slot_detail", "text": _slot_generic(line, stock, "a specific detail only this speaker knows"),
                               "note": "replace the slot with a real object, place, number or name"})
        partner = None
        fam = bd.get("end_family")
        if fam:
            for other in a["bars"]:
                if other["bar"] != b and other.get("end_family") == fam:
                    partner = other.get("end_word")
                    break
        end_word = bd.get("end_word")
        ending_is_problem = any(f["rule"] in ("predictable_pair", "forced_syntax") for f in flags)
        options = []
        # The ending may change when it is the flagged problem, or when it is not one of the voice anchors.
        if partner and (ending_is_problem or (end_word and end_word not in anchors)):
            max_options = int(cfg.repair.get("max_ending_options", 8))
            options = [c.word for c in find_rhymes(partner, {"slant": True, "max_results": max_options}, config=cfg)
                       if c.word not in (end_word, partner)]
        for word in options[:int(cfg.repair.get("max_end_swaps", 3))]:
            swapped = _swap_end_word(line, word)
            if swapped and swapped != line:
                candidates.append({"type": "end_swap", "text": swapped,
                                   "note": f"ending swapped to '{word}', same rhyme family as '{partner}'"})
        ranked = rank_candidates(line, candidates, p, cfg)
        instruction = "Revise bar {b} ({job}). Problems: {probs}. Keep: {keep}.".format(
            b=b, job=bd["job"]["job"], probs="; ".join(reasons), keep=", ".join(keep) or "the speaker's own words")
        actions.append({"bar": b, "original": line, "problems": reasons, "preserve": keep, "instruction": instruction,
                        "candidates": ranked, "ending_options": options,
                        "rhyme_family": fam, "planned_job": bd.get("planned_job") or bd["job"]["job"]})
    lines = ["Revise only the bars listed. For each one, keep every word in its keep list, keep its rhyme family, "
             "stay inside the persona's vocabulary and metaphor domains, and change as little as possible.", ""]
    for act in actions:
        lines.append(f"- {act['instruction']}")
    lines.append("")
    lines.append("Return each revised bar with one sentence on what changed and why. Do not touch other bars.")
    return RepairPlan(
        actions=actions, llm_instructions="\n".join(lines),
        preserved_voice={"persona_id": p.id if p else None, "keep_by_bar": preserved},
        notes=["Candidates are mechanical edits and slots for the writer, not finished lyrics.",
               "Ranking favors candidates that keep the speaker's anchor words over candidates that only read cleaner."],
    )


def _swap_end_word(line: str, new_word: str) -> str | None:
    """Replace the last word of a bar, keeping its case style and any trailing punctuation."""
    words = list(_WORD_RE.finditer(line))
    if not words:
        return None
    last = words[-1]
    old = last.group()
    if old.isupper() and len(old) > 1:
        new = new_word.upper()
    elif old[0].isupper():
        new = new_word[:1].upper() + new_word[1:]
    else:
        new = new_word.lower()
    return line[:last.start()] + new + line[last.end():]


def apply_repairs(text: str, plan: RepairPlan | dict, skip_types: Sequence[str] = ("slot_detail",)) -> tuple[str, list[dict]]:
    """Apply the best finished candidate per action. Slots and unchanged candidates are never applied."""
    raw_lines = (text or "").splitlines()
    bars = parse_lines(text)
    # Map each bar to its raw line so tag blocks, comments and blank lines survive the edit.
    rows, j = [], 0
    for bar in bars:
        while raw_lines[j] != bar.raw:
            j += 1
        rows.append(j)
        j += 1
    actions = plan.actions if isinstance(plan, RepairPlan) else plan.get("actions", [])
    changes = []
    for act in actions:
        i = act["bar"] - 1
        if not 0 <= i < len(bars):
            continue
        pick = next((c for c in act["candidates"]
                     if c["type"] not in skip_types and "<" not in c["text"] and c["text"] != act["original"]), None)
        if pick is None:
            continue
        raw, old = bars[i].raw, bars[i].text
        k = raw.rfind(old)
        raw_lines[rows[i]] = raw[:k] + pick["text"] + raw[k + len(old):] if k >= 0 else pick["text"]
        changes.append({"bar": act["bar"], "type": pick["type"], "from": act["original"], "to": pick["text"],
                        "voice_similarity": pick["voice_similarity"]})
    return "\n".join(raw_lines) + ("\n" if text.endswith("\n") else ""), changes


def repair_before_after(text: str, context: dict | None = None, config: Config | dict | None = None) -> dict:
    """Analyze and score a draft, apply the repair plan mechanically, and score it again."""
    cfg = resolve_config(config)
    ctx = dict(context or {}, config=cfg)

    def snap(t: str) -> tuple[dict, VerseAnalysis]:
        a = analyze_verse(t, ctx)
        s = score_verse(a, None, cfg)
        ad = a.to_dict()
        return {"text": t, "composite": s.composite, "weak_bars": sorted(w["bar"] for w in ad.get("weak_bars", [])),
                "dimensions": {k: v.get("score") for k, v in s.dimensions.items()}}, a

    before, analysis = snap(text)
    plan = suggest_repairs(text, analysis, ctx.get("persona"), None, cfg)
    repaired, changes = apply_repairs(text, plan, cfg.repair.get("demo_skip_types", ["slot_detail"]))
    after, _ = snap(repaired)
    both = before["composite"] is not None and after["composite"] is not None
    return {
        "before": before, "after": after, "changes": changes,
        "delta": {"composite": round(after["composite"] - before["composite"], 3) if both else None,
                  "weak_bar_count": len(after["weak_bars"]) - len(before["weak_bars"])},
        "note": "Edits are mechanical (filler removed, endings swapped within the rhyme family); "
                "slots are left for the writer, and the delta can be negative.",
    }
