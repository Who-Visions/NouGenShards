"""Universal Deterministic Information-Gain Primitive for NouGenShards.

Mathematical Formulation:
    Let memory state M be a corpus of observed entities, features, or n-grams.
    The prior probability of feature f in memory is:
        P_M(f) = (count_M(f) + alpha) / (N_M + alpha * |V|)
    
    The conditional information gain Delta_I of an incoming event E given M is:
        Delta_I(E | M) = sum_{f in E} Q_E(f) * [-log2 P_M(f)]
    
    Normalized Information Gain:
        G(E | M) = (Delta_I(E | M) - I_min) / (I_max - I_min) in [0.0, 1.0]

Properties:
    - Repeated / identical information approaches marginal gain ~ 0.0.
    - Genuinely state-changing information approaches marginal gain ~ 1.0.
    - Explicit provenance separation: raw_observation, inferred_relationship,
      and action_recommendation remain strictly isolated.
"""
from __future__ import annotations

import collections
import dataclasses
import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple


TOKEN_RE = re.compile(r"\b[a-zA-Z0-9_\-\.]{2,}\b")


def tokenize(text: str) -> List[str]:
    """Deterministic token extraction for feature representation."""
    return [t.lower() for t in TOKEN_RE.findall(text)]


@dataclasses.dataclass(frozen=True)
class ProvenanceEnvelopes:
    raw_observation: Dict[str, Any]
    inferred_relationship: Dict[str, Any]
    action_recommendation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_observation": self.raw_observation,
            "inferred_relationship": self.inferred_relationship,
            "action_recommendation": self.action_recommendation,
        }


class InformationGainState:
    """State tracker for the memory corpus vocabulary and feature distributions."""

    def __init__(self, alpha: float = 1.0, dedup_threshold: float = 0.15, beacon_threshold: float = 0.80):
        self.alpha = max(1e-6, alpha)
        self.dedup_threshold = dedup_threshold
        self.beacon_threshold = beacon_threshold
        self.counts: collections.Counter[str] = collections.Counter()
        self.total_tokens: int = 0
        self.seen_hashes: Set[str] = set()

    def update(self, text: str) -> None:
        """Incorporate a text block into the background memory state."""
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.seen_hashes.add(h)
        tokens = tokenize(text)
        self.counts.update(tokens)
        self.total_tokens += len(tokens)

    def evaluate(self, event_text: str, confidence: float = 1.0) -> ProvenanceEnvelopes:
        """Calculate conditional information gain Delta_I(event | memory_state)
        and project onto the 6 fleet operational vectors.
        """
        tokens = tokenize(event_text)
        token_count = len(tokens)
        h = hashlib.sha256(event_text.encode("utf-8")).hexdigest()
        is_exact_duplicate = h in self.seen_hashes

        vocab_size = max(10, len(self.counts))
        denom = self.total_tokens + (self.alpha * vocab_size)

        if token_count == 0 or is_exact_duplicate:
            delta_i = 0.0
            norm_gain = 0.0
        else:
            event_counts = collections.Counter(tokens)
            unseen_tokens = sum(cnt for tok, cnt in event_counts.items() if self.counts[tok] == 0)
            unseen_ratio = unseen_tokens / token_count

            # Max surprisal corresponds to completely novel tokens
            max_surprisal = -math.log2(self.alpha / denom)
            min_surprisal = -math.log2(max(self.counts.values(), default=1) / max(1, self.total_tokens))

            surprisal_sum = 0.0
            for tok, cnt in event_counts.items():
                p_m = (self.counts[tok] + self.alpha) / denom
                surprisal = -math.log2(p_m)
                weight = cnt / token_count
                surprisal_sum += weight * surprisal

            delta_i = surprisal_sum

            # When all tokens are known in memory, gain is strictly bounded by background frequency
            if unseen_ratio == 0.0:
                freq_ratio = sum(self.counts[tok] for tok in event_counts) / (len(event_counts) * max(1, self.total_tokens))
                norm_gain = max(0.01, min(0.30, 0.30 * (1.0 - min(1.0, freq_ratio * 5))))
            else:
                norm_gain = min(1.0, (0.65 * unseen_ratio) + (0.35 * min(1.0, delta_i / max_surprisal)))

        # 1. Novelty Scoring
        novelty_score = round(norm_gain, 4)

        # 2. Deduplication Verdict
        if is_exact_duplicate or norm_gain < self.dedup_threshold:
            dedup_verdict = "duplicate"
        elif norm_gain < 0.40:
            dedup_verdict = "marginal"
        else:
            dedup_verdict = "novel"

        # 3. Retrieval Ranking Boost
        retrieval_boost = round(1.0 + (novelty_score * 0.5), 4)

        # 4. Causal / Provenance Edge Weight
        edge_weight = round(novelty_score * max(0.0, min(1.0, confidence)), 4)

        # 5. Relay Urgency
        if novelty_score >= self.beacon_threshold:
            relay_urgency = "beacon"
        elif novelty_score >= 0.45:
            relay_urgency = "elevated"
        else:
            relay_urgency = "routine"

        # 6. Action Gating
        action_allowed = novelty_score >= self.dedup_threshold and not is_exact_duplicate

        raw_observation = {
            "hash": h,
            "token_count": token_count,
            "is_exact_seen": is_exact_duplicate,
            "provenance_layer": "raw_observation",
        }

        inferred_relationship = {
            "conditional_information_gain_bits": round(delta_i, 4),
            "normalized_information_gain": novelty_score,
            "novelty_score": novelty_score,
            "retrieval_boost": retrieval_boost,
            "edge_weight": edge_weight,
            "is_inferred": True,
            "provenance_layer": "inferred_relationship",
        }

        action_recommendation = {
            "deduplication_verdict": dedup_verdict,
            "relay_urgency": relay_urgency,
            "action_allowed": action_allowed,
            "is_recommendation": True,
            "provenance_layer": "action_recommendation",
        }

        return ProvenanceEnvelopes(
            raw_observation=raw_observation,
            inferred_relationship=inferred_relationship,
            action_recommendation=action_recommendation,
        )
