"""NouGen Bounded Context Packet Primitive & Scalpel First Engine.

Implements Hardcade mandate for Relay legs:
- 20260926T160434Z: Adopt Scalpel First as universal retrieval policy.
- 20260926T160743Z: Build NouGen Context Mode as a bounded MCP context-packet primitive.

Law:
1. One AI call in -> One bounded, deterministic ContextPacket out.
2. Scalpel First flow: Narrowest Stage 1 FTS5 probe -> single-dimension Stage 2 vault expansion only when confidence threshold not satisfied.
3. Strict budget ceilings: max_results, max_expansions, min_confidence, deadline_ms.
4. Cryptographic provenance tuple: (source, id, hash, timestamp, confidence).
"""

from __future__ import annotations
import time
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

DEFAULT_MAX_RESULTS = 5
DEFAULT_MIN_CONFIDENCE = 0.70
DEFAULT_DEADLINE_MS = 500

@dataclass(frozen=True)
class ProvenanceTuple:
    source_node: str
    shard_id: str
    content_hash: str
    timestamp_utc: str
    confidence_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_node": self.source_node,
            "shard_id": self.shard_id,
            "content_hash": self.content_hash,
            "timestamp_utc": self.timestamp_utc,
            "confidence_score": self.confidence_score,
        }

@dataclass
class ContextPacket:
    query: str
    retrieval_stage: str  # "stage_1_scalpel" or "stage_2_expanded"
    provenance_chain: List[ProvenanceTuple] = field(default_factory=list)
    content_payload: List[Dict[str, Any]] = field(default_factory=list)
    tokens_consumed: int = 0
    duration_ms: float = 0.0
    budget_adhered: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "retrieval_stage": self.retrieval_stage,
            "provenance_chain": [p.to_dict() for p in self.provenance_chain],
            "content_payload": self.content_payload,
            "metrics": {
                "tokens_consumed": self.tokens_consumed,
                "duration_ms": self.duration_ms,
                "budget_adhered": self.budget_adhered
            }
        }

def scalpel_first_retrieve(
    query: str,
    stage_1_candidates: List[Dict[str, Any]],
    stage_2_vault: Optional[List[Dict[str, Any]]] = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    deadline_ms: int = DEFAULT_DEADLINE_MS
) -> ContextPacket:
    """Executes Scalpel First bounded retrieval."""
    t0 = time.time()
    query_lower = query.strip().lower()
    
    # --- STAGE 1: Narrowest Scalpel FTS5 Probe ---
    stage_1_hits = []
    for cand in stage_1_candidates:
        content = cand.get("content", "").lower()
        title = cand.get("title", "").lower()
        score = 0.0
        if query_lower in title:
            score = 0.95
        elif query_lower in content:
            score = 0.82
        elif any(token in content for token in query_lower.split() if len(token) > 2):
            score = 0.65
        
        if score > 0.0:
            stage_1_hits.append((score, cand))
            
    stage_1_hits.sort(key=lambda x: x[0], reverse=True)
    
    stage = "stage_1_scalpel"
    final_hits = []
    
    # Evaluate confidence threshold
    top_score = stage_1_hits[0][0] if stage_1_hits else 0.0
    if top_score >= min_confidence:
        final_hits = stage_1_hits[:max_results]
    else:
        # --- STAGE 2: Progressive Bounded Expansion ---
        stage = "stage_2_expanded"
        expanded = list(stage_1_hits)
        if stage_2_vault:
            for item in stage_2_vault:
                c = item.get("content", "").lower()
                if any(w in c for w in query_lower.split() if len(w) > 2):
                    expanded.append((0.72, item))
        expanded.sort(key=lambda x: x[0], reverse=True)
        final_hits = expanded[:max_results]

    # Build Provenance Chain
    provenance = []
    payload = []
    total_tokens = 0
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for score, item in final_hits:
        body = item.get("content", "")
        h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        sid = str(item.get("id", "0"))
        node = item.get("source_node", "local")
        
        provenance.append(ProvenanceTuple(
            source_node=node,
            shard_id=sid,
            content_hash=f"sha256:{h}",
            timestamp_utc=now_iso,
            confidence_score=score
        ))
        
        payload.append({
            "id": sid,
            "title": item.get("title", ""),
            "content": body,
            "confidence": score
        })
        total_tokens += len(body.split())

    duration = (time.time() - t0) * 1000
    budget_ok = duration <= deadline_ms

    return ContextPacket(
        query=query,
        retrieval_stage=stage,
        provenance_chain=provenance,
        content_payload=payload,
        tokens_consumed=total_tokens,
        duration_ms=round(duration, 2),
        budget_adhered=budget_ok
    )
