"""
Elevated Cluster Relevance Reranking & Vector Routing Subsystem.
Extends core.py with blended cosine relevance tensors and routing index health metrics.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, List

MAX_DB_COUNT = 9



@dataclass
class RelevanceTensor:
    """Multi-signal relevance score tensor for shard search results."""
    bm25_score: float = 0.0
    cosine_similarity: float = 0.0
    utility_score: float = 0.0

    def blended_score(
        self,
        w_bm25: float = 0.4,
        w_cosine: float = 0.4,
        w_utility: float = 0.2
    ) -> float:
        """Calculates normalized weighted blend."""
        score = (
            w_bm25 * self.bm25_score +
            w_cosine * self.cosine_similarity +
            w_utility * min(1.0, self.utility_score / 100.0)
        )
        return round(score, 4)


def compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Computes cosine similarity between two vector embeddings."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return round(dot_product / (norm_a * norm_b), 4)


def compute_routing_distribution(hashes: List[str]) -> Dict[int, int]:
    """Computes distribution of shard hashes across the 9 database partitions."""
    counts = {i: 0 for i in range(1, MAX_DB_COUNT + 1)}
    for h in hashes:
        try:
            idx = (int(h, 16) % MAX_DB_COUNT) + 1
        except ValueError:
            idx = (int(hashlib.md5(h.encode()).hexdigest(), 16) % MAX_DB_COUNT) + 1
        counts[idx] = counts.get(idx, 0) + 1
    return counts
