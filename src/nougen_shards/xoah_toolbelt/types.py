"""Shared types for every Xoah Toolbelt tool. Import these; do not redefine."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple


class CanonKind(str, Enum):
    """Five distinct kinds. A tool may never promote one into another --
    canon mutation is a separate, reviewed path."""
    LOCKED = "locked"                # GM-locked canon: authoritative
    CANDIDATE = "candidate"          # proposed, not promoted
    PROCESS_DONOR = "process_donor"  # method borrowed from another work (how)
    SOURCE_DONOR = "source_donor"    # material borrowed from another work (what)
    SPECULATION = "speculation"      # unvetted idea

    @property
    def binding(self) -> bool:
        """Only LOCKED records may produce a hard contradiction."""
        return self is CanonKind.LOCKED


@dataclass(frozen=True)
class Provenance:
    """Where a record came from. Shard ids are NOT unique across vaults, so a
    citation always carries db + node + a title phrase, never an id alone."""
    shard_id: Optional[int]
    db: str
    node: str
    phrase: str

    def cite(self) -> str:
        sid = f"#{self.shard_id}" if self.shard_id is not None else "#?"
        return f"{self.node}/{self.db}{sid} \"{self.phrase[:80]}\""


@dataclass(frozen=True)
class CanonRecord:
    id: str
    kind: CanonKind
    statement: str
    topics: Tuple[str, ...] = ()          # a lock is relevant only when a scene touches these
    contradicts: Tuple[str, ...] = ()     # regexes that contradict the statement
    routes: Tuple[str, ...] = ()          # empty = every route
    volumes: Tuple[int, ...] = ()         # empty = every volume
    provenance: Tuple[Provenance, ...] = ()


@dataclass(frozen=True)
class Scene:
    scene_id: str
    route: str
    variant: str
    volume: int
    order: int                            # position on the route's timeline
    text: str = ""


@dataclass(frozen=True)
class TimelineEntry:
    """A fact becomes known to the character at ``order`` on ``route``."""
    fact_id: str
    route: str
    order: int
    statement: str
    patterns: Tuple[str, ...] = ()       # how a scene would show she knows it
    provenance: Tuple[Provenance, ...] = ()


@dataclass(frozen=True)
class Capability:
    id: str
    level: int
    statement: str
    patterns: Tuple[str, ...] = ()
    provenance: Tuple[Provenance, ...] = ()


@dataclass(frozen=True)
class CanonPacket:
    """Everything a tool may consult. Built from the private vault; never
    committed to this repo. ``revision`` pins receipts to a canon snapshot."""
    revision: str
    records: Tuple[CanonRecord, ...] = ()
    scenes: Tuple[Scene, ...] = ()
    timeline: Tuple[TimelineEntry, ...] = ()
    capabilities: Tuple[Capability, ...] = ()
    level_locks: Mapping[int, Tuple[int, int]] = field(default_factory=dict)  # volume -> (min, max)
    level_lock_provenance: Tuple[Provenance, ...] = ()

    def scene(self, scene_id: str) -> Optional[Scene]:
        return next((s for s in self.scenes if s.scene_id == scene_id), None)


@dataclass(frozen=True)
class ToolReceipt:
    """Every tool returns one. ``receipt_id`` is sha256 of the canonical JSON
    of everything else, so identical inputs + packet revision reproduce it."""
    tool: str
    packet_revision: str
    inputs: Mapping[str, Any]
    verdict: str
    findings: Tuple[Mapping[str, Any], ...] = ()
    sources: Tuple[Provenance, ...] = ()
    kinds_used: Tuple[str, ...] = ()
    receipt_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("receipt_id")
        return d

    def sealed(self) -> "ToolReceipt":
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        rid = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return ToolReceipt(**{**asdict_shallow(self), "receipt_id": rid})


def asdict_shallow(obj: Any) -> Dict[str, Any]:
    return {f: getattr(obj, f) for f in obj.__dataclass_fields__}


def receipt(tool: str, packet: CanonPacket, inputs: Mapping[str, Any], verdict: str,
            findings=(), sources=(), kinds=()) -> ToolReceipt:
    uniq = tuple(sorted(set(sources), key=lambda p: (p.node, p.db, p.shard_id or -1, p.phrase)))
    return ToolReceipt(tool, packet.revision, dict(inputs), verdict, tuple(findings), uniq,
                       tuple(sorted(set(kinds)))).sealed()
