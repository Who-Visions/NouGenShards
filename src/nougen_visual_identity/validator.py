"""Hard identity gates and Pareto selection for candidate render metrics."""
import math
from typing import Any, Dict, List


class IdentityValidator:
    """Evaluate normalized render metrics against configured hard limits."""

    def __init__(self, thresholds: Dict[str, float] = None, weights: Dict[str, float] = None):
        self.thresholds = {
            "identity_similarity_min": 0.85,
            "geometry_error_max": 0.12,
            "mark_error_max": 0.10,
            "hair_error_max": 0.15,
        }
        if thresholds:
            self.thresholds.update(thresholds)
        for value in self.thresholds.values():
            self._unit_value(value, "threshold")

        self.weights = {
            "identity": 0.35,
            "geometry": 0.20,
            "marks": 0.15,
            "hair": 0.10,
            "prompt": 0.10,
            "perceptual": 0.10,
            "artifact_penalty": 0.15,
        }
        if weights:
            self.weights.update(weights)
        for value in self.weights.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Weights must be finite non-negative numbers")
        if sum(self.weights.values()) <= 0:
            raise ValueError("At least one objective weight must be positive")

    @staticmethod
    def _unit_value(value: Any, label: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
        ):
            raise ValueError(f"{label} must be a finite number in [0, 1]")
        return float(value)

    def hard_gate(self, metrics: Dict[str, float]) -> bool:
        """Reject missing or invalid hard-gate metrics; aesthetics cannot override identity."""
        required = ("identity_similarity", "geometry_error", "mark_error", "hair_error")
        if any(key not in metrics for key in required):
            return False
        try:
            values = {key: self._unit_value(metrics[key], key) for key in required}
        except ValueError:
            return False
        return (
            values["identity_similarity"] >= self.thresholds["identity_similarity_min"]
            and values["geometry_error"] <= self.thresholds["geometry_error_max"]
            and values["mark_error"] <= self.thresholds["mark_error_max"]
            and values["hair_error"] <= self.thresholds["hair_error_max"]
        )

    def calculate_quality_score(self, metrics: Dict[str, float]) -> float:
        """Calculate a normalized weighted score; reject non-finite supplied metrics."""
        defaults = {
            "identity_similarity": 0.0,
            "geometry_error": 1.0,
            "mark_error": 1.0,
            "hair_error": 1.0,
            "prompt_alignment": 0.0,
            "perceptual_quality": 0.0,
            "artifact_score": 1.0,
        }
        values = dict(defaults)
        for key in defaults:
            if key in metrics:
                values[key] = self._unit_value(metrics[key], key)

        score = (
            self.weights["identity"] * values["identity_similarity"]
            + self.weights["geometry"] * (1.0 - values["geometry_error"])
            + self.weights["marks"] * (1.0 - values["mark_error"])
            + self.weights["hair"] * (1.0 - values["hair_error"])
            + self.weights["prompt"] * values["prompt_alignment"]
            + self.weights["perceptual"] * values["perceptual_quality"]
            - self.weights["artifact_penalty"] * values["artifact_score"]
        )
        return score / sum(self.weights.values())

    @staticmethod
    def pareto_select(
        candidates: List[Dict[str, Any]], objectives: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Return candidates not dominated on the requested normalized objectives."""
        if not candidates:
            return []
        objectives = objectives or [
            "identity_similarity",
            "perceptual_quality",
            "prompt_alignment",
        ]
        normalized = []
        for candidate in candidates:
            metrics = candidate.get("metrics", candidate)
            normalized.append(
                {
                    key: IdentityValidator._unit_value(metrics.get(key, 0.0), key)
                    for key in objectives
                }
            )

        frontier = []
        for index, candidate in enumerate(candidates):
            dominated = any(
                all(other[key] >= normalized[index][key] for key in objectives)
                and any(other[key] > normalized[index][key] for key in objectives)
                for other_index, other in enumerate(normalized)
                if other_index != index
            )
            if not dominated:
                frontier.append(candidate)
        return frontier
