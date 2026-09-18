"""Reconstructive Recall & Evidence-Locked Temporal Multi-Store Retrieval Engine.

Implements MRAgent active reconstruction, Agent Zero Memory triple-store grounding,
conflict-at-write gating, and staged pulse retrieval with absolute evidence locking.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


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
    evidence_pointer: Optional[str] = None
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
    evidence_manifest: Dict[str, str]
    provenance_lock_sha: str
    vault_coverage_pct_bps: int
    scanned_stores: List[str]
    store_coverage_bps: int
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

    def __init__(self, available_stores: Optional[Set[SourceType]] = None):
        self.events: Dict[str, MemoryEvent] = {}
        self.quarantined_events: Dict[str, MemoryEvent] = {}
        self.edges: List[AssociativeEdge] = []
        self.adjacency: Dict[str, List[AssociativeEdge]] = {}
        self.available_stores = set(SourceType) if available_stores is None else set(available_stores)

    def insert_event(self, event: MemoryEvent) -> Tuple[bool, ContradictionState]:
        """Insert a memory event with conflict-at-write validation."""
        prior_id = event.event_id
        if prior_id in self.events:
            if self.events[prior_id] == event:
                return True, ContradictionState.NONE
            self.quarantined_events[prior_id] = event
            return False, ContradictionState.QUARANTINED
        if prior_id in self.quarantined_events:
            return False, ContradictionState.QUARANTINED

        contradiction = ContradictionState.NONE
        if event.supersedes:
            predecessor = self.events.get(event.supersedes)
            valid_supersession = (
                predecessor is not None
                and event.contradiction_group is not None
                and predecessor.contradiction_group == event.contradiction_group
                and predecessor.branch == event.branch
                and event.event_ms >= predecessor.event_ms
                and event.content != predecessor.content
            )
            if not valid_supersession:
                self.quarantined_events[prior_id] = event
                return True, ContradictionState.QUARANTINED
            contradiction = ContradictionState.VERSIONED
        elif event.contradiction_group:
            conflicting = any(
                existing.contradiction_group == event.contradiction_group
                and existing.branch == event.branch
                and existing.content != event.content
                for existing in self.events.values()
            )
            if conflicting:
                self.quarantined_events[prior_id] = event
                return True, ContradictionState.QUARANTINED

        self.events[prior_id] = event
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

    @staticmethod
    def _event_digest(event: MemoryEvent) -> str:
        payload = asdict(event)
        payload["source_type"] = event.source_type.value
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _lock_digest(manifest: Dict[str, str]) -> str:
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify_evidence_lock(
        self, envelope: ReconstructionEnvelope, cited_ids: Optional[Set[str]] = None
    ) -> bool:
        """Reject citations outside the opened set or whose source changed after retrieval."""
        cited = set(envelope.opened_evidence_ids) if cited_ids is None else set(cited_ids)
        opened = set(envelope.opened_evidence_ids)
        if not cited.issubset(opened) or set(envelope.evidence_manifest) != opened:
            raise EvidenceLockError("citation is not present in the opened evidence manifest")
        if any(
            evidence_id not in self.events
            or self._event_digest(self.events[evidence_id]) != envelope.evidence_manifest[evidence_id]
            for evidence_id in opened
        ):
            raise EvidenceLockError("opened evidence changed after the reconstruction lock was issued")
        if self._lock_digest(envelope.evidence_manifest) != envelope.provenance_lock_sha:
            raise EvidenceLockError("provenance lock does not match its evidence manifest")
        return True

    def execute_pulse_retrieval(
        self,
        query: str,
        as_of_ms: Optional[int] = None,
        required_nodes: Optional[Set[str]] = None,
        known_as_of_ms: Optional[int] = None,
    ) -> ReconstructionEnvelope:
        """Executes staged pulse retrieval: exact -> lexical -> associative -> provenance reconstruction."""
        t_start = time.perf_counter_ns()
        latencies: Dict[str, int] = {}
        angle_sequence = ["PULSE_1_EXACT_TEMPORAL", "PULSE_2_LEXICAL", "PULSE_3_ASSOCIATIVE", "PULSE_4_PROVENANCE"]
        per_angle_hits: Dict[str, List[str]] = {p: [] for p in angle_sequence}
        opened_ids: Set[str] = set()

        q_lower = query.lower()
        query_fp = hashlib.sha256(query.encode("utf-8")).hexdigest()

        def in_scope(ev: MemoryEvent) -> bool:
            return (
                ev.source_type in self.available_stores
                and (as_of_ms is None or ev.event_ms <= as_of_ms)
                and (known_as_of_ms is None or ev.created_ms <= known_as_of_ms)
            )

        # Pulse 1: Exact & Temporal Matching
        t0 = time.perf_counter_ns()
        for ev_id, ev in self.events.items():
            if not in_scope(ev):
                continue
            if ev.event_id.lower() in q_lower or ev.branch.lower() in q_lower:
                per_angle_hits["PULSE_1_EXACT_TEMPORAL"].append(ev_id)
                opened_ids.add(ev_id)
        latencies["pulse_1_us"] = (time.perf_counter_ns() - t0) // 1000

        # Pulse 2: Lexical Match
        t0 = time.perf_counter_ns()
        q_tokens = set(q_lower.split())
        for ev_id, ev in self.events.items():
            if not in_scope(ev):
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
                edge_in_scope = (
                    edge.temporal_valid
                    and edge.correction_state not in {"RETRACTED", "QUARANTINED"}
                    and (as_of_ms is None or edge.first_seen_ms <= as_of_ms)
                    and (as_of_ms is None or not edge.last_seen_ms or edge.last_seen_ms >= as_of_ms)
                )
                target = self.events.get(edge.target_id)
                if edge_in_scope and target is not None and in_scope(target):
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
                evidence_manifest={},
                provenance_lock_sha=self._lock_digest({}),
                vault_coverage_pct_bps=(
                    (len(self.available_stores) * 10000) // len(SourceType)
                    if not required_nodes else 0
                ),
                scanned_stores=sorted(store.value for store in self.available_stores),
                store_coverage_bps=(len(self.available_stores) * 10000) // len(SourceType),
                temporal_coverage=f"valid_as_of_ms={as_of_ms};known_as_of_ms={known_as_of_ms}",
                contradiction_state=ContradictionState.NONE,
                confidence_bps=0,
                abstention_reason="ZERO_EVIDENCE_UNLOCKED",
                latency_by_phase_us=latencies
            )

        # Coverage reports available local source lanes separately from required-node hit coverage.
        represented_nodes = {self.events[eid].source_node for eid in opened_ids if eid in self.events}
        if required_nodes:
            covered = len(represented_nodes & required_nodes)
            coverage_bps = (covered * 10000) // len(required_nodes)
        else:
            coverage_bps = (len(self.available_stores) * 10000) // len(SourceType)

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
        evidence_manifest = {ev.event_id: self._event_digest(ev) for ev in valid_events}
        evidence_fingerprint = self._lock_digest(evidence_manifest)

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
            evidence_manifest=evidence_manifest,
            provenance_lock_sha=evidence_fingerprint,
            vault_coverage_pct_bps=coverage_bps,
            scanned_stores=sorted(store.value for store in self.available_stores),
            store_coverage_bps=(len(self.available_stores) * 10000) // len(SourceType),
            temporal_coverage=f"valid_as_of_ms={as_of_ms};known_as_of_ms={known_as_of_ms}",
            contradiction_state=contradiction_state,
            confidence_bps=valid_events[0].confidence_bps if valid_events else 0,
            latency_by_phase_us=latencies,
            reconstructed_text=reconstructed_text
        )
