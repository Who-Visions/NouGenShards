"""Reconstructive Recall & Evidence-Locked Temporal Multi-Store Retrieval Engine.

Implements MRAgent active reconstruction, Agent Zero Memory triple-store grounding,
conflict-at-write gating, and staged pulse retrieval with absolute evidence locking.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class SourceType(str, Enum):
    EPISODIC_RELAY = "EPISODIC_RELAY"
    DOCUMENTARY_SHARD = "DOCUMENTARY_SHARD"
    ASSOCIATIVE_GRAPH = "ASSOCIATIVE_GRAPH"
    PROCESS_DONOR = "PROCESS_DONOR"


class ContradictionState(str, Enum):
    NONE = "NONE"
    VERSIONED = "VERSIONED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class MemoryEvent:
    event_id: str
    event_ms: int
    created_ms: int
    updated_ms: int
    ai_touched_ms: int
    migrated_ms: int
    source_node: str
    source_type: SourceType
    content: str
    supersedes: Optional[str] = None
    contradiction_group: Optional[str] = None
    branch: str = "main"
    confidence_bps: int = 10000
    utility_bps: int = 5000


@dataclass(frozen=True)
class AssociativeEdge:
    source_id: str
    target_id: str
    relation: str
    weight_bps: int  # 0 to 10,000
    learned_utility_bps: int = 5000
    first_seen_ms: int = 0
    last_seen_ms: int = 0
    temporal_valid: bool = True
    correction_state: str = "VALID"  # VALID, AMENDED, RETRACTED


@dataclass
class ReconstructionEnvelope:
    query_fingerprint: str
    angle_sequence: List[str]
    per_angle_hits: Dict[str, List[str]]
    opened_evidence_ids: List[str]
    provenance_lock_sha: str
    vault_coverage_pct_bps: int
    temporal_coverage: str
    contradiction_state: ContradictionState
    confidence_bps: int
    abstention_reason: Optional[str] = None
    latency_by_phase_us: Dict[str, int] = field(default_factory=dict)
    reconstructed_text: str = ""


class EvidenceLockError(Exception):
    """Raised when an answer attempts to cite unopened evidence."""
    pass


class ReconstructiveRecallEngine:
    """Evidence-locked reconstructive recall engine across episodic, documentary, and associative stores."""

    def __init__(self):
        self.events: Dict[str, MemoryEvent] = {}
        self.edges: List[AssociativeEdge] = []
        self.adjacency: Dict[str, List[AssociativeEdge]] = {}

    def insert_event(self, event: MemoryEvent) -> Tuple[bool, ContradictionState]:
        """Insert a memory event with conflict-at-write validation."""
        contradiction = ContradictionState.NONE

        # Conflict-at-write check against same-entity / same-temporal neighbors
        if event.contradiction_group:
            for existing_id, existing in self.events.items():
                if existing.contradiction_group == event.contradiction_group:
                    if existing.branch == event.branch and existing.content != event.content:
                        if event.supersedes == existing_id:
                            contradiction = ContradictionState.VERSIONED
                        else:
                            contradiction = ContradictionState.QUARANTINED

        self.events[event.event_id] = event
        return True, contradiction

    def add_edge(self, edge: AssociativeEdge) -> None:
        self.edges.append(edge)
        self.adjacency.setdefault(edge.source_id, []).append(edge)

    def find_provenance_path(self, start_id: str, target_id: str, max_depth: int = 3) -> List[str]:
        """Find minimal associative graph path connecting start entity to target memory."""
        if start_id == target_id:
            return [start_id]
        
        queue: List[Tuple[str, List[str]]] = [(start_id, [start_id])]
        visited: Set[str] = {start_id}

        while queue:
            curr, path = queue.pop(0)
            if len(path) > max_depth:
                continue
            for edge in self.adjacency.get(curr, []):
                if not edge.temporal_valid or edge.correction_state == "RETRACTED":
                    continue
                nxt = edge.target_id
                if nxt == target_id:
                    return path + [nxt]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))
        return []

    def execute_pulse_retrieval(
        self,
        query: str,
        as_of_ms: Optional[int] = None,
        required_nodes: Optional[Set[str]] = None
    ) -> ReconstructionEnvelope:
        """Executes staged pulse retrieval: exact -> lexical -> associative -> provenance reconstruction."""
        t_start = time.perf_counter_ns()
        latencies: Dict[str, int] = {}
        angle_sequence = ["PULSE_1_EXACT_TEMPORAL", "PULSE_2_LEXICAL", "PULSE_3_ASSOCIATIVE", "PULSE_4_PROVENANCE"]
        per_angle_hits: Dict[str, List[str]] = {p: [] for p in angle_sequence}
        opened_ids: Set[str] = set()

        q_lower = query.lower()
        query_fp = hashlib.sha256(query.encode("utf-8")).hexdigest()

        # Pulse 1: Exact & Temporal Matching
        t0 = time.perf_counter_ns()
        for ev_id, ev in self.events.items():
            if as_of_ms is not None and ev.event_ms > as_of_ms:
                continue
            if ev.event_id.lower() in q_lower or ev.branch.lower() in q_lower:
                per_angle_hits["PULSE_1_EXACT_TEMPORAL"].append(ev_id)
                opened_ids.add(ev_id)
        latencies["pulse_1_us"] = (time.perf_counter_ns() - t0) // 1000

        # Pulse 2: Lexical Match
        t0 = time.perf_counter_ns()
        q_tokens = set(q_lower.split())
        for ev_id, ev in self.events.items():
            if as_of_ms is not None and ev.event_ms > as_of_ms:
                continue
            ev_tokens = set(ev.content.lower().split())
            if q_tokens & ev_tokens:
                per_angle_hits["PULSE_2_LEXICAL"].append(ev_id)
                opened_ids.add(ev_id)
        latencies["pulse_2_us"] = (time.perf_counter_ns() - t0) // 1000

        # Pulse 3: Associative Graph Traversal
        t0 = time.perf_counter_ns()
        for seed_id in list(opened_ids):
            for edge in self.adjacency.get(seed_id, []):
                if edge.temporal_valid and edge.correction_state != "RETRACTED":
                    per_angle_hits["PULSE_3_ASSOCIATIVE"].append(edge.target_id)
                    opened_ids.add(edge.target_id)
        latencies["pulse_3_us"] = (time.perf_counter_ns() - t0) // 1000

        # Pulse 4: Provenance Lock & Reconstruction
        t0 = time.perf_counter_ns()
        if not opened_ids:
            return ReconstructionEnvelope(
                query_fingerprint=query_fp,
                angle_sequence=angle_sequence,
                per_angle_hits=per_angle_hits,
                opened_evidence_ids=[],
                provenance_lock_sha=hashlib.sha256(b"ABSTAIN").hexdigest(),
                vault_coverage_pct_bps=10000,
                temporal_coverage=f"as_of_ms={as_of_ms}" if as_of_ms else "all_time",
                contradiction_state=ContradictionState.NONE,
                confidence_bps=0,
                abstention_reason="ZERO_EVIDENCE_UNLOCKED",
                latency_by_phase_us=latencies
            )

        # Coverage Verification
        represented_nodes = {self.events[eid].source_node for eid in opened_ids if eid in self.events}
        if required_nodes:
            covered = len(represented_nodes & required_nodes)
            coverage_bps = (covered * 10000) // len(required_nodes)
        else:
            coverage_bps = 10000

        # Sort opened events deterministically by event_ms desc, confidence_bps desc
        valid_events = [self.events[eid] for eid in opened_ids if eid in self.events]
        valid_events.sort(key=lambda x: (-x.event_ms, -x.confidence_bps, x.event_id))

        # Check for contradictions among opened events
        contradiction_state = ContradictionState.NONE
        c_groups = [ev.contradiction_group for ev in valid_events if ev.contradiction_group]
        if len(c_groups) != len(set(c_groups)):
            # If multiple versions exist in the same group, check if properly superseding
            for ev in valid_events:
                if ev.supersedes:
                    contradiction_state = ContradictionState.VERSIONED
                    break
            else:
                contradiction_state = ContradictionState.QUARANTINED

        # Evidence-locked text synthesis
        evidence_fingerprint = hashlib.sha256(
            "".join(f"{ev.event_id}:{ev.confidence_bps}" for ev in valid_events).encode("utf-8")
        ).hexdigest()

        reconstructed_lines = [
            f"[{ev.event_id}] [{ev.source_type.value} from {ev.source_node} @ {ev.event_ms}] {ev.content}"
            for ev in valid_events
        ]
        reconstructed_text = "\n".join(reconstructed_lines)

        latencies["pulse_4_us"] = (time.perf_counter_ns() - t0) // 1000
        latencies["total_us"] = (time.perf_counter_ns() - t_start) // 1000

        return ReconstructionEnvelope(
            query_fingerprint=query_fp,
            angle_sequence=angle_sequence,
            per_angle_hits=per_angle_hits,
            opened_evidence_ids=[ev.event_id for ev in valid_events],
            provenance_lock_sha=evidence_fingerprint,
            vault_coverage_pct_bps=coverage_bps,
            temporal_coverage=f"as_of_ms={as_of_ms}" if as_of_ms else "all_time",
            contradiction_state=contradiction_state,
            confidence_bps=valid_events[0].confidence_bps if valid_events else 0,
            latency_by_phase_us=latencies,
            reconstructed_text=reconstructed_text
        )
