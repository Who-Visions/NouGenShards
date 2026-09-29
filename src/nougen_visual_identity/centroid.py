"""
NouGen Multi-Reference Identity Centroid and Mathematical Formulations
"""
import math
from typing import List, Tuple

def l2_normalize(vector: List[float]) -> List[float]:
    """Compute normalized vector \hat{e} = e / ||e||_2."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return [0.0] * len(vector)
    return [x / norm for x in vector]

def compute_identity_centroid(reference_vectors: List[List[float]], 
                              qualities: List[float], 
                              redundancies: List[float]) -> List[float]:
    """
    Construct multi-reference identity centroid:
    \mu = \frac{ \sum w_i \hat{e}_i }{ || \sum w_i \hat{e}_i ||_2 }
    where w_i = \frac{ q_i(1-r_i) }{ \sum_j q_j(1-r_j) }
    """
    if not reference_vectors:
        raise ValueError("Cannot compute centroid from empty reference vectors.")
    if len(reference_vectors) != len(qualities) or len(reference_vectors) != len(redundancies):
        raise ValueError("Vectors, qualities, and redundancies must have matching length.")

    # 1. Compute raw weights: q_i * (1 - r_i)
    raw_weights = [max(0.0, q * (1.0 - r)) for q, r in zip(qualities, redundancies)]
    weight_sum = sum(raw_weights)
    if weight_sum == 0.0:
        # Fallback to uniform if all weights degenerate
        weights = [1.0 / len(raw_weights)] * len(raw_weights)
    else:
        weights = [w / weight_sum for w in raw_weights]

    dim = len(reference_vectors[0])
    weighted_sum = [0.0] * dim

    # 2. Accumulate normalized vectors with weights
    for v, w in zip(reference_vectors, weights):
        norm_v = l2_normalize(v)
        for d in range(dim):
            weighted_sum[d] += w * norm_v[d]

    # 3. Final L2 normalization
    return l2_normalize(weighted_sum)

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    n1 = l2_normalize(v1)
    n2 = l2_normalize(v2)
    return sum(a * b for a, b in zip(n1, n2))

def identity_distance(candidate: List[float], centroid: List[float]) -> float:
    """Identity distance D_id = 1 - S_id."""
    return 1.0 - cosine_similarity(candidate, centroid)

def compute_identity_drift_index(embeddings: List[List[float]]) -> Tuple[float, float, float]:
    """
    Compute Identity Drift Index (Identity Entropy):
    H_I = (1/n) * \sum (1 - cos(e_i, \mu))
    Returns: (mean_similarity, std_dev, drift_index)
    """
    if not embeddings:
        return 0.0, 0.0, 0.0
    
    # Compute centroid of the batch
    centroid = l2_normalize([sum(col) for col in zip(*embeddings)])
    sims = [cosine_similarity(e, centroid) for e in embeddings]
    mean_sim = sum(sims) / len(sims)
    variance = sum((s - mean_sim) ** 2 for s in sims) / len(sims)
    std_dev = math.sqrt(variance)
    drift_index = sum(1.0 - s for s in sims) / len(sims)
    return mean_sim, std_dev, drift_index
