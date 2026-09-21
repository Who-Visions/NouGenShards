"""xoah_timeline_trace: what she knows at a scene, and what she must not."""
from __future__ import annotations

import re
from typing import Optional

from .types import CanonKind, CanonPacket, ToolReceipt, receipt


def _hits(patterns, text: str):
    out = []
    for p in patterns:
        try:
            if re.search(p, text, re.I):
                out.append(p)
        except re.error:
            if p.lower() in text.lower():
                out.append(p)
    return out


def timeline_trace(packet: CanonPacket, scene_id: str, text: Optional[str] = None) -> ToolReceipt:
    """knowledge_before: facts learned earlier on this route; knowledge_after:
    plus facts learned in this scene; forbidden_future_knowledge: facts learned
    later -- if the scene text shows any of them, that is accidental omniscience."""
    inputs = {"scene_id": scene_id, "text_given": text is not None}
    scene = packet.scene(scene_id)
    if scene is None:
        return receipt("xoah_timeline_trace", packet, inputs, "unknown_scene",
                       [{"missing": "scene", "scene_id": scene_id}])
    body = scene.text if text is None else text
    route = [e for e in packet.timeline if e.route == scene.route]
    before = [e for e in route if e.order < scene.order]
    during = [e for e in route if e.order == scene.order]
    future = [e for e in route if e.order > scene.order]
    violations = [{"fact_id": e.fact_id, "statement": e.statement, "learned_at": e.order,
                   "matched": _hits(e.patterns, body),
                   "sources": [p.cite() for p in e.provenance]}
                  for e in future if _hits(e.patterns, body)]
    findings = [{
        "route": scene.route, "scene_order": scene.order,
        "knowledge_before": [e.fact_id for e in before],
        "knowledge_after": [e.fact_id for e in before + during],
        "forbidden_future_knowledge": [e.fact_id for e in future],
        "callbacks_available": [e.statement for e in before],
        "violations": violations,
    }]
    used = [p for e in route for p in e.provenance]
    return receipt("xoah_timeline_trace", packet, inputs,
                   "knowledge_violation" if violations else "pass",
                   findings, used, [CanonKind.LOCKED.value] if used else [])
