"""Numerically guarded identity centroid and embedding distance helpers."""
import math
from typing import List, Tuple


def _validated_vector(vector: List[float], label: str) -> List[float]:
    if not vector:
        raise ValueError(f"{label} must not be empty")
    values = []
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label} must contain only finite numbers")
        values.append(float(value))
    return values


def l2_normalize(vector: List[float]) -> List[float]:
    """Return the L2-normalized vector, preserving an all-zero vector."""
    values = _validated_vector(vector, "vector")
    norm = math.hypot(*values)
    if norm == 0.0:
        return [0.0] * len(values)
    return [value / norm for value in values]


def _validate_batch(vectors: List[List[float]]) -> List[List[float]]:
    if not vectors:
        raise ValueError("At least one embedding is required")
    values = [_validated_vector(vector, "embedding") for vector in vectors]
    dimension = len(values[0])
    if any(len(vector) != dimension for vector in values):
        raise ValueError("All embeddings must have the same dimension")
    return values


def compute_identity_centroid(
    reference_vectors: List[List[float]],
    qualities: List[float],
    redundancies: List[float],
) -> List[float]:
    """Build a normalized centroid using quality times non-redundancy weights."""
    vectors = _validate_batch(reference_vectors)
    if len(vectors) != len(qualities) or len(vectors) != len(redundancies):
        raise ValueError("Vectors, qualities, and redundancies must have matching length")

    raw_weights = []
    for quality, redundancy in zip(qualities, redundancies):
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
            for value in (quality, redundancy)
        ):
            raise ValueError("Quality and redundancy values must be finite numbers in [0, 1]")
        raw_weights.append(float(quality) * (1.0 - float(redundancy)))

    total = sum(raw_weights)
    if total <= 0.0:
        raise ValueError("At least one reference must have positive quality and non-redundancy weight")
    weights = [weight / total for weight in raw_weights]
    weighted_sum = [
        sum(weight * l2_normalize(vector)[index] for vector, weight in zip(vectors, weights))
        for index in range(len(vectors[0]))
    ]
    centroid = l2_normalize(weighted_sum)
    if not any(centroid):
        raise ValueError("Cannot compute an identity centroid from zero vectors")
    return centroid


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity after validating compatible dimensions."""
    left = _validated_vector(v1, "left embedding")
    right = _validated_vector(v2, "right embedding")
    if len(left) != len(right):
        raise ValueError("Embeddings must have the same dimension")
    left_norm = math.hypot(*left)
    right_norm = math.hypot(*right)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum((a / left_norm) * (b / right_norm) for a, b in zip(left, right))


def identity_distance(candidate: List[float], centroid: List[float]) -> float:
    """Return one minus cosine similarity."""
    return 1.0 - cosine_similarity(candidate, centroid)


def compute_identity_drift_index(embeddings: List[List[float]]) -> Tuple[float, float, float]:
    """Return mean cosine similarity, population standard deviation, and drift."""
    if not embeddings:
        return 0.0, 0.0, 0.0
    vectors = _validate_batch(embeddings)
    centroid = l2_normalize(
        [sum(vector[index] for vector in vectors) for index in range(len(vectors[0]))]
    )
    if not any(centroid):
        return 0.0, 0.0, 1.0
    similarities = [cosine_similarity(vector, centroid) for vector in vectors]
    mean = sum(similarities) / len(similarities)
    variance = sum((value - mean) ** 2 for value in similarities) / len(similarities)
    drift = sum(1.0 - value for value in similarities) / len(similarities)
    return mean, math.sqrt(variance), drift
