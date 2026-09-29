"""
NouGen Multi-Modal Identity Manifold & Covariance Math
Implements Mahalanobis distance, shrinkage covariance, and scene-aware reference selection.
"""
import math
from typing import List, Dict, Any

def compute_empirical_covariance(vectors: List[List[float]], centroid: List[float]) -> List[List[float]]:
    """Compute sample covariance matrix \Sigma = \frac{1}{n-1} \sum (e_i - \mu)(e_i - \mu)^T."""
    n = len(vectors)
    if n < 2:
        dim = len(centroid)
        return [[1.0 if i == j else 0.0 for j in range(dim)] for i in range(dim)]

    dim = len(centroid)
    cov = [[0.0] * dim for _ in range(dim)]
    for v in vectors:
        diff = [v[d] - centroid[d] for d in range(dim)]
        for i in range(dim):
            for j in range(dim):
                cov[i][j] += diff[i] * diff[j]

    for i in range(dim):
        for j in range(dim):
            cov[i][j] /= (n - 1)
    return cov

def apply_shrinkage(cov: List[List[float]], shrinkage_lambda: float = 0.2) -> List[List[float]]:
    """Apply Ledoit-Wolf-style shrinkage \Sigma' = (1 - \lambda)\Sigma + \lambda I."""
    dim = len(cov)
    shrunk = [[0.0] * dim for _ in range(dim)]
    for i in range(dim):
        for j in range(dim):
            diag = 1.0 if i == j else 0.0
            shrunk[i][j] = (1.0 - shrinkage_lambda) * cov[i][j] + shrinkage_lambda * diag
    return shrunk

def invert_diagonal_approximation(cov: List[List[float]]) -> List[float]:
    """Invert diagonal variances for robust high-dimensional Mahalanobis distance."""
    dim = len(cov)
    inv_diag = []
    for i in range(dim):
        var = cov[i][i]
        inv_diag.append(1.0 / var if var > 1e-6 else 1.0)
    return inv_diag

def mahalanobis_distance_diagonal(vector: List[float], centroid: List[float], inv_diag: List[float]) -> float:
    """Compute D_M(e) = \sqrt{ \sum (e_i - \mu_i)^2 * inv_diag_i }."""
    diff_sq_sum = 0.0
    for v, c, inv_v in zip(vector, centroid, inv_diag):
        diff = v - c
        diff_sq_sum += (diff * diff) * inv_v
    return math.sqrt(max(0.0, diff_sq_sum))

def scene_aware_reference_selection(
    references: List[Dict[str, Any]],
    target_yaw: float,
    target_pitch: float,
    max_refs: int = 4
) -> List[Dict[str, Any]]:
    """
    Scene-aware selection: picks references nearest target geometry (yaw/pitch)
    while strictly retaining at least one primary identity anchor.
    """
    if not references:
        return []

    # 1. Identify primary anchor
    anchors = [r for r in references if r.get("role") == "identity_anchor"]
    primary_anchor = anchors[0] if anchors else references[0]

    # 2. Score remaining candidates by angular distance D = \alpha |yaw - t_yaw| + \beta |pitch - t_pitch|
    candidates = [r for r in references if r != primary_anchor]
    
    def score_ref(ref):
        v = ref.get("view", {})
        d_yaw = abs(v.get("yaw", 0.0) - target_yaw)
        d_pitch = abs(v.get("pitch", 0.0) - target_pitch)
        q = ref.get("quality", 1.0)
        return (d_yaw * 0.6 + d_pitch * 0.4) - (q * 10.0)

    candidates.sort(key=score_ref)
    selected = [primary_anchor] + candidates[:max_refs - 1]
    return selected
