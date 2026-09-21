"""xoah_canon_query: the smallest authoritative canon packet for a question.

Deterministic: no model in the loop. Canon comes from a ``CanonPacket`` built from the
private vault at runtime; this module holds no lore.

Rules this tool enforces:
  * the five ``CanonKind``s stay separate in the output; a CANDIDATE is never listed
    as a fact, and only LOCKED records are marked binding;
  * a record is relevant only when the question touches its topics (or shares real
    content words with its statement). Generic words ("canon", "lock", "existing") never
    match on their own; that is the known ask_xoah false positive, where a bare "canon"
    in an engineering question fired FACT_CONFLICT against an unrelated lock;
  * a conflict is reported only when a CANDIDATE contradicts a LOCKED record on a topic
    they share, so an unrelated lock cannot raise one;
  * records dropped by route or volume scope are counted, not silently lost;
  * the output is capped and says how much was cut.
"""
from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from .types import CanonKind, CanonPacket, CanonRecord, Provenance, ToolReceipt, receipt

# Words that describe the act of asking about canon, not the subject. They never
# establish relevance by themselves.
GENERIC: FrozenSet[str] = frozenset({
    "canon", "lore", "lock", "locks", "locked", "existing", "exist", "story", "scene", "scenes",
    "character", "fact", "facts", "about", "what", "which", "bears", "bear", "on", "this",
    "that", "the", "a", "an", "of", "for", "and", "or", "to", "in", "is", "are", "does", "do",
    "how", "why", "when", "where", "who", "it", "its", "with", "any", "all", "from", "by",
})
_TOKEN = re.compile(r"[a-z0-9]+")
KIND_KEYS = {
    CanonKind.LOCKED: "facts",
    CanonKind.CANDIDATE: "candidate_facts",
    CanonKind.PROCESS_DONOR: "process_donors",
    CanonKind.SOURCE_DONOR: "source_donors",
    CanonKind.SPECULATION: "speculation",
}


def content_words(text: str) -> FrozenSet[str]:
    return frozenset(t for t in _TOKEN.findall((text or "").lower()) if t not in GENERIC and len(t) > 1)


def _topic_words(rec: CanonRecord) -> FrozenSet[str]:
    return frozenset(w for t in rec.topics for w in _TOKEN.findall(t.lower()) if w not in GENERIC)


def relevance(rec: CanonRecord, query_words: FrozenSet[str]) -> int:
    """0 = not relevant. A topic hit counts double; a lone statement-word hit is not enough."""
    topic_hits = len(query_words & _topic_words(rec))
    stmt_hits = len(query_words & content_words(rec.statement))
    if topic_hits == 0 and stmt_hits < 2:
        return 0
    return topic_hits * 2 + stmt_hits


def in_scope(rec: CanonRecord, route: Optional[str], volume: Optional[int]) -> bool:
    if route and rec.routes and route not in rec.routes:
        return False
    if volume is not None and rec.volumes and volume not in rec.volumes:
        return False
    return True


def relevant_records(packet: CanonPacket, query: str, *, route: Optional[str] = None,
                     volume: Optional[int] = None, character: Optional[str] = None,
                     kinds: Optional[Sequence[CanonKind]] = None) -> Tuple[List[Tuple[int, CanonRecord]], int]:
    """(ranked [(score, record)], number of relevant records excluded by route/volume scope)."""
    words = content_words(query) | (content_words(character) if character else frozenset())
    allowed = set(kinds) if kinds else set(CanonKind)
    ranked: List[Tuple[int, CanonRecord]] = []
    excluded = 0
    for rec in packet.records:
        if rec.kind not in allowed:
            continue
        score = relevance(rec, words)
        if not score:
            continue
        if not in_scope(rec, route, volume):
            excluded += 1
            continue
        ranked.append((score, rec))
    ranked.sort(key=lambda sr: (-sr[0], sr[1].id))
    return ranked, excluded


def _shared_topic(a: CanonRecord, b: CanonRecord) -> bool:
    return bool(_topic_words(a) & _topic_words(b))


def _contradicts(locked: CanonRecord, other: CanonRecord) -> Optional[str]:
    for pat in locked.contradicts:
        try:
            if re.search(pat, other.statement, re.IGNORECASE):
                return pat
        except re.error:
            continue  # a malformed pattern in the vault must not break a query
    return None


def find_conflicts(records: Sequence[CanonRecord]) -> List[Dict[str, Any]]:
    """A CANDIDATE that a LOCKED record's patterns contradict, on a shared topic. Nothing else."""
    out = []
    locked = [r for r in records if r.kind.binding]
    for cand in (r for r in records if r.kind is CanonKind.CANDIDATE):
        for lk in locked:
            if not _shared_topic(lk, cand):
                continue
            pat = _contradicts(lk, cand)
            if pat:
                out.append({"locked": lk.id, "candidate": cand.id, "pattern": pat,
                            "note": "candidate contradicts a locked record; it stays a candidate"})
    return out


def _entry(score: int, rec: CanonRecord) -> Dict[str, Any]:
    return {"id": rec.id, "kind": rec.kind.value, "binding": rec.kind.binding,
            "statement": rec.statement, "score": score,
            "cites": [p.cite() for p in rec.provenance]}


def xoah_canon_query(packet: CanonPacket, query: str, *, scope: str = "all", volume: Optional[int] = None,
                     route: Optional[str] = None, character: Optional[str] = None,
                     timepoint: Optional[int] = None, max_records: int = 8) -> ToolReceipt:
    """Return a sealed receipt whose findings are grouped by canon kind.

    ``scope`` is ``"locked"`` (binding canon only) or ``"all"``. Verdicts: ``OK``,
    ``CONFLICTS`` (a candidate contradicts a lock), ``NO_MATCH``. ``timepoint`` is accepted
    for the leg's signature but knowledge-at-a-scene is ``xoah_timeline_trace``'s job, so
    it is recorded, not applied.
    """
    if scope not in ("locked", "all"):
        raise ValueError("scope must be 'locked' or 'all'")
    if max_records < 1:
        raise ValueError("max_records must be >= 1")
    kinds = [CanonKind.LOCKED] if scope == "locked" else None
    ranked, excluded = relevant_records(packet, query, route=route, volume=volume,
                                        character=character, kinds=kinds)
    kept, cut = ranked[:max_records], max(0, len(ranked) - max_records)
    sections: Dict[str, List[Dict[str, Any]]] = {k: [] for k in KIND_KEYS.values()}
    for score, rec in kept:
        sections[KIND_KEYS[rec.kind]].append(_entry(score, rec))
    conflicts = find_conflicts([r for _, r in kept])
    findings: List[Dict[str, Any]] = [
        {"section": k, "records": v} for k, v in sections.items() if v
    ]
    if conflicts:
        findings.append({"section": "conflicts", "records": conflicts})
    findings.append({"section": "scope_report", "returned": len(kept), "truncated": cut,
                     "excluded_by_route_or_volume": excluded,
                     "timepoint": ("recorded, not applied (see xoah_timeline_trace)"
                                   if timepoint is not None else None)})
    verdict = "NO_MATCH" if not kept else ("CONFLICTS" if conflicts else "OK")
    sources: List[Provenance] = [p for _, r in kept for p in r.provenance]
    return receipt("xoah_canon_query", packet,
                   {"query": query, "scope": scope, "volume": volume, "route": route,
                    "character": character, "timepoint": timepoint, "max_records": max_records},
                   verdict, findings, sources, [r.kind.value for _, r in kept])
