"""
retrieval_v2.py

NouGen Retrieval Engine v2 (ZANGIEF 720 Architecture).
Multi-Axis State Vector, Typed Query Compiler, Deterministic RRF Fusion, and State-Driven Recovery.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# ============================================================
# 1. TYPED SCHEMAS & QUERY COMPILER
# ============================================================

@dataclass(frozen=True)
class TemporalDeixis:
    raw_expression: str = ""
    period: str = "ALL_TIME"  # YTD, MTD, QTD, DAILY, ALL_TIME, CUSTOM
    year: Optional[int] = None
    month: Optional[int] = None
    start_utc: Optional[str] = None
    end_utc: Optional[str] = None


@dataclass(frozen=True)
class CanonicalEntity:
    entity_id: str
    canonical_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    machine_binding: str = "fleet"  # blade1tb, phoebus, whoart, fleet
    domain: str = "general"


@dataclass(frozen=True)
class RetrievalIntent:
    raw_query: str
    normalized_query: str
    metric: str = "general_search"
    scope: str = "fleet"  # node, fleet, domain
    temporal: TemporalDeixis = field(default_factory=TemporalDeixis)
    required_entities: tuple[CanonicalEntity, ...] = field(default_factory=tuple)
    canonical_key: str = ""


def normalize_nfkc(text: str) -> str:
    """Normalize Unicode NFKC, strip excess whitespace."""
    normalized = unicodedata.normalize("NFKC", text or "")
    return " ".join(normalized.split()).strip()


def parse_temporal_deixis(query: str, now: Optional[datetime] = None) -> TemporalDeixis:
    """Deterministic temporal parser extracting deixis without floating-point drift."""
    now = now or datetime.now(timezone.utc)
    q = query.lower()
    
    if "ytd" in q or "year to date" in q or "this year" in q:
        return TemporalDeixis(
            raw_expression="YTD",
            period="YTD",
            year=now.year,
            start_utc=f"{now.year}-01-01T00:00:00Z",
            end_utc=now.isoformat()
        )
    elif "today" in q:
        return TemporalDeixis(
            raw_expression="today",
            period="DAILY",
            year=now.year,
            month=now.month,
            start_utc=f"{now.strftime('%Y-%m-%d')}T00:00:00Z",
            end_utc=now.isoformat()
        )
    elif "month to date" in q or "mtd" in q or "this month" in q:
        return TemporalDeixis(
            raw_expression="MTD",
            period="MTD",
            year=now.year,
            month=now.month,
            start_utc=f"{now.strftime('%Y-%m')}-01T00:00:00Z",
            end_utc=now.isoformat()
        )
    return TemporalDeixis(raw_expression="all_time", period="ALL_TIME", year=now.year)


def compile_retrieval_intent(
    query: str,
    now: Optional[datetime] = None,
    entities_registry: Sequence[CanonicalEntity] = (),
) -> RetrievalIntent:
    """Typed Query Compiler producing deterministic JSON-serializable intent."""
    normalized = normalize_nfkc(query)
    temporal = parse_temporal_deixis(normalized, now=now)
    
    # Classify metric
    q_lower = normalized.lower()
    if any(w in q_lower for w in ("token", "tokens", "usage", "cost", "billing", "spend")):
        metric = "token_usage"
    elif any(w in q_lower for w in ("shard", "memory", "recall", "vault")):
        metric = "shard_memory"
    elif any(w in q_lower for w in ("relay", "handoff", "leg", "baton")):
        metric = "relay_handoff"
    else:
        metric = "knowledge_search"

    # Identify entities
    matched_entities: list[CanonicalEntity] = []
    for entity in entities_registry:
        if entity.canonical_name.lower() in q_lower or any(a.lower() in q_lower for a in entity.aliases):
            matched_entities.append(entity)

    # Scope inference
    if any(e.machine_binding != "fleet" for e in matched_entities):
        scope = "node"
    elif "fleet" in q_lower or "all machines" in q_lower or "all-machine" in q_lower:
        scope = "fleet"
    else:
        scope = "fleet"

    canonical_key = f"{metric}::{scope}::{temporal.period}::{temporal.year}"
    
    return RetrievalIntent(
        raw_query=query,
        normalized_query=normalized,
        metric=metric,
        scope=scope,
        temporal=temporal,
        required_entities=tuple(matched_entities),
        canonical_key=canonical_key,
    )


# ============================================================
# 2. MULTI-AXIS STATE VECTOR & ORTHOGONAL FLAGS
# ============================================================

@dataclass(frozen=True)
class OrthogonalFlags:
    missing_expected_nodes: bool = False
    retryable: bool = True
    traceable: bool = True
    deeper_search_available: bool = False
    failover_available: bool = False
    exact_source_available: bool = False
    coverage_complete: bool = True


@dataclass(frozen=True)
class MultiAxisStateVector:
    """Multi-axis state vector ensuring non-collapsed, audited query execution states."""
    completeness: str = "COMPLETE"       # COMPLETE, PARTIAL, UNKNOWN
    conflict: str = "CONSISTENT"         # CONSISTENT, CONFLICTED, UNRESOLVED
    freshness: str = "CURRENT"           # CURRENT, STALE, EXPIRED
    retrieval: str = "HIT"               # HIT, NO_HIT, AMBIGUOUS
    pagination: str = "NORMAL"           # NORMAL, STALLED, LOOP_DETECTED
    availability: str = "AVAILABLE"      # AVAILABLE, DEGRADED, TIMEOUT
    truth_quality: str = "EXACT"         # EXACT, ESTIMATED, UNKNOWN
    canonicality: str = "CANONICAL"      # CANONICAL, SUPERSEDED, FORKED
    canonical_key: str = ""
    flags: OrthogonalFlags = field(default_factory=OrthogonalFlags)

    def validate_schema(self) -> list[str]:
        """Detect invalid or contradictory state combinations."""
        violations = []
        if self.completeness == "COMPLETE" and self.flags.missing_expected_nodes:
            violations.append("Contradiction: completeness=COMPLETE while missing_expected_nodes=True")
        if self.truth_quality == "EXACT" and self.conflict == "CONFLICTED":
            violations.append("Contradiction: truth_quality=EXACT while conflict=CONFLICTED")
        if self.freshness == "EXPIRED" and self.canonicality == "CANONICAL" and self.flags.coverage_complete:
            violations.append("Warning: freshness=EXPIRED on current canonical key without supersession")
        return violations


# ============================================================
# 3. DETERMINISTIC RECOVERY DISPATCHER
# ============================================================

def next_recovery_action(state: MultiAxisStateVector) -> str:
    """State-driven recovery dispatcher evaluating deterministic next action."""
    s = state
    f = s.flags

    if s.completeness == "PARTIAL" and f.missing_expected_nodes and f.retryable:
        return "CONTINUE_FEDERATION"
    if s.conflict == "CONFLICTED" and f.traceable:
        return "TRACE_PROVENANCE"
    if s.freshness == "STALE" and s.canonical_key:
        return "REFRESH_CANONICAL"
    if s.retrieval == "NO_HIT" and not f.coverage_complete:
        return "EXPAND_RETRIEVAL"
    if s.retrieval == "NO_HIT" and f.coverage_complete and f.deeper_search_available:
        return "DRIFT_RECURSE"
    if s.pagination in ("STALLED", "LOOP_DETECTED"):
        return "REPARTITION_QUERY"
    if s.availability == "TIMEOUT" and f.failover_available:
        return "FAILOVER"
    if s.truth_quality == "ESTIMATED" and f.exact_source_available:
        return "RECONCILE"
    if s.canonicality == "SUPERSEDED":
        return "FOLLOW_SUPERSESSION"
    
    return "STOP_WITH_EXPLICIT_STATE"


# ============================================================
# 4. CANDIDATE SCHEMA & DETERMINISTIC RRF FUSION
# ============================================================

@dataclass(frozen=True)
class ArtifactCandidate:
    candidate_id: str
    title: str
    lane: str  # exact, bm25, trigram, ann, graph
    raw_score: float
    snippet: str = ""
    provenance_source: str = ""
    db_index: int = 1


def reciprocal_rank_fusion(
    lane_candidates: Dict[str, Sequence[ArtifactCandidate]],
    k: int = 60,
    top_n: int = 20,
) -> List[Tuple[ArtifactCandidate, float]]:
    """Deterministic Reciprocal Rank Fusion with stable candidate ID tie-breaking."""
    rrf_scores: dict[str, float] = defaultdict(float)
    candidate_map: dict[str, ArtifactCandidate] = {}

    for lane_name in sorted(lane_candidates.keys()):
        candidates = list(lane_candidates[lane_name])
        # Stable sort candidates within lane (highest score first, tie-break by candidate_id)
        sorted_candidates = sorted(candidates, key=lambda c: (-c.raw_score, c.candidate_id))
        
        for rank, cand in enumerate(sorted_candidates, start=1):
            rrf_scores[cand.candidate_id] += 1.0 / (k + rank)
            if cand.candidate_id not in candidate_map:
                candidate_map[cand.candidate_id] = cand

    # Stable global sort (highest RRF score first, tie-break by candidate_id)
    sorted_ids = sorted(
        candidate_map.keys(),
        key=lambda cid: (-rrf_scores[cid], cid)
    )

    return [(candidate_map[cid], rrf_scores[cid]) for cid in sorted_ids[:top_n]]


# ============================================================
# 5. QUERY RECEIPT & PROVENANCE DAG
# ============================================================

@dataclass(frozen=True)
class QueryReceipt:
    query_id: str
    intent: RetrievalIntent
    state: MultiAxisStateVector
    recommended_action: str
    fused_candidates: tuple[ArtifactCandidate, ...]
    coverage_nodes: tuple[str, ...]
    latency_ms: float
    receipt_hash: str

    def to_json(self) -> str:
        return json.dumps({
            "query_id": self.query_id,
            "intent": asdict(self.intent),
            "state": asdict(self.state),
            "recommended_action": self.recommended_action,
            "candidates_count": len(self.fused_candidates),
            "coverage_nodes": list(self.coverage_nodes),
            "latency_ms": self.latency_ms,
            "receipt_hash": self.receipt_hash,
        }, indent=2, default=str)


def create_query_receipt(
    intent: RetrievalIntent,
    state: MultiAxisStateVector,
    fused_candidates: Sequence[ArtifactCandidate],
    coverage_nodes: Sequence[str] = ("whoart",),
    latency_ms: float = 0.0,
) -> QueryReceipt:
    """Generate tamper-evident query receipt with deterministic recovery action."""
    action = next_recovery_action(state)
    payload = f"{intent.canonical_key}|{state.completeness}|{state.conflict}|{state.freshness}|{action}"
    receipt_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    query_id = f"qr-{hashlib.sha256(intent.raw_query.encode()).hexdigest()[:10]}"

    return QueryReceipt(
        query_id=query_id,
        intent=intent,
        state=state,
        recommended_action=action,
        fused_candidates=tuple(fused_candidates),
        coverage_nodes=tuple(coverage_nodes),
        latency_ms=latency_ms,
        receipt_hash=receipt_hash,
    )
