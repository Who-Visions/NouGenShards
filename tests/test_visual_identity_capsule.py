import json
import math
from pathlib import Path

from nougen_shards.visual_identity_adapters import (
    FluxIdentityAdapter,
    IdentityCompiler,
    SDXLIdentityAdapter,
    VeoIdentityAdapter,
)
from nougen_shards.visual_identity_capsule import (
    IdentityRoot,
    IdentityVariant,
    calculate_identity_confidence,
    compute_weighted_centroid,
    find_pareto_frontier,
    score_candidate,
    select_capsule,
    validate_capsule,
)

FIXTURES = Path(__file__).parent / "fixtures" / "visual_identity"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_capsule_fixture_preserves_evidence_classes_and_validates_asset_binding():
    capsule = fixture("base.json")
    digests = {ref["asset_id"]: ref["sha256"] for ref in capsule["references"]}
    assert validate_capsule(capsule, known_assets=digests) == []
    assert {claim["evidence_class"] for claim in capsule["identity"]["claims"]} == {
        "reference_observation", "narrative_canon", "generated_interpretation"
    }
    assert validate_capsule(capsule, known_assets={"asset:front": "0" * 64})


def test_exact_tenant_character_lookup_uses_latest_non_retracted_revision():
    first = fixture("base.json")
    superseded = {**first, "capsule_id": "capsule:sample-1:r2", "revision": 2, "state": "retracted", "retraction_reason": "test"}
    wrong_character = fixture("other_character.json")
    assert select_capsule([wrong_character, superseded, first], tenant_id="tenant:sample-a", character_id="character:sample-1") is first
    assert select_capsule([first], tenant_id="tenant:other", character_id="character:sample-1") is None


def test_candidate_score_cannot_override_failed_hard_invariant():
    result = score_candidate({"identity": 0.1, "geometry": 0.2}, hard_invariants={"required_reference": True, "scar_topology": False})
    assert result.accepted is False
    assert result.score == 0.86
    assert result.failures == ("scar_topology",)


def test_invalid_vectors_and_unprovenanced_claims_are_rejected():
    capsule = fixture("base.json")
    capsule["identity"]["embedding"]["centroid"] = [3.0, 0.0]
    capsule["identity"]["embedding"]["dimension"] = 2
    capsule["identity"]["claims"][0]["source_ids"] = []
    issues = validate_capsule(capsule)
    assert any("L2-normalized" in item.message for item in issues)
    assert any("explicit provenance" in item.message for item in issues)


def test_malformed_external_values_return_issues_instead_of_raising():
    capsule = fixture("base.json")
    capsule["unexpected"] = True
    capsule["identity"]["claims"] = None
    capsule["identity"]["embedding"]["reference_asset_ids"] = None
    assert validate_capsule(capsule)
    result = score_candidate({"identity": "not-a-distance"}, hard_invariants={})
    assert result.accepted is False
    assert "metrics must include finite 0..1 distances" in result.failures


def test_retraction_requires_a_reason_and_unknown_state_is_rejected():
    capsule = fixture("base.json")
    capsule["state"] = "withdrawn"
    issues = validate_capsule(capsule)
    assert any(item.path == "state" for item in issues)
    capsule["state"] = "retracted"
    assert any(item.path == "retraction_reason" for item in validate_capsule(capsule))


def test_compute_weighted_centroid_math():
    e1 = [1.0, 0.0, 0.0]
    e2 = [0.0, 1.0, 0.0]
    q = [0.9, 0.9]
    r = [0.0, 0.0]
    centroid = compute_weighted_centroid([e1, e2], q, r)
    assert len(centroid) == 3
    assert abs(centroid[0] - centroid[1]) < 1e-5
    mag = math.sqrt(sum(x ** 2 for x in centroid))
    assert abs(mag - 1.0) < 1e-4

    # Redundancy penalty test: e2 is 80% redundant
    centroid_penalized = compute_weighted_centroid([e1, e2], [0.9, 0.9], [0.0, 0.8])
    assert centroid_penalized[0] > centroid_penalized[1]


def test_calculate_identity_confidence_ladder():
    low = calculate_identity_confidence(1, angle_coverage=0.2, expression_coverage=0.1, geometry_confidence=0.5)
    assert low["confidence_level"] == "limited"
    assert low["confidence_score"] < 0.50

    high = calculate_identity_confidence(10, angle_coverage=0.9, expression_coverage=0.8, geometry_confidence=0.95)
    assert high["confidence_level"] == "strong"
    assert high["confidence_score"] >= 0.80


def test_find_pareto_frontier_selection():
    # c1 dominates c2 because c1 has lower or equal error on all metrics
    c1 = {"id": "c1", "identity_distance": 0.1, "geometry_error": 0.1, "mark_displacement": 0.1}
    c2 = {"id": "c2", "identity_distance": 0.2, "geometry_error": 0.2, "mark_displacement": 0.2}
    c3 = {"id": "c3", "identity_distance": 0.05, "geometry_error": 0.3, "mark_displacement": 0.15}

    frontier = find_pareto_frontier([c1, c2, c3])
    frontier_ids = {c["id"] for c in frontier}
    assert "c1" in frontier_ids
    assert "c3" in frontier_ids
    assert "c2" not in frontier_ids


def test_identity_compiler_and_generator_adapters():
    capsule = fixture("base.json")
    contract = IdentityCompiler.compile_contract(
        capsule,
        scene_overrides={"environment": "Olympus Mons transit ruins", "pose": "kneeling combat stance"},
        timeline_state={"epoch": "2185"},
    )
    assert "contract_hash" in contract
    assert contract["tenant_id"] == "tenant:sample-a"
    assert contract["character_id"] == "character:sample-1"

    flux = FluxIdentityAdapter().compile(contract)
    assert "Olympus Mons" in flux.positive_prompt
    assert flux.control_signals["flux_lora_scale"] == 0.85
    assert flux.contract_hash == contract["contract_hash"]

    sdxl = SDXLIdentityAdapter().compile(contract)
    assert "photorealistic cinematic portrait" in sdxl.positive_prompt
    assert sdxl.control_signals["sdxl_ip_adapter_scale"] == 0.80

    veo = VeoIdentityAdapter().compile(contract)
    assert "temporal character action sequence" in veo.positive_prompt
    assert veo.control_signals["veo_temporal_consistency"] == 0.95
