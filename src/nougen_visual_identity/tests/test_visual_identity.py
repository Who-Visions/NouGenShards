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
import json
import shutil
from pathlib import Path
import pytest
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
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "synthetic_character"
    data = json.loads((fixture_dir / "capsule.json").read_text(encoding="utf-8"))
    capsule_dir = tmp_path / "test_tenant" / "synthetic_subject"
    shutil.copytree(fixture_dir / "references", capsule_dir / "references")
    capsule_dir.mkdir(parents=True, exist_ok=True)
    (capsule_dir / "capsule.json").write_text(json.dumps(data), encoding="utf-8")

    retriever = DeterministicIdentityRetriever(root_dir=str(tmp_path))
    capsule, confidence = retriever.retrieve("synthetic_subject", tenant_id="test_tenant")
    assert capsule is not None
    assert confidence == "HIGH"
    assert capsule["identity"]["character_id"] == "synthetic_subject"
    assert capsule["schema"] == "nougen.visual_identity.v2"
    assert len(capsule["references"]) == 2
    assert capsule["persistent_marks"][0]["mark_type"] == "scar"
    assert retriever.retrieve("synthetic_subject", tenant_id="other_tenant") == (None, "LOW")

    (capsule_dir / "references" / "front.ref").write_text("tampered", encoding="utf-8")
    assert retriever.retrieve("synthetic_subject", tenant_id="test_tenant") == (None, "LOW")


def test_retriever_rejects_unsafe_identifiers(tmp_path):
    retriever = DeterministicIdentityRetriever(root_dir=str(tmp_path))
    with pytest.raises(ValueError, match="character_id"):
        retriever.retrieve("../outside")
    with pytest.raises(ValueError, match="tenant_id"):
        retriever.retrieve("synthetic_subject", tenant_id="../outside")


def test_retriever_rejects_capsule_identity_mismatch(tmp_path):
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "synthetic_character"
    data = json.loads((fixture_dir / "capsule.json").read_text(encoding="utf-8"))
    data["identity"]["character_id"] = "different_subject"
    capsule_dir = tmp_path / "test_tenant" / "synthetic_subject"
    shutil.copytree(fixture_dir / "references", capsule_dir / "references")
    capsule_dir.mkdir(parents=True, exist_ok=True)
    (capsule_dir / "capsule.json").write_text(json.dumps(data), encoding="utf-8")
    retriever = DeterministicIdentityRetriever(root_dir=str(tmp_path))
    assert retriever.retrieve("synthetic_subject", tenant_id="test_tenant") == (None, "LOW")


def test_centroid_rejects_mismatched_dimensions_and_nonfinite_weights():
    with pytest.raises(ValueError, match="dimension"):
        compute_identity_centroid([[1.0, 0.0], [1.0]], [1.0, 1.0], [0.0, 0.0])
    with pytest.raises(ValueError, match="finite"):
        compute_identity_centroid([[1.0, 0.0]], [float("nan")], [0.0])


def test_hard_gate_rejects_nonfinite_metrics_and_score_rejects_invalid_ranges():
    validator = IdentityValidator()
    metrics = {
        "identity_similarity": float("nan"),
        "geometry_error": 0.0,
        "mark_error": 0.0,
        "hair_error": 0.0,
    }
    assert validator.hard_gate(metrics) is False
    with pytest.raises(ValueError, match="finite"):
        validator.calculate_quality_score({"identity_similarity": float("inf")})


def test_retriever_rejects_reference_path_escape(tmp_path):
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "synthetic_character"
    data = json.loads((fixture_dir / "capsule.json").read_text(encoding="utf-8"))
    data["references"][0]["uri"] = "../outside.ref"
    capsule_dir = tmp_path / "test_tenant" / "synthetic_subject"
    shutil.copytree(fixture_dir / "references", capsule_dir / "references")
    capsule_dir.mkdir(parents=True, exist_ok=True)
    (capsule_dir / "capsule.json").write_text(json.dumps(data), encoding="utf-8")
    retriever = DeterministicIdentityRetriever(root_dir=str(tmp_path))
    assert retriever.retrieve("synthetic_subject", tenant_id="test_tenant") == (None, "LOW")
