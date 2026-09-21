"""Slice-1 Xoah tools: timeline_trace, power_ceiling, scene_pressure_test, scene_receipt.

Pure, deterministic functions over a ``CanonPacket`` (see types.py). No model calls,
no canon writes. Every tool returns a sealed ``ToolReceipt``.
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Mapping, Optional, Tuple

from .types import CanonKind, CanonPacket, CanonRecord, Provenance, ToolReceipt, receipt

VERSION = "xoah-toolbelt-slice1-0.1"


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _hit(patterns, text: str) -> Optional[str]:
    for p in patterns:
        try:
            m = re.search(p, text, re.I)
        except re.error:
            continue
        if m:
            return m.group(0)
    return None


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _scene_or_missing(packet: CanonPacket, scene_id: str, tool: str, inputs: Mapping):
    sc = packet.scene(scene_id)
    if sc is None:
        return None, receipt(tool, packet, inputs, "insufficient_context",
                             findings=[{"check": "missing_scene", "missing": [f"scene:{scene_id}"]}])
    return sc, None


# ---------------------------------------------------------------- timeline ---
def _split_timeline(packet: CanonPacket, route: str, order: int):
    before, now, future = [], [], []
    for e in packet.timeline:
        if e.route != route:
            continue
        (before if e.order < order else now if e.order == order else future).append(e)
    return before, now, future


def timeline_trace(packet: CanonPacket, scene_id: str) -> ToolReceipt:
    inputs = {"scene_id": scene_id}
    sc, miss = _scene_or_missing(packet, scene_id, "xoah_timeline_trace", inputs)
    if miss:
        return miss
    before, now, future = _split_timeline(packet, sc.route, sc.order)
    finding = {"check": "timeline", "route": sc.route, "variant": sc.variant, "order": sc.order,
               "knowledge_before": sorted(e.fact_id for e in before),
               "knowledge_after": sorted(e.fact_id for e in before + now),
               "forbidden_future_knowledge": sorted(e.fact_id for e in future)}
    src = tuple(p for e in before + now for p in e.provenance)
    return receipt("xoah_timeline_trace", packet, inputs, "ok", [finding], src, [CanonKind.LOCKED.value])


# ------------------------------------------------------------- power ceiling ---
def _cap_for(packet: CanonPacket, action: str):
    a = action.lower().strip()
    for c in packet.capabilities:
        if c.id.lower() == a:
            return c
    hits = [c for c in packet.capabilities if _hit(c.patterns, action)]
    return max(hits, key=lambda c: c.level) if hits else None


def _ceiling_check(packet: CanonPacket, volume: int, action: str) -> Dict:
    lock = packet.level_locks.get(volume)
    base = {"check": "power_ceiling", "action": action, "volume": volume}
    if lock is None:
        return {**base, "status": "no_ceiling_defined", "allowed": False}
    cap = _cap_for(packet, action)
    if cap is None:
        return {**base, "status": "unknown_action", "allowed": None, "ceiling": list(lock)}
    if cap.level <= lock[1]:
        return {**base, "status": "ok", "allowed": True, "level": cap.level, "ceiling": list(lock)}
    legal = [c for c in packet.capabilities if c.level <= lock[1] and c.id != cap.id]
    best = max(legal, key=lambda c: c.level) if legal else None
    return {**base, "status": "over_ceiling", "allowed": False, "level": cap.level, "ceiling": list(lock),
            "nearest_legal_expression": best.id if best else None}


def power_ceiling(packet: CanonPacket, requested_action: str, scene_id: Optional[str] = None,
                  volume: Optional[int] = None) -> ToolReceipt:
    inputs = {"requested_action": requested_action, "scene_id": scene_id, "volume": volume}
    sc = packet.scene(scene_id) if scene_id else None
    vol = sc.volume if sc else volume
    if vol is None:
        return receipt("xoah_power_ceiling", packet, inputs, "insufficient_context",
                       findings=[{"check": "missing_volume", "missing": ["scene or volume"]}])
    f = _ceiling_check(packet, vol, requested_action)
    verdict = {"ok": "allowed", "over_ceiling": "disallowed"}.get(f["status"], f["status"])
    return receipt("xoah_power_ceiling", packet, inputs, verdict, [f],
                   packet.level_lock_provenance, [CanonKind.LOCKED.value])


# ------------------------------------------------------------ pressure test ---
def _record_applies(r: CanonRecord, sc) -> bool:
    return (not r.routes or sc.route in r.routes) and (not r.volumes or sc.volume in r.volumes)


def _flag(check, severity, ref, note, repair="") -> Dict:
    return {"check": check, "severity": severity, "ref": ref, "note": note, "repair": repair}


def scene_pressure_test(packet: CanonPacket, scene_id: str, text: str,
                        actions: Tuple[str, ...] = (), refs: Tuple[str, ...] = ()) -> ToolReceipt:
    inputs = {"scene_id": scene_id, "text_hash": _sha(text), "actions": list(actions), "refs": list(refs)}
    sc, miss = _scene_or_missing(packet, scene_id, "xoah_scene_pressure_test", inputs)
    if miss:
        return miss
    toks = _tokens(text)
    before, now, future = _split_timeline(packet, sc.route, sc.order)
    flags: List[Dict] = []
    suppressed: List[Dict] = []
    checked: List[str] = []
    sources: List[Provenance] = list(packet.level_lock_provenance)
    kinds = {CanonKind.LOCKED.value}

    for e in future:                                    # 1. omniscience
        why = "cited before Xoah learns it" if e.fact_id in refs else _hit(e.patterns, text)
        if why:
            flags.append(_flag("forbidden_future_knowledge", "hard", e.fact_id,
                               f"scene shows knowledge learned at order {e.order} > {sc.order}: {why}",
                               "cut the disclosure or move the scene later"))
            sources.extend(e.provenance)
    for a in actions:                                   # 2. power ceiling
        f = _ceiling_check(packet, sc.volume, a)
        if f["status"] == "over_ceiling":
            alt = f["nearest_legal_expression"]
            flags.append(_flag("power_ceiling", "hard", a,
                               f"level {f['level']} > max {f['ceiling'][1]} for volume {sc.volume}",
                               f"use {alt!r}" if alt else "cut the action"))
        elif f["status"] in ("unknown_action", "no_ceiling_defined"):
            flags.append(_flag("power_ceiling", "soft", a, f["status"]))
    for r in packet.records:                            # 3. canon locks, relevance-gated
        if not r.contradicts or not _record_applies(r, sc):
            continue
        matched = _hit(r.contradicts, text)
        if r.kind.binding:
            checked.append(r.id)
        if not matched:
            continue
        if r.topics and not (set(t.lower() for t in r.topics) & toks):
            suppressed.append({"record": r.id, "reason": "scene does not touch this record's topics",
                               "matched": matched})            # the false-positive fix
            continue
        kinds.add(r.kind.value)
        sources.extend(r.provenance)
        flags.append(_flag("canon_lock" if r.kind.binding else "non_binding_conflict",
                           "hard" if r.kind.binding else "soft", r.id,
                           f"contradicts {r.kind.value} record: {matched!r}",
                           "rewrite to agree with the record" if r.kind.binding else "review before promotion"))
    by_id = {r.id: r for r in packet.records}
    for ref in refs:                                    # 4. source discipline
        rec = by_id.get(ref)
        if rec is not None:
            kinds.add(rec.kind.value)
            sources.extend(rec.provenance)
            if not rec.kind.binding:
                flags.append(_flag("non_locked_source", "soft", ref, f"relies on a {rec.kind.value} record"))
        elif not any(e.fact_id == ref for e in packet.timeline):
            flags.append(_flag("unknown_ref", "soft", ref, "reference not found in the canon packet"))
    hard = any(f["severity"] == "hard" for f in flags)
    verdict = "hard_contradiction" if hard else "soft_flags" if flags else "pass"
    summary = {"check": "summary", "route": sc.route, "variant": sc.variant, "order": sc.order,
               "knowledge_before": sorted(e.fact_id for e in before),
               "forbidden_future_knowledge": sorted(e.fact_id for e in future),
               "checked_locks": sorted(checked), "suppressed_irrelevant": suppressed}
    return receipt("xoah_scene_pressure_test", packet, inputs, verdict, [summary] + flags, sources, kinds)


# ------------------------------------------------------------ scene receipt ---
def scene_receipt(packet: CanonPacket, scene_id: str, text: str, actions: Tuple[str, ...] = (),
                  refs: Tuple[str, ...] = (), model_and_prompt: str = "") -> ToolReceipt:
    """Run the slice-1 chain on one scene and emit the machine-readable receipt."""
    pressure = scene_pressure_test(packet, scene_id, text, actions, refs)
    inputs = {"scene_id": scene_id, "text_hash": _sha(text), "actions": list(actions), "refs": list(refs),
              "model_and_prompt_hash": _sha(model_and_prompt)}
    if pressure.verdict == "insufficient_context":
        return receipt("xoah_scene_receipt", packet, inputs, "insufficient_context", pressure.findings)
    summary = pressure.findings[0]
    flags = pressure.findings[1:]
    by_id = {r.id: r for r in packet.records}
    used = set(refs) | set(summary["checked_locks"])
    tiers = {k.value: sorted(i for i in used if i in by_id and by_id[i].kind is k) for k in CanonKind}
    state = {
        "check": "scene_state", "scene_id": scene_id, "route": summary["route"], "variant": summary["variant"],
        "canon_sources": tiers["locked"], "candidate_sources": tiers["candidate"],
        "donor_sources": sorted(tiers["process_donor"] + tiers["source_donor"]),
        "speculation_sources": tiers["speculation"],
        "timeline_state": {"knowledge_before": summary["knowledge_before"],
                           "forbidden_future_knowledge": summary["forbidden_future_knowledge"]},
        "power_state": [dict(_ceiling_check(packet, packet.scene(scene_id).volume, a)) for a in actions],
        "suppressed_irrelevant": summary["suppressed_irrelevant"],
        "not_evaluated": ["relationship_state", "object_state", "foreshadowing_used", "science_assumptions"],
        "conflicts_remaining": [f for f in flags if f["severity"] == "hard"],
        "soft_flags": [f for f in flags if f["severity"] == "soft"],
        "tool_version": VERSION,
    }
    return receipt("xoah_scene_receipt", packet, inputs, pressure.verdict, [state],
                   pressure.sources, pressure.kinds_used)
