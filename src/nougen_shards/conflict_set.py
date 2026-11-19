"""Conflict set for recall: surface disagreeing shards instead of hiding them.

Recall used to return ranked hits and nothing else, so when two retrieved
shards disagreed (an old claim and its later correction, or two lanes
recording different answers) the reader got both with no signal that they
were in tension, or got only the higher-ranked one. This module finds those
pairs among the retrieved shards and renders them as an explicit, unresolved
block appended to the recall packet.

Design choices and where they come from (ideas only, no code taken):

* Preserve and pass the ranked conflict set to the reader instead of collapsing
  it to one winner: arXiv 2611.22461 reports that this is the one memory
  mechanism that survived its gated ablation, while a write-time trust gate
  cost accuracy. So nothing here drops, down-ranks or picks a side.
* Conflicts tend to vanish at handoffs between agents (arXiv 2611.22245), so
  the block names both shards by stable reference for the next lane.
* Detection is symbolic and cheap (no model call in the recall hot path); the
  write-time LLM decider in ``consolidate`` stays where it is.

Everything threshold-shaped resolves from the environment with a logged
fallback (see ``_env_int`` / ``_env_float``).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from nougen_shards.consolidate import RETRACTION_CUE, _tokens

log = logging.getLogger(__name__)

ENV_ENABLED = "NOUGEN_RECALL_CONFLICT_SET"
ENV_MIN_OVERLAP = "NOUGEN_CONFLICT_MIN_OVERLAP"
ENV_MIN_JACCARD = "NOUGEN_CONFLICT_MIN_JACCARD"
ENV_MAX_PAIRS = "NOUGEN_CONFLICT_MAX_PAIRS"
ENV_SNIPPET_CHARS = "NOUGEN_CONFLICT_SNIPPET_CHARS"
ENV_SCAN_CHARS = "NOUGEN_CONFLICT_SCAN_CHARS"

ENV_RESTATEMENT_JACCARD = "NOUGEN_CONFLICT_RESTATEMENT_JACCARD"
_FALLBACK_RESTATEMENT_JACCARD = 0.6
_FALLBACK_MIN_OVERLAP = 4
_FALLBACK_MIN_JACCARD = 0.08
_FALLBACK_MAX_PAIRS = 5
_FALLBACK_SNIPPET_CHARS = 160
_FALLBACK_SCAN_CHARS = 4000

# Words a lane writes when it is correcting the record, beyond the
# conversational cues consolidate already knows ("no longer", "actually").
CORRECTION_CUE = re.compile(
    r"\b(correction|corrected|retract(?:ed|ion|s)?|supersed(?:e|es|ed|ing)|amend(?:ed|s|ment)?|"
    r"contradict(?:s|ed|ion)?|disputed?|is wrong|was wrong|stale|outdated|false alarm|"
    r"not\s+(?:true|correct|accurate)|do not (?:trust|use|advertise))\b", re.I)

_REF = re.compile(r"(?:shard:)?(\d+)\s*@\s*db\s*(\d+)", re.I)
_SUPERSEDES_TAG = re.compile(r"supersedes:\s*(?:shard:)?(\d+)(?:\s*@\s*db\s*(\d+))?", re.I)


def _env_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    if raw:
        log.warning("%s=%r is not an integer; using fallback %s", name, raw, fallback)
    return fallback


def _env_float(name: str, fallback: float) -> float:
    raw = os.environ.get(name, "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            log.warning("%s=%r is not a number; using fallback %s", name, raw, fallback)
    return fallback


def enabled() -> bool:
    """On unless the operator switches it off."""
    return os.environ.get(ENV_ENABLED, "1").strip().lower() not in ("0", "false", "off", "no")


def _locator(item: Dict[str, Any]) -> Dict[str, Any]:
    """Where a shard fetched from a peer really lives. Peer results arrive with
    ``id`` rewritten to ``cloud_<identity>`` and ``_db_index`` to
    ``cloud_<peer>``; the id and database a correction would name are kept in
    ``source_locator``."""
    loc = item.get("source_locator")
    return loc if isinstance(loc, dict) else {}


def _key(item: Dict[str, Any]) -> Tuple[str, str]:
    """The (shard id, database) a reference such as ``101@db1`` would name."""
    loc = _locator(item)
    if loc.get("shard_id") is not None:
        return str(loc.get("shard_id")), str(loc.get("db_index") if loc.get("db_index") is not None else "")
    return str(item.get("id", "")), str(item.get("_db_index", item.get("db", "")) or "")


def _identity(item: Dict[str, Any]) -> Tuple[str, str, str]:
    """Unique per shard across nodes: the same id and database on two different
    peers are two different shards."""
    sid, db = _key(item)
    return sid, db, str(_locator(item).get("node") or "")


def _ref(item: Dict[str, Any]) -> str:
    sid, db = _key(item)
    return f"{sid}@db{db}" if db else sid


def _text(item: Dict[str, Any], scan_chars: int) -> str:
    title = str(item.get("title") or "")
    body = str(item.get("content") or item.get("text") or "")
    return (title + "\n" + body)[:scan_chars]


def _tags(item: Dict[str, Any]) -> str:
    tags = item.get("tags") or ""
    if isinstance(tags, (list, tuple, set)):
        return " ".join(str(t) for t in tags)
    return str(tags)


_NEGATION = re.compile(r"\b(?:not|no longer|never|cannot|isn't|aren't|wasn't|weren't|doesn't|don't|didn't|"
                       r"won't|can't|without|neither|nor)\b|\bn't\b", re.I)


def _negation_count(text: str) -> int:
    """How many negations a shard holds. Two shards with the same vocabulary but
    a different count are making opposite claims, not repeating each other."""
    return len(_NEGATION.findall(text or ""))


def _points_at(text: str, tags: str, other: Dict[str, Any],
               source: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Does this shard name the other one by reference? Returns the signal name.

    A reference such as ``101@db1`` names an id inside one store. Each peer
    numbers its own shards, so the reference only means the other shard when
    both came from the same store; ``101@db1`` written on one peer says nothing
    about shard 101 on another. Disagreement across peers is still found by
    the cue-and-shared-subject path.
    """
    oid, odb = _key(other)
    if not oid:
        return None
    if source is not None and _identity(source)[2] != _identity(other)[2]:
        return None
    for m in _SUPERSEDES_TAG.finditer(tags + "\n" + text):
        if m.group(1) == oid and (not m.group(2) or not odb or m.group(2) == odb):
            return "supersedes_marker"
    for m in _REF.finditer(text):
        if m.group(1) == oid and (not odb or m.group(2) == odb):
            return "names_reference"
    return None


