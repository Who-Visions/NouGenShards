"""Load a CanonPacket from a private JSON file (NOUGEN_XOAH_PACKET).

The file lives outside this public repo (default ~/.nougen/canon/). Every
record must carry provenance; a record without it is refused, because a tool
that cannot cite cannot be trusted to have read canon at all."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .types import (CanonKind, CanonPacket, CanonRecord, Capability, Provenance, Scene,
                    TimelineEntry)


def default_path() -> Path:
    return Path(os.environ.get("NOUGEN_XOAH_PACKET")
                or Path.home() / ".nougen" / "canon" / "xoah_packet.json")


def _prov(items) -> tuple:
    out = tuple(Provenance(p.get("shard_id"), p["db"], p["node"], p["phrase"]) for p in items or ())
    return out


def _need(obj: Dict[str, Any], what: str) -> tuple:
    prov = _prov(obj.get("provenance"))
    if not prov:
        raise ValueError(f"{what} {obj.get('id') or obj.get('fact_id')!r} has no provenance")
    return prov


def from_dict(d: Dict[str, Any]) -> CanonPacket:
    return CanonPacket(
        revision=str(d["revision"]),
        records=tuple(CanonRecord(r["id"], CanonKind(r["kind"]), r["statement"],
                                  tuple(r.get("topics", ())), tuple(r.get("contradicts", ())),
                                  tuple(r.get("routes", ())), tuple(r.get("volumes", ())),
                                  _need(r, "record")) for r in d.get("records", ())),
        scenes=tuple(Scene(s["scene_id"], s["route"], s.get("variant", ""), int(s["volume"]),
                           int(s["order"]), s.get("text", "")) for s in d.get("scenes", ())),
        timeline=tuple(TimelineEntry(t["fact_id"], t["route"], int(t["order"]), t["statement"],
                                     tuple(t.get("patterns", ())), _need(t, "timeline fact"))
                       for t in d.get("timeline", ())),
        capabilities=tuple(Capability(c["id"], int(c["level"]), c["statement"],
                                      tuple(c.get("patterns", ())), _need(c, "capability"))
                           for c in d.get("capabilities", ())),
        level_locks={int(k): (int(v[0]), int(v[1])) for k, v in (d.get("level_locks") or {}).items()},
        level_lock_provenance=_prov(d.get("level_lock_provenance")),
    )


def load(path: Optional[Path] = None) -> CanonPacket:
    p = Path(path) if path else default_path()
    return from_dict(json.loads(p.read_text(encoding="utf-8")))
