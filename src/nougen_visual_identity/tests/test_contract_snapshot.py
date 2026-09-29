"""Transaction guarantees, independent of any renderer or canonical character."""
from dataclasses import replace
import json
import pytest

from nougen_visual_identity.compiler import CharacterStateCompiler
from nougen_visual_identity.decomposable import IdentityRoot, IdentityVariant, MutationPolicy


def root():
    return IdentityRoot("subject", "Synthetic subject", tenant_id="tenant-a",
                        face_geometry={"jaw": {"ratio": 0.7}})


def test_nested_snapshot_is_detached_and_immutable():
    source = root()
    contract = CharacterStateCompiler().resolve(source)
    source.face_geometry["jaw"]["ratio"] = 0.1
    assert contract.resolved_phenotype["face_geometry"]["jaw"]["ratio"] == 0.7
    with pytest.raises(TypeError):
        contract.resolved_phenotype["face_geometry"]["jaw"]["ratio"] = 0.2
    exported = contract.to_dict()
    exported["resolved_phenotype"]["face_geometry"]["jaw"]["ratio"] = 0.3
    assert contract.contract_hash == contract.compute_hash()
    json.dumps(exported, allow_nan=False)


def test_resolution_does_not_mutate_amendments():
    amendments = [{"target": "phenotype", "delta": {"persistent_marks": []}}]
    variant = IdentityVariant("branch", "subject", mark_delta={"id": "synthetic"})
    CharacterStateCompiler().resolve(root(), variant, amendments)
    assert amendments[0]["delta"]["persistent_marks"] == []


def test_hash_is_reproducible_but_transaction_is_unique():
    compiler = CharacterStateCompiler()
    first, second = compiler.resolve(root()), compiler.resolve(root())
    assert first.transaction_id != second.transaction_id
    assert first.contract_hash == second.contract_hash == first.compute_hash()


def test_hash_includes_namespace_and_causal_state():
    compiler = CharacterStateCompiler()
    variant = IdentityVariant("branch", "subject", timeline_state="before")
    contracts = [compiler.resolve(root(), variant),
                 compiler.resolve(replace(root(), tenant_id="tenant-b"), variant),
                 compiler.resolve(root(), variant, project_id="other"),
                 compiler.resolve(root(), replace(variant, timeline_state="after")),
                 compiler.resolve(root(), replace(variant, route_state="other")),
                 compiler.resolve(root(), replace(variant, scene_state="other"))]
    assert len({c.contract_hash for c in contracts}) == len(contracts)


def test_wrong_parent_is_rejected():
    with pytest.raises(ValueError, match="parent"):
        CharacterStateCompiler().resolve(root(), IdentityVariant("branch", "someone-else"))


@pytest.mark.parametrize("budget", [-0.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_mutation_budget_is_rejected(budget):
    with pytest.raises(ValueError, match="budgets"):
        CharacterStateCompiler().resolve(replace(root(), mutation_policy=MutationPolicy(pose=budget)))


def test_missing_visual_evidence_does_not_claim_validated_fidelity():
    assert CharacterStateCompiler().resolve(root()).fidelity_level == 0


def test_nonfinite_state_is_rejected():
    with pytest.raises(ValueError):
        CharacterStateCompiler().resolve(root(), scene_overrides={"pose": float("nan")})
