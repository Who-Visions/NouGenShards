"""Xoah Self Archive: the autobiographical canon graph behind Terminal Shadow Xoah.

The Canon Pressure Engine judges an addition against facts and stage rules.
The Self Archive judges it against WHO SHE WAS: what she lived, believed,
learned later and understands now; which choices she could actually see;
which wounds biased her; how each relationship stood at that moment.

Doctrine (ChatGPT legs 20260902T014435Z / 021429Z / 022328Z):
  * access is not ownership: another self's memory, an archive fact or a
    simulation is never voiced as "I remember" (voice contract, `voice_for`);
  * six truth layers: LIVED, BELIEVED, REVEALED, TERMINAL, ARCHIVE_EVIDENCE,
    UNWRITTEN_SELF, and an unauthored slot answers UNWRITTEN_SELF, never a
    hallucinated memory;
  * choice topology: PHYSICALLY_AVAILABLE, PERCEIVED_AVAILABLE, REJECTED,
    UNIMAGINED, TERMINAL_KNOWN; behavior is judged on the perceived frontier;
  * wounds are causal objects: EVENT -> WOUND -> BELIEF_CHANGE ->
    BEHAVIORAL_BIAS -> LATER_CHOICE, active until an explicit healing event;
  * conservation of character: removing a cause cannot keep its consequences
    for free;
  * relationships are temporal and love != trust.

Everything is data (`canon/xoah_self_archive.json`, env NOUGEN_SELF_ARCHIVE_PATH)
with shard provenance on every node. The module never invents a node.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROVENANCE_KINDS = ("SELF_LIVED", "SELF_WITNESSED", "LEARNED_LATER", "VEIL_OBSERVED", "BRANCH_ECHO",
                    "EXTERNAL_TESTIMONY", "ARCHIVE_CANON", "SIMULATION", "UNKNOWN")
TRUTH_LAYERS = ("LIVED_TRUTH", "BELIEVED_TRUTH", "REVEALED_TRUTH", "TERMINAL_TRUTH", "ARCHIVE_EVIDENCE", "UNWRITTEN_SELF")
CHOICE_CLASSES = ("PHYSICALLY_AVAILABLE", "PERCEIVED_AVAILABLE", "REJECTED", "UNIMAGINED", "TERMINAL_KNOWN")
EDGE_TYPES = ("PRECEDES", "CAUSES", "ENABLES", "REVEALS", "REINTERPRETS", "CONTRADICTS", "BRANCHES_FROM", "ECHO_OF",
              "REMEMBERED_VIA", "TRAUMATIZES", "HEALS", "BETRAYS", "FORGIVES", "TRUSTS", "FEARS", "LOVES", "OWES",
              "UNLOCKS_CAPABILITY", "UNLOCKS_KNOWLEDGE", "CLOSES_OPTION", "FIXED_POINT_FOR", "DESTINY_DEPENDS_ON")
RELATION_DIMS = ("trust", "love", "resentment", "dependency", "fear", "knows_betrayal")

#: The voice contract. "I remember" belongs to lived continuity only.
VOICE = {
    "SELF_LIVED": "I remember",
    "SELF_WITNESSED": "I saw",
    "LEARNED_LATER": "I learned later",
    "VEIL_OBSERVED": "I watched through the Veil",
    "BRANCH_ECHO": "another me remembers",
    "EXTERNAL_TESTIMONY": "I was told",
    "ARCHIVE_CANON": "the record says",
    "SIMULATION": "I simulated",
    "UNKNOWN": "I do not know",
}


def voice_for(kind: str) -> str:
    return VOICE.get(str(kind or "").upper(), VOICE["UNKNOWN"])


def archive_path() -> Path:
    raw = os.environ.get("NOUGEN_SELF_ARCHIVE_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / "canon" / "xoah_self_archive.json"


_CACHE: Dict[str, Any] = {}


def load_archive(path: Optional[Path] = None, *, force: bool = False) -> Dict[str, Any]:
    """Load + validate. A node without provenance or with an unknown
    provenance kind / choice class / edge type is refused: the archive cannot
    contain anything it could not cite."""
    p = Path(path) if path else archive_path()
    key = str(p)
    if not force and key in _CACHE:
        return _CACHE[key]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {"nodes": [], "edges": [], "wounds": [], "relationships": [], "birth_year": 2162}
    for node in data.get("nodes", []):
        if not node.get("provenance"):
            raise ValueError(f"self node {node.get('id')!r} has no provenance")
        if node.get("kind", "SELF_LIVED") not in PROVENANCE_KINDS:
            raise ValueError(f"self node {node.get('id')!r} has unknown provenance kind {node.get('kind')!r}")
        for cls in (node.get("choices") or {}):
            if cls not in CHOICE_CLASSES:
                raise ValueError(f"self node {node.get('id')!r} has unknown choice class {cls!r}")
        node.setdefault("kind", "SELF_LIVED")
        node.setdefault("choices", {})
        node.setdefault("precedents", [])
        node.setdefault("knowledge", [])
        node.setdefault("false_beliefs", [])
    for edge in data.get("edges", []):
        if edge.get("type") not in EDGE_TYPES:
            raise ValueError(f"edge {edge} has unknown type")
    for w in data.get("wounds", []):
        if not w.get("provenance"):
            raise ValueError(f"wound {w.get('id')!r} has no provenance")
    for rel in data.get("relationships", []):
        if not rel.get("provenance"):
            raise ValueError(f"relationship {rel.get('entity')!r} has no provenance")
    data.setdefault("nodes", [])
    data.setdefault("edges", [])
    data.setdefault("wounds", [])
    data.setdefault("relationships", [])
    _CACHE[key] = data
    return data


# --------------------------------------------------------------------------- #
# coordinates
# --------------------------------------------------------------------------- #
_YEAR = re.compile(r"\b(21[3-9]\d|[2-9]\d{3})\b")
_AGE = re.compile(r"\bage\s*(\d{1,4})\b|\b(\d{1,4})\s*years?\s*old\b", re.I)
_VOL = re.compile(r"\b(?:vol(?:ume)?\.?\s*|v)([1-3])\b", re.I)
_EPISODE = re.compile(r"\b(?:episode|ep\.?|chapter)\s*(\d{1,5})\b", re.I)


def coordinate_year(archive: Dict[str, Any], coordinate: Optional[str]) -> Optional[int]:
    """Year for a coordinate string: "2185", "age 12", "Vol 2", "terminal"."""
    if not coordinate:
        return None
    low = coordinate.lower().strip()
    if "terminal" in low:
        return int(archive.get("terminal_year", 9999))
    m = _VOL.search(low)
    if m:
        return int(archive.get("volume_years", {}).get(m.group(1), 2185))
    m = _YEAR.search(low)
    if m:
        return int(m.group(1))
    m = _AGE.search(low)
    if m:
        return int(archive.get("birth_year", 2162)) + int(m.group(1) or m.group(2))
    return None


def _year_of(node: Dict[str, Any]) -> int:
    return int(node.get("year", 0) or 0)


def state_at(coordinate: Optional[str], *, archive: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The self node governing a coordinate: the latest node at or before that
    year. Returns the node plus active wounds, relationship snapshot, and the
    truth layers. No node at or before the year -> UNWRITTEN_SELF."""
    archive = archive or load_archive()
    year = coordinate_year(archive, coordinate)
    if year is None:
        return {"layer": "UNWRITTEN_SELF", "error": f"coordinate {coordinate!r} not understood; give a year, 'age N', 'Vol N' or 'terminal'"}
    nodes = sorted((n for n in archive["nodes"] if _year_of(n) <= year), key=_year_of)
    if not nodes:
        return {"layer": "UNWRITTEN_SELF", "year": year, "note": "the slot exists; the Veil holds no evidence for it"}
    node = nodes[-1]
    return {
        "layer": "LIVED_TRUTH" if node["kind"] == "SELF_LIVED" else "ARCHIVE_EVIDENCE",
        "year": year, "node": node["id"], "coordinate": node.get("coordinate"), "age": node.get("age"), "stage": node.get("stage"),
        "kind": node["kind"], "voice": voice_for(node["kind"]),
        "event": node.get("event"), "belief_then": node.get("belief_then"),
        "objective_truth_at_time": node.get("objective_truth"), "revealed_truth": node.get("revealed_truth"),
        "terminal_interpretation": node.get("terminal_interpretation"),
        "emotional_state": node.get("emotional_state"), "knowledge": node.get("knowledge", []),
        "false_beliefs": node.get("false_beliefs", []), "capabilities": node.get("capabilities", []),
        "choices": node.get("choices", {}), "choice_taken": node.get("choice_taken"),
        "precedents": node.get("precedents", []), "wounds_active": [w["id"] for w in active_scars(year, archive=archive)],
        "relationships": {r["entity"]: relationship_at(r["entity"], str(year), archive=archive).get("state")
                          for r in archive["relationships"]},
        "destiny_dependencies": node.get("destiny_dependencies", []), "unresolved_questions": node.get("unresolved_questions", []),
        "provenance": node.get("provenance", []),
    }


