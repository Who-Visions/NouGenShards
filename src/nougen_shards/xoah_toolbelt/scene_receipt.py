"""xoah_scene_receipt: one machine-readable receipt per generated/revised scene."""
from __future__ import annotations

from typing import Optional

from .power import power_ceiling
from .pressure import relevant, scene_pressure_test
from .timeline import _hits, timeline_trace
from .types import CanonPacket, ToolReceipt, receipt

NOT_BUILT = "not_implemented_in_v1_slice"


def scene_receipt(packet: CanonPacket, scene_id: str, text: Optional[str] = None,
                  model_and_prompt_hash: Optional[str] = None) -> ToolReceipt:
    scene = packet.scene(scene_id)
    inputs = {"scene_id": scene_id, "model_and_prompt_hash": model_and_prompt_hash}
    if scene is None:
        return receipt("xoah_scene_receipt", packet, inputs, "unknown_scene",
                       [{"missing": "scene", "scene_id": scene_id}])
    body = scene.text if text is None else text
    tl = timeline_trace(packet, scene_id, body)
    pressure = scene_pressure_test(packet, scene_id, body)
    caps = [c for c in packet.capabilities if _hits(c.patterns, body)]
    power = power_ceiling(packet, scene_id, body) if caps else None
    rel = [r for r in packet.records if relevant(r, scene, body)]
    canon = [r for r in rel if r.kind.binding]
    cand = [r for r in rel if not r.kind.binding]
    canon_sources = sorted({p.cite() for p in tl.sources} | {p.cite() for r in canon for p in r.provenance}
                           | ({p.cite() for p in power.sources} if power else set()))
    p0 = pressure.findings[0] if pressure.findings else {}
    fields = {
        "scene_id": scene_id, "route": scene.route, "variant": scene.variant, "volume": scene.volume,
        "canon_sources": canon_sources,
        "candidate_sources": sorted({f"{r.kind.value}:{r.id}" for r in cand}),
        "timeline_state": {"verdict": tl.verdict, **(tl.findings[0] if tl.findings else {})},
        "power_state": {"verdict": power.verdict, **power.findings[0]} if power else
                       {"verdict": "no_capability_shown"},
        "relationship_state": NOT_BUILT, "object_state": NOT_BUILT, "foreshadowing_used": NOT_BUILT,
        "science_assumptions": [],
        "conflicts_remaining": p0.get("hard", []) + p0.get("soft", []),
        "model_and_prompt_hash": model_and_prompt_hash,
        "tool_receipts": [tl.receipt_id, pressure.receipt_id] + ([power.receipt_id] if power else []),
    }
    verdict = "clean" if pressure.verdict in ("pass", "out_of_domain") else pressure.verdict
    return receipt("xoah_scene_receipt", packet, inputs, verdict, [fields],
                   list(tl.sources) + [p for r in canon for p in r.provenance]
                   + (list(power.sources) if power else []),
                   [r.kind.value for r in rel])
