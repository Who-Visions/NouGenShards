r'''
Unlearning Elevated Mathematical Algorithm (Module: Knowledge Graph Geometry & Unlearning).
Elevates unlearning into formal graph flow dynamics, Riemannian Fisher Information projection,
and multi-source Bayes factor support calculation.

Mathematical Foundations:
1. Directed Acyclic Graph (DAG) Support Attenuation:
   Let $G = (V, E)$ be the provenance DAG. For target seed $s \in V$, the influence
   propagating along path $P = (s = v_0, v_1, \dots, v_k = v)$ is:
   $w(P) = \prod_{i=0}^{k-1} w(v_i, v_{i+1}) \cdot \frac{1}{1 + \gamma \cdot i}$
   where $\gamma > 0$ is the geodesic depth attenuation factor.

2. Generalized Capacity & Multi-Path Resistance (Kirchhoff Analog):
   $W_{eff}(s \to v) = 1 - \prod_{P \in \mathcal{P}(s, v)} (1 - w(P))$
   Aggregates multi-route propagation without overcounting redundant parallel paths.

3. Fisher Information / Subspace Orthogonalization (Projection Operator):
   Let $F_s$ be the Fisher Information matrix / direction of the retracted concept.
   The projection orthogonal to the unlearned concept subspace is:
   $P_{\perp s} = I - \frac{F_s F_s^T}{\|F_s\|^2}$
   Mitigates catastrophic forgetting of adjacent valid facts while zeroing out retracted manifold directions.

4. Bayesian Corroboration Odds & Independent Support Ratio:
   $\Lambda(v \mid \neg s) = \frac{P(v \mid \mathcal{S}_{\text{indep}})}{P(v \mid s)} \approx \prod_{f \in \mathcal{F}_{\text{indep}}} \left(1 + \beta \cdot \text{reliability}(f)\right)$
   Independent Support Ratio:
   $R_{indep}(v) = 1 - \exp\left( -\sum_{f \in \mathcal{F}_{\text{indep}}} \kappa_f \right)$

5. Unified Rigorous Dependency Score:
   $D(v, s) = W_{eff}(s \to v) \cdot (1 - R_{indep}(v)) \cdot \left(\alpha + (1 - \alpha) \cdot \text{Sim}_{trigram}(s, v)\right)$
   Bounded in $[0, 1]$.
'''

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class Disposition(str, Enum):
    KEEP = "KEEP"
    REVERIFY = "REVERIFY"
    QUARANTINE = "QUARANTINE"
    RETRACT = "RETRACT"
    FORGET = "FORGET"
    ERASE = "ERASE"


@dataclass
class MathematicalLineageNode:
    node_id: str
    depth: int = 0
    inbound_relation: str = "seed"
    effective_path_weight: float = 1.0
    trigram_similarity: float = 0.0
    independent_families: Set[str] = field(default_factory=set)
    independent_support_ratio: float = 0.0
    dependency_score: float = 0.0
    disposition: Disposition = Disposition.KEEP
    disposition_reason: str = ""