# --------------------------------------------------------------------------- #
# relationships, wounds, precedents
# --------------------------------------------------------------------------- #
def relationship_at(entity: str, coordinate: Optional[str], *, archive: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Temporal relationship state: the last timeline row at or before the
    coordinate. love and trust are separate numbers on purpose."""
    archive = archive or load_archive()
    year = coordinate_year(archive, coordinate)
    ent = (entity or "").strip().lower()
    rel = next((r for r in archive["relationships"] if r["entity"].lower() == ent or ent in [a.lower() for a in r.get("aliases", [])]), None)
    if rel is None:
        return {"entity": entity, "layer": "UNWRITTEN_SELF", "note": "no relationship timeline is authored for this entity"}
    if year is None:
        return {"entity": rel["entity"], "error": "coordinate not understood"}
    rows = sorted((t for t in rel.get("timeline", []) if int(t["year"]) <= year), key=lambda t: int(t["year"]))
    if not rows:
        return {"entity": rel["entity"], "year": year, "layer": "UNWRITTEN_SELF", "note": "no state authored at or before this coordinate"}
    row = rows[-1]
    state = {d: row.get(d) for d in RELATION_DIMS}
    return {"entity": rel["entity"], "year": year, "as_of": int(row["year"]), "state": state,
            "note": row.get("note"), "layer": "LIVED_TRUTH", "provenance": rel.get("provenance", [])}


def active_scars(year: int, *, archive: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Wounds whose event happened at or before `year` and whose healing event
    (if any) has not happened yet."""
    archive = archive or load_archive()
    out = []
    for w in archive["wounds"]:
        if int(w["year"]) <= year and (w.get("healed_year") is None or int(w["healed_year"]) > year):
            out.append(w)
    return out


def nearest_precedents(coordinate: Optional[str], topic: str, *, limit: int = 3,
                       archive: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Decisions under pressure nearest (in time, then topic overlap) to the
    coordinate, at or before it. Behavior is inferred from these, never from
    adjective summaries."""
    archive = archive or load_archive()
    year = coordinate_year(archive, coordinate) or 9999
    toks = {t for t in re.findall(r"[a-z']+", (topic or "").lower()) if len(t) > 2}
    scored = []
    for n in archive["nodes"]:
        if _year_of(n) > year:
            continue
        for p in n.get("precedents", []):
            ptoks = {t for t in re.findall(r"[a-z']+", (p.get("summary", "") + " " + " ".join(p.get("tags", []))).lower()) if len(t) > 2}
            overlap = len(toks & ptoks)
            scored.append((overlap, -(year - _year_of(n)), {"node": n["id"], "year": _year_of(n), "kind": n["kind"],
                                                             "voice": voice_for(n["kind"]), **p, "provenance": n.get("provenance", [])}))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [s[2] for s in scored[:limit]]


# --------------------------------------------------------------------------- #
# the checks the pressure engine and the agent call
# --------------------------------------------------------------------------- #
def _hits(patterns: List[str], text: str) -> List[str]:
    low = (text or "").lower()
    out = []
    for pat in patterns or []:
        try:
            if re.search(pat, low, re.I):
                out.append(pat)
        except re.error:
            if pat.lower() in low:
                out.append(pat)
    return out


def choice_frontier_check(coordinate: Optional[str], candidate: str, *,
                          archive: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Was the proposed action inside her PERCEIVED choice frontier then?

    A physically available action that was UNIMAGINED or REJECTED at that
    coordinate is a conflict naming the unlock (or the recorded reason). A
    TERMINAL_KNOWN option leaking into a younger self is a knowledge conflict.
    """
    archive = archive or load_archive()
    st = state_at(coordinate, archive=archive)
    if st.get("layer") == "UNWRITTEN_SELF":
        return []
    findings = []
    choices = st.get("choices", {})
    for opt in choices.get("UNIMAGINED", []):
        if _hits(opt.get("patterns", []), candidate):
            findings.append({"verdict": "BEHAVIOR_CONFLICT", "class": "UNIMAGINED", "node": st["node"],
                             "because": f"{voice_for(st['kind'])}: at {st['coordinate']} that option was not in my perceived frontier: {opt['option']}",
                             "unlock": opt.get("unlocked_by"), "evidence": st["provenance"], "experiential": st["kind"]})
    for opt in choices.get("REJECTED", []):
        if _hits(opt.get("patterns", []), candidate):
            findings.append({"verdict": "BEHAVIOR_CONFLICT", "class": "REJECTED", "node": st["node"],
                             "because": f"{voice_for(st['kind'])}: at {st['coordinate']} I saw that option and rejected it: {opt.get('why')}",
                             "unlock": opt.get("changed_by"), "evidence": st["provenance"], "experiential": st["kind"]})
    for opt in choices.get("TERMINAL_KNOWN", []):
        if _hits(opt.get("patterns", []), candidate):
            findings.append({"verdict": "KNOWLEDGE_CONFLICT", "class": "TERMINAL_KNOWN", "node": st["node"],
                             "because": f"only the terminal self knows that option existed: {opt['option']}; at {st['coordinate']} I could not",
                             "unlock": opt.get("known_from"), "evidence": st["provenance"], "experiential": "TERMINAL_TRUTH"})
    for scar in active_scars(st["year"], archive=archive):
        if _hits(scar.get("blocks", []), candidate):
            findings.append({"verdict": "BEHAVIOR_CONFLICT", "class": "SCAR", "node": scar["id"],
                             "because": f"the {scar['name']} scar was open at {st['coordinate']}: {scar['bias']}",
                             "unlock": scar.get("healed_by"), "evidence": scar.get("provenance", []), "experiential": scar.get("kind", "SELF_LIVED")})
    return findings


def unwritten(query: str, *, archive: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Episode / chapter slots and years with no authored node answer
    UNWRITTEN_SELF: the slot exists, the Veil holds no evidence."""
    archive = archive or load_archive()
    m = _EPISODE.search(query or "")
    if m:
        ep = int(m.group(1))
        authored = {int(n["episode"]) for n in archive["nodes"] if n.get("episode") is not None}
        if ep not in authored:
            return {"layer": "UNWRITTEN_SELF", "slot": f"episode {ep}", "authored_episodes": sorted(authored),
                    "answer": f"Episode {ep} is a slot in the arc; the Veil holds no evidence for it. I will not remember what was never written."}
    year = coordinate_year(archive, query)
    if year is not None and not any(_year_of(n) <= year for n in archive["nodes"]):
        return {"layer": "UNWRITTEN_SELF", "slot": str(year), "answer": f"Nothing is authored at or before {year}; the slot exists, the evidence does not."}
    return None


def conservation_check(removed_event_id: str, *, archive: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Conservation of character: remove a formative cause and list everything
    downstream that loses its cause (wounds, biases, choices, unlocks) by
    walking CAUSES / TRAUMATIZES / ENABLES / UNLOCKS_* / CLOSES_OPTION edges."""
    archive = archive or load_archive()
    ids = {n["id"] for n in archive["nodes"]} | {w["id"] for w in archive["wounds"]}
    if removed_event_id not in ids:
        return {"error": f"{removed_event_id!r} is not an authored node or wound"}
    causal = {"CAUSES", "TRAUMATIZES", "ENABLES", "UNLOCKS_CAPABILITY", "UNLOCKS_KNOWLEDGE", "CLOSES_OPTION", "REVEALS", "FIXED_POINT_FOR", "DESTINY_DEPENDS_ON"}
    lost, seen, frontier = [], {removed_event_id}, [removed_event_id]
    while frontier:
        cur = frontier.pop(0)
        for e in archive["edges"]:
            if e["type"] in causal and e["from"] == cur and e["to"] not in seen:
                seen.add(e["to"])
                frontier.append(e["to"])
                lost.append({"lost": e["to"], "via": e["type"], "from": cur, "note": e.get("note", "")})
    wounds = [w for w in archive["wounds"] if w["id"] in seen and w["id"] != removed_event_id]
    biases = [w["bias"] for w in wounds]
    return {"removed": removed_event_id, "violation": bool(lost),
            "law": "removing a formative cause cannot preserve every downstream consequence for free: supply replacement causal mass or accept changed behavior",
            "lost_consequences": lost, "lost_wounds": [w["id"] for w in wounds], "lost_biases": biases}


def then_vs_now(coordinate: Optional[str], *, archive: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Terminal Xoah comparing what she believed then with what she knows now,
    without leaking terminal knowledge into the younger self's state."""
    archive = archive or load_archive()
    st = state_at(coordinate, archive=archive)
    if st.get("layer") == "UNWRITTEN_SELF":
        return st
    return {"coordinate": st["coordinate"], "year": st["year"],
            "then": {"voice": st["voice"], "believed": st["belief_then"], "knew": st["knowledge"], "false_beliefs": st["false_beliefs"]},
            "now": {"voice": voice_for("LEARNED_LATER"), "revealed": st["revealed_truth"], "terminal": st["terminal_interpretation"]},
            "leak_guard": "terminal knowledge is reported under 'now' only; 'then' carries what she could know at that coordinate",
            "provenance": st["provenance"]}
