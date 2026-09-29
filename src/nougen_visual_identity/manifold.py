"""Validated covariance helpers and scene-aware reference selection."""
import math
from typing import Any, Dict, List


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _validate_square_matrix(matrix: List[List[float]]) -> List[List[float]]:
    dimension = len(matrix)
    if any(not isinstance(row, list) or len(row) != dimension for row in matrix):
        raise ValueError("Covariance matrix must be square")
    return [[_finite_number(value, "covariance entry") for value in row] for row in matrix]


def compute_empirical_covariance(vectors: List[List[float]], centroid: List[float]) -> List[List[float]]:
    """Compute sample covariance around a finite centroid."""
    center = [_finite_number(value, "centroid value") for value in centroid]
    if not center:
        raise ValueError("Centroid must not be empty")
    checked = []
    for vector in vectors:
        row = [_finite_number(value, "embedding value") for value in vector]
        if len(row) != len(center):
            raise ValueError("Embedding and centroid dimensions must match")
        checked.append(row)

    dimension = len(center)
    if len(checked) < 2:
        return [[1.0 if i == j else 0.0 for j in range(dimension)] for i in range(dimension)]

    covariance = [[0.0] * dimension for _ in range(dimension)]
    for vector in checked:
        delta = [value - center[index] for index, value in enumerate(vector)]
        for row in range(dimension):
            for column in range(dimension):
                covariance[row][column] += delta[row] * delta[column]
    return [
        [value / (len(checked) - 1) for value in row]
        for row in covariance
    ]


def apply_shrinkage(cov: List[List[float]], shrinkage_lambda: float = 0.2) -> List[List[float]]:
    """Apply identity-target shrinkage with a finite coefficient in [0, 1]."""
    matrix = _validate_square_matrix(cov)
    coefficient = _finite_number(shrinkage_lambda, "shrinkage_lambda")
    if not 0.0 <= coefficient <= 1.0:
        raise ValueError("shrinkage_lambda must be in [0, 1]")
    dimension = len(matrix)
    return [
        [
            (1.0 - coefficient) * matrix[row][column]
            + coefficient * (1.0 if row == column else 0.0)
            for column in range(dimension)
        ]
        for row in range(dimension)
    ]


def invert_diagonal_approximation(cov: List[List[float]]) -> List[float]:
    """Invert diagonal variances for a diagonal Mahalanobis approximation."""
    matrix = _validate_square_matrix(cov)
    return [
        1.0 / matrix[index][index] if matrix[index][index] > 1e-6 else 1.0
        for index in range(len(matrix))
    ]


def mahalanobis_distance_diagonal(
    vector: List[float], centroid: List[float], inv_diag: List[float]
) -> float:
    """Compute a diagonal Mahalanobis distance after checking dimensions."""
    values = [_finite_number(value, "embedding value") for value in vector]
    center = [_finite_number(value, "centroid value") for value in centroid]
    inverse = [_finite_number(value, "inverse variance") for value in inv_diag]
    if not values or len(values) != len(center) or len(values) != len(inverse):
        raise ValueError("Embedding, centroid and inverse variance dimensions must match")
    if any(value < 0.0 for value in inverse):
        raise ValueError("Inverse variances must be non-negative")
    distance_squared = sum(
        ((value - center[index]) ** 2) * inverse[index]
        for index, value in enumerate(values)
    )
    return math.sqrt(distance_squared)


def scene_aware_reference_selection(
    references: List[Dict[str, Any]],
    target_yaw: float,
    target_pitch: float,
    max_refs: int = 4,
) -> List[Dict[str, Any]]:
    """Rank references by target view while retaining one identity anchor."""
    if isinstance(max_refs, bool) or not isinstance(max_refs, int) or max_refs < 1:
        raise ValueError("max_refs must be a positive integer")
    target_yaw = _finite_number(target_yaw, "target_yaw")
    target_pitch = _finite_number(target_pitch, "target_pitch")
    if not references:
        return []

    anchors = [reference for reference in references if reference.get("role") == "identity_anchor"]
    anchor = anchors[0] if anchors else references[0]
    candidates = [reference for reference in references if reference is not anchor]

    def score(reference: Dict[str, Any]) -> float:
        view = reference.get("view", {})
        if not isinstance(view, dict):
            raise ValueError("Reference view must be an object")
        yaw = _finite_number(view.get("yaw", 0.0), "reference yaw")
        pitch = _finite_number(view.get("pitch", 0.0), "reference pitch")
        quality = _finite_number(reference.get("quality", 1.0), "reference quality")
        if not 0.0 <= quality <= 1.0:
            raise ValueError("Reference quality must be in [0, 1]")
        return (abs(yaw - target_yaw) * 0.6 + abs(pitch - target_pitch) * 0.4) - quality * 10.0

    candidates.sort(key=score)
    return [anchor] + candidates[: max_refs - 1]
