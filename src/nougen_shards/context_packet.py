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
import json
import math
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

DEFAULT_MAX_RESULTS = 5
DEFAULT_MIN_CONFIDENCE = 0.70
DEFAULT_DEADLINE_MS = 500


def graph_context_packet(query, candidates, expanded=(), *, token_budget=8000,
                         max_results=5, max_dependencies=20, sufficiency=1.0,
                         policy_version="graph-context-v1", load_dependency=None):
    """Select a bounded working projection without changing durable memory.

    Budget units are UTF-8 bytes of canonical payload JSON: a conservative
    token ceiling, not a tokenizer measurement. Dependency closures are atomic;
    missing or oversized prerequisites exclude the dependent root. Sufficiency
    is lexical query coverage, explicitly not a truth or evidence guarantee.
    """
    if token_budget < 0 or max_results < 0 or max_dependencies < 0:
        raise ValueError("budgets must be nonnegative")
    if not math.isfinite(sufficiency) or not 0 <= sufficiency <= 1:
        raise ValueError("sufficiency must be between zero and one")
    terms = set(re.findall(r"\w+", query.casefold()))

    def identity(item):
        return f"{item.get('source_node', 'local')}:{item.get('_db_index', item.get('db_index', 0))}:{item['id']}"

    def canonical(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def finite(value):
        try:
            number = float(value)
            return number if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0

    first, second = list(candidates), list(expanded)
    catalog = {}
    for item in sorted(first + second, key=lambda x: (identity(x), str(x.get('content', '')))):
        catalog.setdefault(identity(item), item)
    selected, decisions, covered, dependency_keys = {}, [], set(), set()
    roots = 0

    def words(item):
        return set(re.findall(r"\w+", (str(item.get('title', '')) + " " + str(item.get('content', ''))).casefold()))

    def closure(root):
        found, visiting = {}, set()

        def visit(item):
            key = identity(item)
            if key in visiting or key in found or key in selected:
                return
            visiting.add(key)
            deps = item.get('dependencies', [])
            if not isinstance(deps, list):
                raise ValueError("invalid_dependencies")
            for dep in sorted(deps, key=canonical):
                if not isinstance(dep, dict) or 'id' not in dep:
                    raise ValueError("invalid_dependency_reference")
                ref = dict(dep)
                ref.setdefault('source_node', item.get('source_node', 'local'))
                ref.setdefault('_db_index', item.get('_db_index', item.get('db_index', 0)))
                dep_key = identity(ref)
                target = catalog.get(dep_key)
                if target is None and load_dependency:
                    target = load_dependency(ref)
                    if target is not None and identity(target) != dep_key:
                        raise ValueError("dependency_identity_mismatch")
                    if target is not None:
                        catalog[dep_key] = target
                if target is None:
                    raise ValueError("missing_dependency")
                if len((set(found) | visiting | dependency_keys) - {identity(root)}) > max_dependencies:
                    raise ValueError("dependency_budget")
                visit(target)
            visiting.remove(key)
            found[key] = item
        visit(root)
        if len((set(found) | dependency_keys) - {identity(root)}) > max_dependencies:
            raise ValueError("dependency_budget")
        return found

    for stage, pool in (("narrow", first), ("expanded", second)):
        ranked = []
        for item in pool:
            relevance = len(terms & words(item)) / len(terms) if terms else 0.0
            if relevance:
                importance = max(0.0, finite(item.get('importance', item.get('utility_score', 0))))
                score = relevance + 0.1 * importance / (1 + importance)
                ranked.append((-score, identity(item), item, relevance))
        for negative_score, key, item, relevance in sorted(ranked, key=lambda row: row[:2]):
            if roots >= max_results or (roots and len(covered) / len(terms) >= sufficiency):
                break
            if key in selected:
                continue
            decision = {"id": key, "stage": stage, "relevance": relevance,
                        "selection_score": -negative_score, "policy_version": policy_version}
            try:
                addition = closure(item)
                proposal = dict(selected, **addition)
                payload = [{"id": k, "title": v.get('title', ''), "content": v.get('content', '')}
                           for k, v in proposal.items()]
                if len(canonical(payload).encode('utf-8')) > token_budget:
                    raise ValueError("token_budget")
                selected = proposal
                dependency_keys.update(set(addition) - {key})
                covered.update(terms & words(item))
                roots += 1
                decision['outcome'] = 'selected'
            except ValueError as exc:
                decision['outcome'] = str(exc)
            decisions.append(decision)
        if roots >= max_results or (roots and len(covered) / len(terms) >= sufficiency):
            break
    payload = [{"id": k, "title": v.get('title', ''), "content": v.get('content', '')}
               for k, v in selected.items()]
    provenance = [{"id": k, "content_hash": "sha256:" + hashlib.sha256(str(v.get('content', '')).encode('utf-8')).hexdigest(),
                   "source_uri": v.get('source_uri'), "evidence_level": v.get('evidence_level', 'unclassified')}
                  for k, v in selected.items()]
    return {"query": query, "policy_version": policy_version, "content_payload": payload,
            "provenance_chain": provenance, "decisions": decisions,
            "metrics": {"budget_units": "utf8_bytes_upper_bound", "tokens_consumed": len(canonical(payload).encode('utf-8')) if payload else 0,
                        "token_budget": token_budget, "query_coverage": len(covered) / len(terms) if terms else 0,
                        "roots": roots, "dependencies": len(dependency_keys)},
            "replay_hash": hashlib.sha256(canonical({"payload": payload, "decisions": decisions, "policy": policy_version}).encode('utf-8')).hexdigest()}

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
