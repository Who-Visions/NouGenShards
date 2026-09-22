"""Evidence-grounded retrieval donor notes and a deterministic cascade baseline.

The papers below are design donors, not implementations shipped by this module.
This baseline has lexical, character-ngram, and entity lanes with RRF. It does
not implement embedding-based ColBERT MaxSim or graph PCST optimization.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .retrieval_v2 import ArtifactCandidate, reciprocal_rank_fusion


class DonorCategory(str, Enum):
    LATE_INTERACTION = "LATE_INTERACTION"
    SUBGRAPH_EXTRACTION = "SUBGRAPH_EXTRACTION"
    ACTIVE_RECONSTRUCTION = "ACTIVE_RECONSTRUCTION"
    PROVENANCE_LOCK = "PROVENANCE_LOCK"


@dataclass(frozen=True)
class ArxivDonorMethod:
    arxiv_id: str
    title: str
    primary_category: DonorCategory
    nougen_component: str
    evidence: str
    integration_status: str
    limitation: str


# Paper-backed design donors. Applicability is qualitative until measured on a
# NouGen benchmark; these records intentionally carry no invented percentages.
CANONICAL_DONORS: List[ArxivDonorMethod] = [
    ArxivDonorMethod(
        arxiv_id="2112.01488",
        title="ColBERTv2: Effective and Efficient Retrieval via Lightweight Late Interaction",
        primary_category=DonorCategory.LATE_INTERACTION,
        nougen_component="retrieval_v2.late_interaction",
        evidence="Token-level multi-vector late interaction with residual compression.",
        integration_status="DESIGN_ONLY",
        limitation="This module has no token embeddings; its lexical scorer is not ColBERT MaxSim.",
    ),
    ArxivDonorMethod(
        arxiv_id="2402.07630",
        title="G-Retriever: Retrieval-Augmented Generation for Textual Graph Understanding and Question Answering",
        primary_category=DonorCategory.SUBGRAPH_EXTRACTION,
        nougen_component="retrieval_v2.graph_subgraph",
        evidence="Textual graph retrieval framed as prize-collecting Steiner tree optimization.",
        integration_status="NOT_APPLICABLE_TO_TEXT_ONLY_CASCADE",
        limitation="The cascade input has no scored graph edges or PCST solver.",
    ),
    ArxivDonorMethod(
        arxiv_id="2607.16208",
        title="ColGraphRAG: Late-Interaction Evidence Retrieval for Multimodal GraphRAG",
        primary_category=DonorCategory.SUBGRAPH_EXTRACTION,
        nougen_component="retrieval_v2.hybrid_cascade",
        evidence="Late-interaction ranking of graph-linked visual evidence; text/table retrieval unchanged.",
        integration_status="NOT_APPLICABLE_TO_TEXT_ONLY_CASCADE",
        limitation="The paper studies multimodal image nodes; this cascade only accepts text.",
    ),
    ArxivDonorMethod(
        arxiv_id="2606.06036",
        title="MRAgent: Memory is Reconstructed, Not Retrieved",
        primary_category=DonorCategory.ACTIVE_RECONSTRUCTION,
        nougen_component="reconstructive_recall_v2",
        evidence="Cue-Tag-Content associative graph with active, iteratively pruned reconstruction.",
        integration_status="PARTIAL_EXISTING_PROTOTYPE",
        limitation="Bounded expansion exists in reconstruction.py; this cascade does not invoke it.",
    ),
    ArxivDonorMethod(
        arxiv_id="2608.29606",
        title="Agent Zero Memory: Provenance-Aware Long-Term Memory for LLM Agents",
        primary_category=DonorCategory.PROVENANCE_LOCK,
        nougen_component="nougen_shards.multi_store",
        evidence="Parallel episodic, associative, and documentary memories with citation-locked reading.",
        integration_status="PARTIAL_EXISTING_PRIMITIVES",
        limitation="Federated lanes exist; this module only cites content it reads from its supplied corpus.",
    )
]


@dataclass(frozen=True)
class CandidateEvidence:
    artifact_id: str
    score_bps: int
    lane: str
    tokens: List[str]
    opened: bool = False
    provenance_sha: str = ""


@dataclass(frozen=True)
class AnswerPacket:
    query: str
    primary_answer: str
    grounded_evidence_ids: List[str]
    abstention_reason: Optional[str] = None
    query_receipt_sha: str = ""
    total_latency_ms: int = 0
    evidence_hashes: Dict[str, str] = field(default_factory=dict)


class ArxivCascadeRetriever:
    """A small, deterministic sparse retrieval baseline.

    The donor papers motivate explicit retrieval lanes, bounded evidence, and
    provenance discipline. Expensive neural/graph operators remain out of scope.
    """

    def __init__(self, donors: Optional[List[ArxivDonorMethod]] = None):
        self.donors = donors or CANONICAL_DONORS

    @staticmethod
    def _tokens(text: str) -> List[str]:
        return re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)

    @staticmethod
    def _ngrams(tokens: List[str], n: int = 3) -> set[str]:
        compact = " ".join(tokens)
        return {compact[i:i + n] for i in range(max(0, len(compact) - n + 1))}

    @staticmethod
    def _overlap(query: set[str], document: set[str]) -> float:
        return len(query & document) / len(query) if query else 0.0

    @staticmethod
    def reciprocal_rank_fusion(rank_lists: Dict[str, List[str]], k: int = 60) -> List[Tuple[str, float]]:
        """Use Retrieval v2's canonical deterministic rank fusion implementation."""
        lanes = {
            lane: [ArtifactCandidate(doc_id, doc_id, lane, 1.0 / rank)
                   for rank, doc_id in enumerate(dict.fromkeys(ids), 1)]
            for lane, ids in rank_lists.items()
        }
        return [
            (candidate.candidate_id if hasattr(candidate, "candidate_id") else str(candidate), score)
            for candidate, score in reciprocal_rank_fusion(lanes, k=k)
        ]

    def execute_cascade(
        self,
        query: str,
        corpus: Dict[str, Dict[str, Any]],
        fast_path_hit: Optional[Dict[str, Any]] = None
    ) -> AnswerPacket:
        t0 = time.perf_counter_ns()
        query_tokens = self._tokens(query)
        query_terms = set(query_tokens)

        # Step 1: Fast path guard
        if self._valid_fast_path(fast_path_hit):
            content = fast_path_hit["content"]
            artifact_id = fast_path_hit["artifact_id"]
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            receipt = hashlib.sha256(
                f"FAST:{query}:{artifact_id}:{content_hash}".encode("utf-8")
            ).hexdigest()
            t1 = time.perf_counter_ns()
            return AnswerPacket(
                query=query,
                primary_answer=content,
                grounded_evidence_ids=[artifact_id],
                query_receipt_sha=receipt,
                total_latency_ms=(t1 - t0) // 1_000_000,
                evidence_hashes={artifact_id: content_hash},
            )

        # Step 2: Multi-lane parallel candidate generation
        lane_scores: Dict[str, Dict[str, float]] = {"lexical": {}, "trigram": {}, "entity": {}}
        document_tokens: Dict[str, set[str]] = {}
        document_ngrams: Dict[str, set[str]] = {}

        for doc_id, data in corpus.items():
            content = data.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue
            tokens = set(self._tokens(content))
            document_tokens[doc_id] = tokens
            document_ngrams[doc_id] = self._ngrams(self._tokens(content))
            lexical_score = self._overlap(query_terms, tokens)
            if lexical_score:
                lane_scores["lexical"][doc_id] = lexical_score
            trigram_score = self._overlap(self._ngrams(query_tokens), document_ngrams[doc_id])
            if trigram_score >= 0.25:
                lane_scores["trigram"][doc_id] = trigram_score
            entity_tokens = set(self._tokens(" ".join(str(e) for e in data.get("entities", []))))
            entity_score = self._overlap(query_terms, entity_tokens)
            if entity_score:
                lane_scores["entity"][doc_id] = entity_score

        # Step 3: Deterministic RRF Fusion
        ranked_lanes = {
            lane: [doc_id for doc_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
            for lane, scores in lane_scores.items()
        }
        fused = self.reciprocal_rank_fusion(ranked_lanes)

        if not fused:
            t1 = time.perf_counter_ns()
            receipt = hashlib.sha256(f"ABSTAIN:{query}".encode("utf-8")).hexdigest()
            return AnswerPacket(
                query=query,
                primary_answer="",
                grounded_evidence_ids=[],
                abstention_reason="ZERO_CANDIDATES_ACROSS_ALL_LANES",
                query_receipt_sha=receipt,
                total_latency_ms=(t1 - t0) // 1_000_000
            )

        # Step 4: Cheap lexical coverage reranking; not embedding-based MaxSim.
        top_candidates = fused[:10]
        reranked = []
        for doc_id, rrf_score in top_candidates:
            lexical_score = self._overlap(query_terms, document_tokens[doc_id])
            entity_score = lane_scores["entity"].get(doc_id, 0.0)
            score = max(lexical_score, entity_score)
            reranked.append((doc_id, score, rrf_score))

        reranked.sort(key=lambda x: (-x[1], -x[2], x[0]))
        best_doc_id, best_score, _ = reranked[0]
        if best_score < 0.6:
            return self._abstain(query, "LOW_EVIDENCE_OVERLAP", t0)
        if len(reranked) > 1 and best_score == reranked[1][1]:
            return self._abstain(query, "AMBIGUOUS_TOP_EVIDENCE", t0)
        best_data = corpus[best_doc_id]

        # Step 5: Evidence Grounding Lock (only cite opened documents)
        grounded_ids = [best_doc_id]
        answer_text = f"Synthesized from {best_doc_id}: {best_data['content']}"
        content_hash = hashlib.sha256(best_data["content"].encode("utf-8")).hexdigest()
        receipt = hashlib.sha256(f"{query}:{best_doc_id}:{content_hash}:{best_score:.6f}".encode("utf-8")).hexdigest()
        t1 = time.perf_counter_ns()

        return AnswerPacket(
            query=query,
            primary_answer=answer_text,
            grounded_evidence_ids=grounded_ids,
            query_receipt_sha=receipt,
            total_latency_ms=(t1 - t0) // 1_000_000,
            evidence_hashes={best_doc_id: content_hash},
        )

    @staticmethod
    def _valid_fast_path(hit: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(hit, dict) or hit.get("opened") is not True:
            return False
        artifact_id, content = hit.get("artifact_id"), hit.get("content")
        if not isinstance(artifact_id, str) or not artifact_id.strip() or not isinstance(content, str):
            return False
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return bool(content.strip()) and hit.get("provenance_sha") == expected

    @staticmethod
    def _abstain(query: str, reason: str, started_ns: int) -> AnswerPacket:
        elapsed = (time.perf_counter_ns() - started_ns) // 1_000_000
        receipt = hashlib.sha256(f"ABSTAIN:{query}:{reason}".encode("utf-8")).hexdigest()
        return AnswerPacket(query=query, primary_answer="", grounded_evidence_ids=[],
                            abstention_reason=reason, query_receipt_sha=receipt,
                            total_latency_ms=elapsed)
