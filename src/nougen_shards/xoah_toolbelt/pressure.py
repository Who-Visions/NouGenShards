"""xoah_scene_pressure_test: attack a scene from canon, knowledge and power.

The relevance gate is the point. A lock is consulted only when the scene is
in its scope (route, volume) AND touches one of its topics. The old ask_xoah
behaviour matched a lock's contradiction patterns against ANY text, so an
engineering question containing "fix" or "survives" drew a FACT_CONFLICT from
an unrelated lock. Here a lock the scene never touches cannot fire.
"""
from __future__ import annotations

import re
from typing import Optional

from .power import power_ceiling
from .timeline import _hits, timeline_trace
from .types import CanonPacket, CanonRecord, Scene, ToolReceipt, receipt

_ENGINEERING = re.compile(
    r"\b(pull request|PR\s*#?\d+|pytest|unit test|stack ?trace|traceback|refactor|deploy|"
    r"endpoint|api|repo|branch|commit|merge|ci|lint|function|module|schema|sql|json|regex)\b|"
    r"```|def \w+\(|class \w+|import \w+", re.I)


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9][a-z0-9'-]+", text.lower()))


def relevant(rec: CanonRecord, scene: Scene, text: str) -> bool:
    if rec.routes and scene.route not in rec.routes:
        return False
    if rec.volumes and scene.volume not in rec.volumes:
        return False
    toks, low = _tokens(text), text.lower()
    return any((t.lower() in low) if " " in t else (t.lower() in toks) for t in rec.topics)


def _scene_for(packet: CanonPacket, scene_id: Optional[str], text: str,
               route: str, volume: int) -> Scene:
    return packet.scene(scene_id) if scene_id and packet.scene(scene_id) else \
        Scene(scene_id or "adhoc", route, "", volume, 10 ** 9, text)


def scene_pressure_test(packet: CanonPacket, scene_id: Optional[str] = None,
                        text: Optional[str] = None, *, route: str = "", volume: int = 0) -> ToolReceipt:
    scene = _scene_for(packet, scene_id, text or "", route, volume)
    body = scene.text if text is None else text
    inputs = {"scene_id": scene.scene_id, "route": scene.route, "volume": scene.volume,
              "text_given": text is not None}
    rel = [r for r in packet.records if relevant(r, scene, body)]
    if not rel and _ENGINEERING.search(body):
        return receipt("xoah_scene_pressure_test", packet, inputs, "out_of_domain",
                       [{"reason": "engineering text touching no canon topic; no lock consulted",
                         "skipped_irrelevant": len(packet.records)}])
    hard, soft, sources, kinds = [], [], [], []
    for r in rel:
        m = _hits(r.contradicts, body)
        if not m:
            continue
        item = {"record": r.id, "kind": r.kind.value, "because": r.statement, "matched": m,
                "sources": [p.cite() for p in r.provenance]}
        (hard if r.kind.binding else soft).append(item)
        sources += r.provenance
        kinds.append(r.kind.value)
    if packet.scene(scene.scene_id):
        tl = timeline_trace(packet, scene.scene_id, body)
        for v in tl.findings[0].get("violations", []) if tl.findings else []:
            hard.append({"check": "timeline", **v})
        sources += tl.sources
    for c in packet.capabilities:
        if _hits(c.patterns, body):
            pc = power_ceiling(packet, scene.scene_id, body) if packet.scene(scene.scene_id) else None
            if pc and pc.verdict == "disallowed":
                hard.append({"check": "power", **pc.findings[0]})
                sources += pc.sources
            break
    repairs = [f"rephrase or cut the span matching {h.get('matched')} ({h.get('record') or h.get('check')})"
               for h in hard]
    repairs += ["declare an explicit non-Prime branch if the contradiction is intended"] if hard else []
    verdict = "hard_contradictions" if hard else ("soft_flags" if soft else "pass")
    return receipt("xoah_scene_pressure_test", packet, inputs, verdict,
                   [{"hard": hard, "soft": soft, "repairs": repairs,
                     "relevant_records": [r.id for r in rel],
                     "skipped_irrelevant": len(packet.records) - len(rel)}],
                   sources + [p for r in rel for p in r.provenance],
                   kinds + [r.kind.value for r in rel])
