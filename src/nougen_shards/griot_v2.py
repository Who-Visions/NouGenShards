"""
griot_v2.py

NouGen Griot v2 — Archive-Oriented Memory & Retrieval Planner.
Implements a bounded local FTS lane and explicit evidence/coverage envelope.
This is not the complete 28-class HURRICANE KICK implementation.

Key Invariants:
1. Coverage Honesty: No remote node is considered healthy without a caller-supplied probe receipt.
2. Compound Shard IDs: Always `{shard_id}@db{db_index}`.
3. Truncation Transparency: Exposes total candidates, returned count, and truncation flags.
4. Epistemic Typing: Distinguishes verified telemetry, user canon, process donors, external papers, model inferences.
5. Absence Proof: Incomplete configured coverage remains PARTIAL; a local FTS miss is not global absence.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

from nougen_shards.retrieval_v2 import (
    ArtifactCandidate,
    MultiAxisStateVector,
    OrthogonalFlags,
    QueryReceipt,
    RetrievalIntent,
    compile_retrieval_intent,
    create_query_receipt,
    next_recovery_action,
    reciprocal_rank_fusion,
)


# ============================================================
# 1. EPISTEMIC TAXONOMY & COMPOUND ID SPECIFICATION
# ============================================================

class EpistemicClass:
    VERIFIED_TELEMETRY = "VERIFIED_TELEMETRY"
    USER_CANON = "USER_CANON"
    CANDIDATE_CANON = "CANDIDATE_CANON"
    PROCESS_DONOR = "PROCESS_DONOR"
    EXTERNAL_PAPER = "EXTERNAL_PAPER"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    MIGRATED_MEMORY = "MIGRATED_MEMORY"
    STALE_FACT = "STALE_FACT"


@dataclass(frozen=True)
class CompoundShardRef:
    shard_id: int
    db_index: int

    @property
    def compound_id(self) -> str:
        return f"{self.shard_id}@db{self.db_index}"

    @classmethod
    def from_str(cls, raw: str) -> Optional["CompoundShardRef"]:
        if "@db" in raw:
            parts = raw.split("@db")
            try:
                return cls(shard_id=int(parts[0]), db_index=int(parts[1]))
            except ValueError:
                return None
        return None


# ============================================================
# 2. COVERAGE MATRIX & FAILURE TRACKER
# ============================================================

@dataclass(frozen=True)
class NodeCoverageStatus:
    node_name: str
    attempted: bool = True
    succeeded: bool = True
    status_code: int = 200
    error_message: Optional[str] = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class GriotCoverageMatrix:
    nodes: tuple[NodeCoverageStatus, ...]
    vault_dbs_expected: tuple[int, ...]
    vault_dbs_scanned: tuple[int, ...]
    is_fully_covered: bool
    failures: tuple[str, ...]

    def get_node(self, name: str) -> Optional[NodeCoverageStatus]:
        for n in self.nodes:
            if n.node_name == name:
                return n
        return None


# ============================================================
# 3. GRIOT ARTIFACT ENVELOPE & PACKET
# ============================================================

@dataclass(frozen=True)
class GriotArtifact:
    compound_id: str
    title: str
    content: str
    epistemic_class: str
    score: float
    created_at_utc: str
    content_sha256: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    is_superseded: bool = False
    superseded_by: Optional[str] = None


@dataclass(frozen=True)
class GriotPacket:
    query: str
    intent: RetrievalIntent
    state: MultiAxisStateVector
    coverage: GriotCoverageMatrix
    artifacts: tuple[GriotArtifact, ...]
    candidate_total: int
    returned_count: int
    is_truncated: bool
    receipt: QueryReceipt
    recommended_recovery: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": asdict(self.intent),
            "state": asdict(self.state),
            "coverage": {
                "nodes": [asdict(n) for n in self.coverage.nodes],
                "vault_dbs": list(self.coverage.vault_dbs_scanned),
                "is_fully_covered": self.coverage.is_fully_covered,
                "failures": list(self.coverage.failures),
            },
            "artifacts_count": len(self.artifacts),
            "candidate_total": self.candidate_total,
            "returned_count": self.returned_count,
            "is_truncated": self.is_truncated,
            "recommended_recovery": self.recommended_recovery,
            "receipt_hash": self.receipt.receipt_hash,
        }


# ============================================================
# 4. ARCHIVE GATHERING & RETRIEVAL ENGINE V2 PLANNER
# ============================================================

def infer_epistemic_class(title: str, tags: Sequence[str]) -> str:
    """Classify knowledge shard into authoritative epistemic class."""
    t_lower = title.lower()
    tags_lower = [str(t).lower() for t in tags]

    if any("telemetry" in t or "receipt" in t for t in tags_lower):
        return EpistemicClass.VERIFIED_TELEMETRY
    if any("canon" in t or "lore" in t for t in tags_lower):
        return EpistemicClass.USER_CANON
    if any("arxiv" in t or "paper" in t for t in tags_lower) or "arxiv" in t_lower:
        return EpistemicClass.EXTERNAL_PAPER
    if any("stale" in t or "expired" in t for t in tags_lower):
        return EpistemicClass.STALE_FACT
    if any("migrated" in t for t in tags_lower):
        return EpistemicClass.MIGRATED_MEMORY
    if any("skill" in t or "donor" in t for t in tags_lower):
        return EpistemicClass.PROCESS_DONOR
    return EpistemicClass.MODEL_INFERENCE


def gather_griot_archive(
    query: str,
    now: Optional[datetime] = None,
    simulated_node_failures: Optional[Dict[str, str]] = None,
    node_statuses: Optional[Sequence[NodeCoverageStatus]] = None,
    max_top_k: int = 20,
    vault_dbs_dir: Optional[Path] = None,
) -> GriotPacket:
    """Execute Griot v2 archive gathering with coverage honesty and multi-axis state resolution."""
    start_time = time.time()
    intent = compile_retrieval_intent(query, now=now)

    if max_top_k < 0:
        raise ValueError("max_top_k must be non-negative")

    # This planner has no implicit network client: only caller-supplied probe receipts count.
    nodes_coverage = []
    failures_list = []
    supplied_statuses = {status.node_name: status for status in (node_statuses or ())}
    simulated_failures = simulated_node_failures or {}
    fleet_nodes = ("whoart", "blade1tb", "phoebus")
    for node in fleet_nodes:
        if node in simulated_failures:
            err = simulated_failures[node]
            status_code = 502 if "502" in err else 504
            status = NodeCoverageStatus(
                node_name=node,
                attempted=True,
                succeeded=False,
                status_code=status_code,
                error_message=err,
            )
        elif node in supplied_statuses:
            status = supplied_statuses[node]
        else:
            status = NodeCoverageStatus(
                node_name=node,
                attempted=False,
                succeeded=False,
                status_code=0,
                error_message="no probe receipt supplied",
            )
        nodes_coverage.append(status)
        if not status.attempted:
            failures_list.append(f"{node}: not probed")
        elif not status.succeeded or not 200 <= status.status_code < 300:
            failures_list.append(f"{node}: {status.error_message or 'probe failed'}")

    # Query every expected local DB. Missing or unreadable stores are coverage failures.
    v_dir = vault_dbs_dir or (Path.home() / ".nougen" / "shards")
    expected_dbs = tuple(range(1, 10))
    scanned_dbs = []
    candidate_records: list[GriotArtifact] = []
    ranked_lanes: Dict[str, List[ArtifactCandidate]] = {}
    candidate_total = 0
    words = [w for w in re.findall(r"\w+", intent.normalized_query, flags=re.UNICODE) if len(w) > 2]
    match_query = " OR ".join(f'"{word}"' for word in words[:4])
    where_clauses = ["shards_fts MATCH ?"]
    query_params: list[str] = [match_query]
    if intent.temporal.period != "ALL_TIME" and intent.temporal.start_utc and intent.temporal.end_utc:
        where_clauses.extend(("julianday(s.timestamp) >= julianday(?)", "julianday(s.timestamp) <= julianday(?)"))
        query_params.extend((intent.temporal.start_utc, intent.temporal.end_utc))
    where_sql = " AND ".join(where_clauses)

    for i in expected_dbs:
        db_path = v_dir / f"nougen_shards_{i}.db"
        if not db_path.exists():
            failures_list.append(f"vault_db_{i}: expected database missing")
            continue
        try:
            db_uri = f"file:{quote(str(db_path))}?mode=ro"
            with closing(sqlite3.connect(db_uri, uri=True, timeout=2.0)) as conn:
                cur = conn.cursor()
                if match_query:
                    cur.execute(
                        "SELECT COUNT(DISTINCT s.id) "
                        "FROM shards s JOIN shards_fts f ON s.id = f.rowid "
                        f"WHERE {where_sql}",
                        query_params,
                    )
                    candidate_total += int(cur.fetchone()[0])
                    cur.execute(
                        "SELECT s.id, s.title, s.content, s.tags, s.timestamp, "
                        "bm25(shards_fts) AS rank "
                        "FROM shards s JOIN shards_fts f ON s.id = f.rowid "
                        f"WHERE {where_sql} "
                        "ORDER BY rank ASC, s.id ASC LIMIT ?",
                        [*query_params, max_top_k],
                    )
                    rows = cur.fetchall()
                    lane = f"db{i}_fts_bm25"
                    ranked_lanes[lane] = []
                    for shard_id, title, content, tags_json, created_at, rank in rows:
                        try:
                            tags = json.loads(tags_json) if tags_json else []
                        except (TypeError, json.JSONDecodeError):
                            tags = []
                        compound_id = f"{shard_id}@db{i}"
                        candidate_records.append(GriotArtifact(
                            compound_id=compound_id,
                            title=title or "",
                            content=content or "",
                            epistemic_class=infer_epistemic_class(title or "", tags),
                            score=-float(rank),
                            created_at_utc=str(created_at or ""),
                            content_sha256=hashlib.sha256((content or "").encode("utf-8")).hexdigest(),
                            tags=tuple(str(tag) for tag in tags),
                        ))
                        ranked_lanes[lane].append(ArtifactCandidate(
                            candidate_id=compound_id,
                            title=title or "",
                            lane=lane,
                            raw_score=-float(rank),
                            snippet=(content or "")[:150],
                            provenance_source=f"local_db_{i}",
                            db_index=i,
                        ))
                scanned_dbs.append(i)
        except Exception as e:
            failures_list.append(f"vault_db_{i}: {type(e).__name__}: {e}")

    # Deduplicate candidates by content/compound ID
    unique_artifacts: dict[str, GriotArtifact] = {}
    for a in candidate_records:
        if a.compound_id not in unique_artifacts:
            unique_artifacts[a.compound_id] = a

    fused = reciprocal_rank_fusion(ranked_lanes, top_n=max_top_k)
    sorted_artifacts = [
        GriotArtifact(
            **{**asdict(unique_artifacts[candidate.candidate_id]), "score": fused_score}
        )
        for candidate, fused_score in fused
    ]
    returned_count = len(sorted_artifacts)
    is_truncated = candidate_total > returned_count

    # Resolve Multi-Axis State Vector
    is_fully_covered = (
        all(
            status.attempted and status.succeeded and 200 <= status.status_code < 300
            for status in nodes_coverage
        )
        and set(scanned_dbs) == set(expected_dbs)
    )
    completeness = "COMPLETE" if is_fully_covered else "PARTIAL"
    retrieval_status = "HIT" if candidate_total > 0 else "NO_HIT"
    availability_status = "AVAILABLE" if is_fully_covered else "DEGRADED"

    coverage_matrix = GriotCoverageMatrix(
        nodes=tuple(nodes_coverage),
        vault_dbs_expected=expected_dbs,
        vault_dbs_scanned=tuple(scanned_dbs),
        is_fully_covered=is_fully_covered,
        failures=tuple(failures_list),
    )

    flags = OrthogonalFlags(
        missing_expected_nodes=not is_fully_covered,
        retryable=not is_fully_covered,
        traceable=True,
        deeper_search_available=candidate_total == 0,
        coverage_complete=is_fully_covered,
    )

    state_vector = MultiAxisStateVector(
        completeness=completeness,
        conflict="CONSISTENT",
        freshness="CURRENT",
        retrieval=retrieval_status,
        availability=availability_status,
        canonical_key=intent.canonical_key,
        flags=flags,
    )

    # Compile fused candidate models for receipt
    fused_candidates = [
        ArtifactCandidate(
            candidate_id=a.compound_id,
            title=a.title,
            lane="local_db_rrf",
            raw_score=a.score,
            snippet=a.content[:150],
        )
        for a in sorted_artifacts
    ]

    receipt = create_query_receipt(
        intent=intent,
        state=state_vector,
        fused_candidates=fused_candidates,
        coverage_nodes=tuple(n.node_name for n in nodes_coverage if n.succeeded),
        latency_ms=(time.time() - start_time) * 1000,
    )

    recovery_action = next_recovery_action(state_vector)

    return GriotPacket(
        query=query,
        intent=intent,
        state=state_vector,
        coverage=coverage_matrix,
        artifacts=tuple(sorted_artifacts),
        candidate_total=candidate_total,
        returned_count=returned_count,
        is_truncated=is_truncated,
        receipt=receipt,
        recommended_recovery=recovery_action,
    )
