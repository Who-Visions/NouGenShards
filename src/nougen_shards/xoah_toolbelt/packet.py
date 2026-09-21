"""Load a CanonPacket from the private vault export named by NOUGEN_XOAH_PACKET (JSON)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, Optional

from .types import (CanonKind, CanonPacket, CanonRecord, Capability, Provenance, Scene, TimelineEntry)

PACKET_ENV = "NOUGEN_XOAH_PACKET"


class PacketUnavailable(RuntimeError):
    """No canon packet: callers report missing context and never guess."""


def _prov(items):
    return tuple(Provenance(p.get("shard_id"), str(p.get("db", "")), str(p.get("node", "")),
                            str(p.get("phrase", ""))) for p in (items or ()))


def packet_from_dict(d: Mapping) -> CanonPacket:
    def rec(x):
        return CanonRecord(x["id"], CanonKind(x["kind"]), x.get("statement", ""), tuple(x.get("topics", ())),
                           tuple(x.get("contradicts", ())), tuple(x.get("routes", ())),
                           tuple(int(v) for v in x.get("volumes", ())), _prov(x.get("provenance")))
    return CanonPacket(
        revision=str(d.get("revision", "unversioned")),
        records=tuple(rec(x) for x in d.get("records", ())),
        scenes=tuple(Scene(s["scene_id"], s["route"], s.get("variant", ""), int(s["volume"]),
                           int(s["order"]), s.get("text", "")) for s in d.get("scenes", ())),
        timeline=tuple(TimelineEntry(t["fact_id"], t["route"], int(t["order"]), t.get("statement", ""),
                                     tuple(t.get("patterns", ())), _prov(t.get("provenance")))
                       for t in d.get("timeline", ())),
        capabilities=tuple(Capability(c["id"], int(c["level"]), c.get("statement", ""),
                                      tuple(c.get("patterns", ())), _prov(c.get("provenance")))
                           for c in d.get("capabilities", ())),
        level_locks={int(v): (int(lo), int(hi)) for v, (lo, hi) in d.get("level_locks", {}).items()},
        level_lock_provenance=_prov(d.get("level_lock_provenance")),
    )


def load_packet(path: Optional[str] = None) -> CanonPacket:
    p = path or os.environ.get(PACKET_ENV)
    if not p:
        raise PacketUnavailable(f"{PACKET_ENV} is not set")
    f = Path(p)
    if not f.is_file():
        raise PacketUnavailable(f"canon packet not found: {f}")
    return packet_from_dict(json.loads(f.read_text(encoding="utf-8")))
