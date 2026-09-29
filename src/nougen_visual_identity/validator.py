"""
NouGen Multi-Modal Identity Validator & Gate Engine
Implements Hard Invariant Gating, Quality Objective, and Pareto Frontier Selection.
"""
from typing import Dict, List, Any

class IdentityValidator:
    """Evaluates candidate renders against visual identity capsule specifications."""

    def __init__(self, thresholds: Dict[str, float] = None, weights: Dict[str, float] = None):
        self.thresholds = thresholds or {
            "identity_similarity_min": 0.85,
            "geometry_error_max": 0.12,
            "mark_error_max": 0.10,
            "hair_error_max": 0.15
        }
        self.weights = weights or {
            "identity": 0.35,
            "geometry": 0.20,
            "marks": 0.15,
            "hair": 0.10,
            "prompt": 0.10,
            "perceptual": 0.10,
            "artifact_penalty": 0.15
        }

    def hard_gate(self, metrics: Dict[str, float]) -> bool:
        """
        Hard Invariant Gate: PASS_id = 1[ S_id >= tau_id AND D_geo <= tau_geo AND D_mark <= tau_mark ]
        Candidate is rejected if any hard constraint fails, regardless of aesthetic quality.
        """
        if metrics.get("identity_similarity", 0.0) < self.thresholds.get("identity_similarity_min", 0.85):
            return False
        if metrics.get("geometry_error", 1.0) > self.thresholds.get("geometry_error_max", 0.12):
            return False
        if metrics.get("mark_error", 1.0) > self.thresholds.get("mark_error_max", 0.10):
            return False
        if metrics.get("hair_error", 1.0) > self.thresholds.get("hair_error_max", 0.15):
            return False
        return True

    def calculate_quality_score(self, metrics: Dict[str, float]) -> float:
        """
        Candidate quality objective J:
        J = w_id * S_id + w_geo * (1 - D_geo) + w_marks * (1 - D_marks) + w_hair * (1 - D_hair)
            + w_prompt * S_prompt + w_perceptual * Q_perceptual - w_artifact * A_artifact
        """
        w = self.weights
        m = metrics
        score = (
            w["identity"] * m.get("identity_similarity", 0.0) +
            w["geometry"] * (1.0 - m.get("geometry_error", 0.0)) +
            w["marks"] * (1.0 - m.get("mark_error", 0.0)) +
            w["hair"] * (1.0 - m.get("hair_error", 0.0)) +
            w["prompt"] * m.get("prompt_alignment", 0.0) +
            w["perceptual"] * m.get("perceptual_quality", 0.0) -
            w["artifact_penalty"] * m.get("artifact_score", 0.0)
        )
        return score

    @staticmethod
    def pareto_select(candidates: List[Dict[str, Any]], objectives: List[str] = None) -> List[Dict[str, Any]]:
        """
        Multi-objective Pareto Frontier Selection.
        A candidate 'a' dominates 'b' iff:
        f_i(a) >= f_i(b) for all i AND exists j such that f_j(a) > f_j(b).
        """
        if not candidates:
            return []
        
        objectives = objectives or ["identity_similarity", "perceptual_quality", "prompt_alignment"]
        pareto_front = []

        for i, cand_a in enumerate(candidates):
            dominated = False
            metrics_a = cand_a.get("metrics", cand_a)
            for j, cand_b in enumerate(candidates):
                if i == j:
                    continue
                metrics_b = cand_b.get("metrics", cand_b)
                
                # Check if b dominates a
                b_ge_all = all(metrics_b.get(obj, 0.0) >= metrics_a.get(obj, 0.0) for obj in objectives)
                b_gt_one = any(metrics_b.get(obj, 0.0) > metrics_a.get(obj, 0.0) for obj in objectives)
                
                if b_ge_all and b_gt_one:
                    dominated = True
                    break
            
            if not dominated:
                pareto_front.append(cand_a)

        return pareto_front
