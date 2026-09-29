"""
Integration & Regression Tests for Decomposable Identity, Manifold Math, and Compilers
"""
from nougen_visual_identity.decomposable import IdentityRoot, IdentityVariant, MutationPolicy
from nougen_visual_identity.compiler import CharacterStateCompiler
from nougen_visual_identity.manifold import (
    compute_empirical_covariance,
    apply_shrinkage,
    invert_diagonal_approximation,
    mahalanobis_distance_diagonal,
    scene_aware_reference_selection
)

def test_decomposable_identity_inheritance():
    root = IdentityRoot(
        character_id="xoah_oda",
        canonical_name="Xoah Oda",
        tenant_id="veilverse",
        face_embedding=[0.1, 0.2, 0.3],
        face_geometry={"jaw_ratio": 0.72},
        persistent_marks=[{"mark_id": "left_eye_scar"}],
        base_hair={"type": "dense_locs", "color": "black"},
        body={"build": "athletic"}
    )

    sdx_variant = IdentityVariant(
        variant_id="xoah_sdx",
        parent_id="xoah_oda",
        timeline_state="2185",
        route_state="route_2",
        mark_delta={"mark_id": "caldera_burn_mark"},
        hair_delta={"accent": "violet_cyan_sheen"}
    )

    compiler = CharacterStateCompiler()
    contract = compiler.resolve(root=root, variant=sdx_variant)

    assert contract.character_id == "xoah_oda"
    assert contract.variant_id == "xoah_sdx"
    # Root marks preserved + delta added
    marks = [m["mark_id"] for m in contract.resolved_phenotype["persistent_marks"]]
    assert "left_eye_scar" in marks
    assert "caldera_burn_mark" in marks
    # Hair delta applied
    assert contract.resolved_presentation["hair"]["accent"] == "violet_cyan_sheen"
    # Immutable face geometry untouched
    assert contract.resolved_phenotype["face_geometry"]["jaw_ratio"] == 0.72
    assert len(contract.contract_hash) == 64

def test_scene_override_mutation_budget_enforcement():
    root = IdentityRoot(
        character_id="xoah_oda",
        canonical_name="Xoah Oda",
        face_geometry={"interocular_ratio": 0.44},
        mutation_policy=MutationPolicy(face_geometry=0.0, pose=1.0)
    )

    compiler = CharacterStateCompiler()
    # Attempt illegal drift (altering face_geometry without explicit authorization)
    illegal_scene = {
        "pose": "kneeling_combat",
        "face_geometry": {"interocular_ratio": 0.85}  # Illegal drift
    }
    contract = compiler.resolve(root=root, scene_overrides=illegal_scene)

    assert contract.resolved_presentation["pose"] == "kneeling_combat"
    # Illegal geometry change was rejected by compiler
    assert contract.resolved_phenotype["face_geometry"]["interocular_ratio"] == 0.44

def test_mahalanobis_covariance_and_shrinkage():
    vectors = [
        [1.0, 0.1],
        [1.1, 0.2],
        [0.9, 0.05]
    ]
    centroid = [1.0, 0.1167]
    cov = compute_empirical_covariance(vectors, centroid)
    assert len(cov) == 2
    assert cov[0][0] > 0.0

    shrunk = apply_shrinkage(cov, shrinkage_lambda=0.2)
    assert shrunk[0][0] > 0.0

    inv_diag = invert_diagonal_approximation(shrunk)
    dist = mahalanobis_distance_diagonal([1.0, 0.1167], centroid, inv_diag)
    assert dist < 0.001  # Centroid has zero distance

def test_scene_aware_reference_selection():
    refs = [
        {"asset_id": "ref_front", "role": "identity_anchor", "view": {"yaw": 0.0, "pitch": 0.0}, "quality": 0.99},
        {"asset_id": "ref_profile", "role": "pose_variant", "view": {"yaw": 88.0, "pitch": 0.0}, "quality": 0.90},
        {"asset_id": "ref_3quarter", "role": "pose_variant", "view": {"yaw": 32.0, "pitch": -5.0}, "quality": 0.95},
        {"asset_id": "ref_downward", "role": "pose_variant", "view": {"yaw": 5.0, "pitch": -35.0}, "quality": 0.92},
    ]

    # Target: 3/4 right view (yaw=30, pitch=0)
    selected = scene_aware_reference_selection(refs, target_yaw=30.0, target_pitch=0.0, max_refs=2)
    ids = [r["asset_id"] for r in selected]
    # Must contain anchor + nearest geometric view
    assert "ref_front" in ids
    assert "ref_3quarter" in ids
    assert "ref_profile" not in ids