class UnlearningElevated:
    """
    Mathematical Graph Engine for Exact Lineage Attenuation, Multi-Path Resistance,
    and Orthogonal Subspace Protection.
    """
    def __init__(
        self,
        depth_decay_gamma: float = 0.30,
        similarity_weight_alpha: float = 0.50,
        erase_threshold: float = 0.65,
        quarantine_threshold: float = 0.35,
        keep_threshold: float = 0.20
    ):
        self.gamma = depth_decay_gamma
        self.alpha = similarity_weight_alpha
        self.erase_th = erase_threshold
        self.quarantine_th = quarantine_threshold
        self.keep_th = keep_threshold

    @staticmethod
    def compute_trigram_jaccard(text1: str, text2: str) -> float:
        """Calculates exact Jaccard similarity over character trigrams."""
        t1 = text1.strip().lower()
        t2 = text2.strip().lower()
        if len(t1) < 3 or len(t2) < 3:
            return 1.0 if t1 == t2 and t1 else 0.0

        grams1 = {t1[i:i+3] for i in range(len(t1) - 2)}
        grams2 = {t2[i:i+3] for i in range(len(t2) - 2)}
        intersection = len(grams1 & grams2)
        union = len(grams1 | grams2)
        return intersection / union if union > 0 else 0.0

    def compute_multipath_effective_weight(self, path_weights: List[float]) -> float:
        """
        Combines independent parallel path weights using probability of at least one path:
        W_eff = 1 - product(1 - w_i).
        Ensures parallel derivations aggregate monotonically without exceeding 1.0.
        """
        if not path_weights:
            return 0.0
        complement_prod = 1.0
        for w in path_weights:
            clamped = max(0.0, min(1.0, w))
            complement_prod *= (1.0 - clamped)
        return 1.0 - complement_prod

    def compute_independent_support_ratio(self, independent_families: Set[str], weight_per_family: float = 1.0) -> float:
        """
        Computes saturating Bayesian support ratio:
        R_indep = 1 - exp(- sum_k w_k).
        0 families -> 0.0
        1 family -> 1 - e^-1 = 0.632
        2 families -> 1 - e^-2 = 0.865
        3 families -> 1 - e^-3 = 0.950
        """
        if not independent_families:
            return 0.0
        k = len(independent_families) * weight_per_family
        return 1.0 - math.exp(-k)

    def compute_dependency_score(
        self,
        effective_path_weight: float,
        independent_support_ratio: float,
        semantic_similarity: float
    ) -> float:
        """
        Computes formal dependency score:
        D(v, s) = W_eff * (1 - R_indep) * (alpha + (1 - alpha) * Sim)
        """
        sim_factor = self.alpha + (1.0 - self.alpha) * max(0.0, min(1.0, semantic_similarity))
        dep = effective_path_weight * (1.0 - independent_support_ratio) * sim_factor
        return max(0.0, min(1.0, dep))

    def classify_disposition(
        self,
        dep_score: float,
        independent_families_count: int
    ) -> Tuple[Disposition, str]:
        """
        Determines mathematical disposition based on strict thresholds.
        """
        if independent_families_count >= 2 and dep_score < self.quarantine_th:
            return (
                Disposition.KEEP,
                f"Multi-source independent corroboration preserved ({independent_families_count} families). DepScore={dep_score:.3f}"
            )
        if dep_score >= self.erase_th:
            return (
                Disposition.ERASE,
                f"Severe path dependency without sufficient independent support. DepScore={dep_score:.3f} >= {self.erase_th}"
            )
        if dep_score >= self.quarantine_th:
            return (
                Disposition.QUARANTINE,
                f"Moderate dependency requiring verification quarantine. DepScore={dep_score:.3f}"
            )
        if dep_score < self.keep_threshold_or_equal():
            return (
                Disposition.KEEP,
                f"Negligible lineage dependency. DepScore={dep_score:.3f} < {self.keep_th}"
            )
        return (
            Disposition.REVERIFY,
            f"Lineage attenuation requires epistemic reverification. DepScore={dep_score:.3f}"
        )

    def keep_threshold_or_equal(self) -> float:
        return self.keep_th

    def project_orthogonal_subspace(self, target_embedding: List[float], retract_embedding: List[float]) -> List[float]:
        """
        Projects target_embedding onto the orthogonal complement of retract_embedding:
        v_proj = v - (v . u) * u, where u = r / ||r||.
        Guarantees zero cosine similarity with retracted concept direction.
        """
        norm_r = math.sqrt(sum(x * x for x in retract_embedding))
        if norm_r == 0.0:
            return list(target_embedding)

        u = [x / norm_r for x in retract_embedding]
        dot = sum(v * ui for v, ui in zip(target_embedding, u))

        # v_proj = v - dot * u
        proj = [v - dot * ui for v, ui in zip(target_embedding, u)]
        return proj
