"""Shannon 1948 Communication System Formalism & Multi-Layer Transport for NouGen.

Mathematical & Architectural Levels:
    - Level A (Shannon Technical): Physical & syntactic reliability across channels
      (Git, MCP, NouGenMsg, IPC). Detects and remediates noise, corruption, loss,
      truncation, duplication, and reordering.
    - Level B (Semantic Invariant): Evaluates meaning, provenance validity,
      and contextual consistency.
    - Level C (Pragmatic / Action): Modulates utility and controls execution gating.

Invariant:
    Shannon channel reliability (Level A) does NOT imply semantic truth (Level B).
    Transport integrity and semantic validation are strictly decoupled.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclasses.dataclass(frozen=True)
class ShannonPacket:
    payload_id: str
    sequence_num: int
    source_node: str
    target_node: str
    schema_version: str
    timestamp_utc: float
    data: Dict[str, Any]
    checksum: str

    @classmethod
    def create(cls, payload_id: str, seq: int, src: str, dst: str, data: Dict[str, Any],
               version: str = "1.0.0") -> ShannonPacket:
        now = time.time()
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        cksum = hashlib.sha256(f"{payload_id}:{seq}:{src}:{dst}:{serialized}".encode("utf-8")).hexdigest()
        return cls(
            payload_id=payload_id,
            sequence_num=seq,
            source_node=src,
            target_node=dst,
            schema_version=version,
            timestamp_utc=now,
            data=data,
            checksum=cksum,
        )

    def verify_integrity(self) -> bool:
        """Level A check: bit/byte integrity and uncorrupted delivery."""
        serialized = json.dumps(self.data, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(f"{self.payload_id}:{self.sequence_num}:{self.source_node}:{self.target_node}:{serialized}".encode("utf-8")).hexdigest()
        return expected == self.checksum

    def to_envelope(self) -> str:
        return json.dumps(dataclasses.asdict(self))


class ShannonReceiver:
    """Channel receiver with noise, loss, duplication, and reordering fault tolerance."""

    def __init__(self, max_stale_seconds: float = 3600.0):
        self.max_stale_seconds = max_stale_seconds
        self.seen_payload_ids: Set[str] = set()
        self.highest_seq_by_node: Dict[str, int] = {}

    def ingest(self, raw_json: str) -> Dict[str, Any]:
        """Process incoming raw string from noisy channel. Returns structured status."""
        # 1. Truncation / JSON parse check
        try:
            d = json.loads(raw_json)
            if not isinstance(d, dict):
                return {"status": "rejected", "fault": "invalid_structure", "level": "Level_A"}
        except (json.JSONDecodeError, ValueError) as exc:
            return {"status": "rejected", "fault": "truncated_json", "error": str(exc), "level": "Level_A"}

        # Required fields check
        req = ["payload_id", "sequence_num", "source_node", "target_node", "schema_version", "data", "checksum"]
        if any(k not in d for k in req):
            return {"status": "rejected", "fault": "schema_missing_fields", "level": "Level_A"}

        packet = ShannonPacket(
            payload_id=d["payload_id"],
            sequence_num=d["sequence_num"],
            source_node=d["source_node"],
            target_node=d["target_node"],
            schema_version=d["schema_version"],
            timestamp_utc=d.get("timestamp_utc", 0.0),
            data=d["data"],
            checksum=d["checksum"],
        )

        # 2. Corruption check (Level A)
        if not packet.verify_integrity():
            return {"status": "rejected", "fault": "checksum_mismatch", "level": "Level_A"}

        # 3. Duplication check (Level A)
        if packet.payload_id in self.seen_payload_ids:
            return {"status": "deduplicated", "fault": "duplicate_payload", "payload_id": packet.payload_id, "level": "Level_A"}

        # 4. Stale state check (Level A / Level B boundary)
        now = time.time()
        if packet.timestamp_utc > 0 and (now - packet.timestamp_utc) > self.max_stale_seconds:
            return {"status": "rejected", "fault": "stale_timestamp", "age": now - packet.timestamp_utc, "level": "Level_B"}

        # 5. Reordering check
        last_seq = self.highest_seq_by_node.get(packet.source_node, 0)
        is_reordered = packet.sequence_num <= last_seq and last_seq > 0
        self.highest_seq_by_node[packet.source_node] = max(last_seq, packet.sequence_num)
        self.seen_payload_ids.add(packet.payload_id)

        # 6. Schema drift check (preserves unknown fields cleanly)
        unknown_fields = {k: v for k, v in d.items() if k not in req and k != "timestamp_utc"}

        return {
            "status": "accepted",
            "level_a_verified": True,
            "reordered": is_reordered,
            "schema_version": packet.schema_version,
            "unknown_fields_preserved": unknown_fields,
            "packet": dataclasses.asdict(packet),
        }
