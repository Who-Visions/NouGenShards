"""xoah_missing_context: prove there is enough evidence before answering.

The fleet law this encodes: a recall miss is not proof of absence. "Nothing found" is
only ABSENT_PROVEN when every expected vault was read successfully; otherwise it is
CANNOT_DETERMINE. With no coverage evidence at all the answer is also CANNOT_DETERMINE,
never a default "sufficient" or "absent" (an unmeasured check must not read as a pass).

Verdicts: SUFFICIENT, INSUFFICIENT, CANNOT_DETERMINE, ABSENT_PROVEN.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from .canon_query import in_scope, relevant_records
from .types import CanonPacket, Provenance, ToolReceipt, receipt

OK_STATES = frozenset({"ok", "complete"})


def xoah_missing_context(packet: CanonPacket, query: str, *, coverage: Mapping[str, str],
                         expected_vaults: Sequence[str], route: Optional[str] = None,
                         volume: Optional[int] = None, scene_id: Optional[str] = None,
                         character: Optional[str] = None) -> ToolReceipt:
    """``coverage`` maps vault name -> state as reported by the recall that built ``packet``
    (``ok``/``complete`` means read fully; anything else, or absent, means not proven)."""
    missing_vaults = sorted(v for v in expected_vaults if str(coverage.get(v, "")).lower() not in OK_STATES)
    findings: List[Dict[str, Any]] = []

    missing_scene = None
    if scene_id is not None and packet.scene(scene_id) is None:
        missing_scene = scene_id
        findings.append({"section": "missing_scene", "scene_id": scene_id,
                         "note": "scene is not in this canon packet"})

    ranked, excluded = relevant_records(packet, query, route=route, volume=volume, character=character)
    missing_era = None
    if volume is not None and not any(volume in r.volumes for r in packet.records if r.volumes) \
            and not any(not r.volumes for r in packet.records):
        missing_era = volume
        findings.append({"section": "missing_era", "volume": volume,
                         "note": "no record in the packet covers this volume"})

    ambiguity: List[Dict[str, Any]] = []
    if route is None:
        routes = sorted({rt for _, r in ranked for rt in r.routes})
        if len(routes) > 1:
            ambiguity.append({"kind": "route", "candidates": routes,
                              "note": "relevant records are route-specific and no route was given"})
    variants = sorted({s.variant for s in packet.scenes if scene_id is None and s.route == route}) if route else []
    if len(variants) > 1:
        ambiguity.append({"kind": "variant", "candidates": variants,
                          "note": "several character variants on this route and no scene given"})
    if ambiguity:
        findings.append({"section": "ambiguity", "items": ambiguity})
    if missing_vaults:
        findings.append({"section": "missing_vaults", "vaults": missing_vaults,
                         "note": "not confirmed read; a miss here is not proof of absence"})
    if not expected_vaults:
        findings.append({"section": "no_coverage_evidence",
                         "note": "no expected vaults were given, so completeness cannot be judged"})

    if not expected_vaults:
        verdict = "CANNOT_DETERMINE"
    elif not ranked:
        verdict = "CANNOT_DETERMINE" if missing_vaults else "ABSENT_PROVEN"
        if verdict == "ABSENT_PROVEN":
            findings.append({"section": "absence", "note": f"no relevant record in packet revision "
                                                            f"{packet.revision}; all {len(expected_vaults)} expected vaults read"})
    elif missing_scene or missing_era or missing_vaults or ambiguity:
        verdict = "INSUFFICIENT"
    else:
        verdict = "SUFFICIENT"
    sources: List[Provenance] = [p for _, r in ranked for p in r.provenance]
    return receipt("xoah_missing_context", packet,
                   {"query": query, "route": route, "volume": volume, "scene_id": scene_id,
                    "character": character, "expected_vaults": list(expected_vaults),
                    "coverage": dict(coverage)},
                   verdict, findings, sources, [r.kind.value for _, r in ranked])


__all__ = ["xoah_missing_context", "OK_STATES", "in_scope"]