def find_conflicts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pairs of retrieved shards that disagree, strongest signal first.

    ``items`` are recall hits (``id``, ``_db_index``, ``title``, ``content``,
    ``timestamp``, ``tags``). Order is preserved as rank. A pair is reported
    when the later shard either marks the earlier one as superseded, or names
    it by reference alongside a correction cue, or carries a correction cue
    and shares enough vocabulary with it. Nothing is resolved: the return value
    describes the disagreement and both sides.
    """
    if len(items) < 2:
        return []
    min_overlap = _env_int(ENV_MIN_OVERLAP, _FALLBACK_MIN_OVERLAP)
    min_jaccard = _env_float(ENV_MIN_JACCARD, _FALLBACK_MIN_JACCARD)
    max_pairs = _env_int(ENV_MAX_PAIRS, _FALLBACK_MAX_PAIRS)
    scan_chars = _env_int(ENV_SCAN_CHARS, _FALLBACK_SCAN_CHARS)
    restatement_jaccard = _env_float(ENV_RESTATEMENT_JACCARD, _FALLBACK_RESTATEMENT_JACCARD)

    prepared = []
    for rank, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        text = _text(item, scan_chars)
        prepared.append({
            "item": item, "rank": rank, "text": text, "tags": _tags(item),
            "tokens": _tokens(text), "ts": str(item.get("timestamp") or ""),
            "cue": bool(CORRECTION_CUE.search(text) or RETRACTION_CUE.search(text)),
            "negations": _negation_count(text),
        })

    strength = {"supersedes_marker": 3, "names_reference": 2, "cue_overlap": 1}
    found: List[Dict[str, Any]] = []
    seen = set()
    for i, a in enumerate(prepared):
        for b in prepared[i + 1:]:
            if _identity(a["item"]) == _identity(b["item"]):
                continue
            # Which side is disputing which:
            #  - both timestamps known: only the later shard can dispute the
            #    earlier one;
            #  - a timestamp missing: either order is tried, and the disputing
            #    side is the one that carries the marker or the cue. If both
            #    sides qualify equally, the higher-ranked hit is reported as the
            #    disputing side (``a`` comes first in rank order).
            pair = None
            for later, earlier in ((a, b), (b, a)):
                if later["ts"] and earlier["ts"] and later["ts"] < earlier["ts"]:
                    continue
                signal = _points_at(later["text"], later["tags"], earlier["item"], later["item"])
                if signal == "names_reference" and not later["cue"]:
                    signal = None            # citing a shard is not disputing it
                if signal is None and later["cue"]:
                    shared = later["tokens"] & earlier["tokens"]
                    union = later["tokens"] | earlier["tokens"]
                    jaccard = len(shared) / len(union) if union else 0.0
                    # Two shards that both carry a cue and say nearly the same
                    # thing are a restatement ("X is not licensed" /
                    # "Confirmed: X is not licensed"), not a disagreement.
                    # ...unless one side negates and the other does not ("is
                    # licensed" / "is not licensed"): same words, opposite claim.
                    restated = (earlier["cue"] and jaccard >= restatement_jaccard
                                and later["negations"] == earlier["negations"])
                    if len(shared) >= min_overlap and jaccard >= min_jaccard and not restated:
                        signal = "cue_overlap"
                if signal and (pair is None or strength[signal] > strength[pair["signal"]]):
                    pair = {"signal": signal, "later": later, "earlier": earlier}
            if pair is None:
                continue
            ident = frozenset((_identity(pair["later"]["item"]), _identity(pair["earlier"]["item"])))
            if ident in seen:
                continue
            seen.add(ident)
            found.append(pair)

    found.sort(key=lambda p: (-strength[p["signal"]], min(p["later"]["rank"], p["earlier"]["rank"])))
    out = []
    for p in found[:max(max_pairs, 0)]:
        out.append({
            "signal": p["signal"],
            "later": _describe(p["later"]),
            "earlier": _describe(p["earlier"]),
        })
    return out


def _describe(side: Dict[str, Any]) -> Dict[str, Any]:
    item = side["item"]
    return {
        "ref": _ref(item), "rank": side["rank"], "timestamp": side["ts"],
        "title": str(item.get("title") or "").strip(),
        "source_node": str(_locator(item).get("node") or item.get("source_node") or item.get("node") or ""),
    }


_SIGNAL_TEXT = {
    "supersedes_marker": "the later shard is marked as superseding the earlier one",
    "names_reference": "the later shard names the earlier one and reads as a correction",
    "cue_overlap": "the later shard reads as a correction on the same subject",
}


def render(conflicts: List[Dict[str, Any]]) -> str:
    """The block appended to a recall packet. Empty string when there is nothing."""
    if not conflicts:
        return ""
    snippet = _env_int(ENV_SNIPPET_CHARS, _FALLBACK_SNIPPET_CHARS)

    def side(d: Dict[str, Any]) -> str:
        bits = [d["ref"]]
        if d["timestamp"]:
            bits.append(d["timestamp"][:19])
        if d["source_node"]:
            bits.append(d["source_node"])
        title = d["title"][:snippet]
        return f"{' | '.join(bits)}" + (f" | {title}" if title else "")

    lines = [f"[CONFLICT SET] {len(conflicts)} pair(s) of recalled shards disagree. "
             "Both sides are kept and neither is ruled correct here: read both, "
             "check the source, and carry the disagreement forward in any handoff."]
    for n, c in enumerate(conflicts, 1):
        lines.append(f"{n}. later:   {side(c['later'])}")
        lines.append(f"   earlier: {side(c['earlier'])}")
        lines.append(f"   why flagged: {_SIGNAL_TEXT.get(c['signal'], c['signal'])}")
    return "\n".join(lines)


def annotate(packet: str, items: List[Dict[str, Any]]) -> str:
    """Append the conflict block to a recall packet. Never raises: a fault in
    conflict detection must not cost the caller its recall."""
    if not enabled():
        return packet
    try:
        block = render(find_conflicts(items))
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("conflict set skipped: %s", exc)
        return packet
    return packet + "\n\n" + block if block else packet
