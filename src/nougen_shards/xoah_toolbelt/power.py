"""xoah_power_ceiling: scene-appropriate capability limits (e.g. Vol 1 = L1-L3)."""
from __future__ import annotations

from .timeline import _hits
from .types import CanonKind, CanonPacket, ToolReceipt, receipt


def power_ceiling(packet: CanonPacket, scene_id: str, requested_action: str) -> ToolReceipt:
    inputs = {"scene_id": scene_id, "requested_action": requested_action}
    scene = packet.scene(scene_id)
    if scene is None:
        return receipt("xoah_power_ceiling", packet, inputs, "unknown_scene",
                       [{"missing": "scene", "scene_id": scene_id}])
    lock = packet.level_locks.get(scene.volume)
    if lock is None:
        # No lock recorded is missing context, never permission.
        return receipt("xoah_power_ceiling", packet, inputs, "no_lock_for_volume",
                       [{"missing": "level_lock", "volume": scene.volume}])
    lo, hi = lock
    matched = [c for c in packet.capabilities if _hits(c.patterns, requested_action)]
    allowed = [c for c in matched if c.level <= hi]
    disallowed = [c for c in matched if c.level > hi]
    legal = sorted((c for c in packet.capabilities if c.level <= hi), key=lambda c: (-c.level, c.id))
    if not matched:
        verdict = "unclassified"  # the action names no known capability: say so, don't pass it
    else:
        verdict = "disallowed" if disallowed else "allowed"
    findings = [{
        "volume": scene.volume, "level_lock": [lo, hi],
        "allowed": [{"id": c.id, "level": c.level} for c in allowed],
        "disallowed": [{"id": c.id, "level": c.level, "over_by": c.level - hi} for c in disallowed],
        "nearest_legal_expression": [{"id": c.id, "level": c.level, "statement": c.statement}
                                     for c in legal[:3]] if disallowed or not matched else [],
    }]
    used = list(packet.level_lock_provenance) + [p for c in matched for p in c.provenance]
    return receipt("xoah_power_ceiling", packet, inputs, verdict, findings, used,
                   [CanonKind.LOCKED.value])
