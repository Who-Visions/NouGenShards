"""
Unit tests for UnlearningElevated mathematical dynamics.
Tests DAG attenuation, multi-path Kirchhoff effective weight, saturating Bayesian support ratio,
dependency score thresholds, and orthogonal subspace projection.
"""

import math
import pytest
from nougen_shards.unlearning_elevated import (
    UnlearningElevated,
    Disposition
)


def test_trigram_jaccard_exact():
    engine = UnlearningElevated()
    # Identical strings
    assert engine.compute_trigram_jaccard("hardcade verifier", "hardcade verifier") == 1.0
    # Completely disjoint
    assert engine.compute_trigram_jaccard("abcdef", "123456") == 0.0
    # Partial overlap
    sim = engine.compute_trigram_jaccard("nougen engine", "nougen shards")
    assert 0.0 < sim < 1.0


def test_multipath_effective_weight():
    engine = UnlearningElevated()
    # Empty
    assert engine.compute_multipath_effective_weight([]) == 0.0
    # Single path 0.5
    assert engine.compute_multipath_effective_weight([0.5]) == 0.5
    # Two independent parallel paths of weight 0.5: 1 - (1 - 0.5)*(1 - 0.5) = 1 - 0.25 = 0.75
    eff = engine.compute_multipath_effective_weight([0.5, 0.5])
    assert pytest.approx(eff, rel=1e-3) == 0.75
    # Clamped bounds
    assert engine.compute_multipath_effective_weight([1.0, 0.5]) == 1.0


def test_saturating_independent_support_ratio():
    engine = UnlearningElevated()
    # Zero families
    assert engine.compute_independent_support_ratio(set()) == 0.0
    # 1 family
    r1 = engine.compute_independent_support_ratio({"family_arxiv"})
    assert pytest.approx(r1, rel=1e-3) == 1.0 - math.exp(-1.0)
    # 2 families
    r2 = engine.compute_independent_support_ratio({"family_arxiv", "family_github"})
    assert pytest.approx(r2, rel=1e-3) == 1.0 - math.exp(-2.0)
    assert r2 > r1


def test_dependency_score_and_disposition():
    engine = UnlearningElevated(erase_threshold=0.65, quarantine_threshold=0.35, keep_threshold=0.20)

    # Case A: Heavy path weight, zero independent corroboration, high similarity -> ERASE
    score_erase = engine.compute_dependency_score(
        effective_path_weight=0.90,
        independent_support_ratio=0.0,
        semantic_similarity=0.80
    )
    # 0.90 * (1 - 0) * (0.5 + 0.5*0.8) = 0.90 * 0.90 = 0.81
    assert pytest.approx(score_erase, rel=1e-3) == 0.81
    disp_a, _ = engine.classify_disposition(score_erase, independent_families_count=0)
    assert disp_a == Disposition.ERASE

    # Case B: Multi-source independent corroboration (2 families) -> KEEP
    disp_b, _ = engine.classify_disposition(0.25, independent_families_count=2)
    assert disp_b == Disposition.KEEP


def test_orthogonal_subspace_projection():
    engine = UnlearningElevated()
    # Let retract direction be along x-axis: [1.0, 0.0]
    retract_vec = [1.0, 0.0]
    # Target vector with both x and y components: [3.0, 4.0]
    target_vec = [3.0, 4.0]

    projected = engine.project_orthogonal_subspace(target_vec, retract_vec)
    # The projected vector must have 0 component along retract_vec: [0.0, 4.0]
    assert pytest.approx(projected[0], abs=1e-6) == 0.0
    assert pytest.approx(projected[1], abs=1e-6) == 4.0

    # Dot product of projected with retract_vec must be 0 (strictly orthogonal)
    dot = sum(p * r for p, r in zip(projected, retract_vec))
    assert pytest.approx(dot, abs=1e-6) == 0.0
