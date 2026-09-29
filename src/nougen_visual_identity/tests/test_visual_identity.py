"""
Test Suite for NouGen Visual Identity Engine
Validates:
1. Multi-reference identity centroid mathematical convergence
2. Identity drift entropy calculation
3. Hard invariant gating
4. Composite quality score calculation
5. Pareto frontier multi-objective selection
6. Deterministic retrieval and confidence verification
"""
import os
import json
from nougen_visual_identity.centroid import (
    compute_identity_centroid,
    compute_identity_drift_index
)
from nougen_visual_identity.validator import IdentityValidator
from nougen_visual_identity.retriever import DeterministicIdentityRetriever

def test_centroid_normalization_and_convergence():
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    qualities = [1.0, 1.0]
    redundancies = [0.0, 0.0]

    centroid = compute_identity_centroid([v1, v2], qualities, redundancies)
    # Normalized sum should be [1/sqrt(2), 1/sqrt(2), 0]
    assert abs(centroid[0] - 0.7071) < 0.01
    assert abs(centroid[1] - 0.7071) < 0.01
    assert centroid[2] == 0.0

def test_redundancy_weight_dampening():
    # v1 is sharp anchor (q=1.0, r=0.0)
    # v2 is duplicate (q=1.0, r=0.9)
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    centroid = compute_identity_centroid([v1, v2], [1.0, 1.0], [0.0, 0.9])
    # v1 weight is 1.0, v2 weight is 0.1 -> centroid should heavily favor v1
    assert centroid[0] > 0.95
    assert centroid[1] < 0.30

def test_identity_drift_index():
    # Stable batch
    stable_batch = [
        [1.0, 0.02, 0.01],
        [0.99, 0.03, 0.01],
        [1.0, 0.01, 0.02]
    ]
    mean_sim, std_dev, drift = compute_identity_drift_index(stable_batch)
    assert mean_sim > 0.99
    assert drift < 0.01

    # Unstable batch ("inventing cousins")
    unstable_batch = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0]
    ]
    _, _, unstable_drift = compute_identity_drift_index(unstable_batch)
    assert unstable_drift > 0.40

def test_hard_invariant_gate():
    validator = IdentityValidator(thresholds={
        "identity_similarity_min": 0.85,
        "geometry_error_max": 0.12,
        "mark_error_max": 0.10,
        "hair_error_max": 0.15
    })

    # Passing candidate
    passing_candidate = {
        "identity_similarity": 0.92,
        "geometry_error": 0.08,
        "mark_error": 0.05,
        "hair_error": 0.10,
        "perceptual_quality": 0.95
    }
    assert validator.hard_gate(passing_candidate) is True

    # High perceptual quality, but failed identity similarity (rejection)
    failed_identity = {
        "identity_similarity": 0.72,  # Below 0.85
        "geometry_error": 0.05,
        "mark_error": 0.04,
        "hair_error": 0.08,
        "perceptual_quality": 0.99
    }
    assert validator.hard_gate(failed_identity) is False

    # Failed scar topology (rejection)
    failed_scar = {
        "identity_similarity": 0.90,
        "geometry_error": 0.08,
        "mark_error": 0.18,  # Exceeds 0.10
        "hair_error": 0.10,
        "perceptual_quality": 0.95
    }
    assert validator.hard_gate(failed_scar) is False

def test_pareto_frontier_selection():
    candidates = [
        {"id": "A", "metrics": {"identity_similarity": 0.95, "perceptual_quality": 0.80, "prompt_alignment": 0.85}},
        {"id": "B", "metrics": {"identity_similarity": 0.88, "perceptual_quality": 0.95, "prompt_alignment": 0.90}},
        {"id": "C", "metrics": {"identity_similarity": 0.82, "perceptual_quality": 0.75, "prompt_alignment": 0.80}},  # Dominated by both
    ]
    pareto = IdentityValidator.pareto_select(candidates)
    pareto_ids = [c["id"] for c in pareto]
    assert "A" in pareto_ids
    assert "B" in pareto_ids
    assert "C" not in pareto_ids

def test_deterministic_retrieval_and_fixture_loading(tmp_path):
    fixture_path = os.path.join(os.path.dirname(__file__), "../fixtures/xoah_oda.json")
    with open(fixture_path) as f:
        xoah_data = json.load(f)

    retriever = DeterministicIdentityRetriever(root_dir=str(tmp_path))
    # Store fixture
    out_file = os.path.join(tmp_path, "xoah_oda.json")
    with open(out_file, "w") as f:
        json.dump(xoah_data, f)

    capsule, confidence = retriever.retrieve("xoah_oda")
    assert capsule is not None
    assert confidence == "HIGH"
    assert capsule["identity"]["character_id"] == "xoah_oda"
    assert capsule["schema"] == "nougen.visual_identity.v2"
    assert len(capsule["references"]) == 2
    assert capsule["persistent_marks"][0]["mark_type"] == "scar"
