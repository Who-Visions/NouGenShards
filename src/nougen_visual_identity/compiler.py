"""
NouGen Character State Compiler (Compiler Engine)
Resolves canonical inheritance:
Root Identity -> Canon Amendments -> Temporal State -> Route/Branch State -> Scene Overrides -> Frozen Contract
"""
import uuid
from copy import deepcopy
from dataclasses import asdict, replace
import math
from typing import Dict, Any, List, Optional
from .decomposable import IdentityRoot, IdentityVariant, FrozenCharacterContract

class CharacterStateCompiler:
    """Compiles decomposable character identities into frozen, hash-addressed contracts."""

    def resolve(
        self,
        root: IdentityRoot,
        variant: Optional[IdentityVariant] = None,
        amendments: Optional[List[Dict[str, Any]]] = None,
        scene_overrides: Optional[Dict[str, Any]] = None,
        canon_revision: int = 1,
        project_id: str = "default"
    ) -> FrozenCharacterContract:
        """
        Deterministic precedence pipeline:
        SceneOverride > BranchState > TemporalState > CanonAmendment > RootIdentity
        """
        if variant is not None and variant.parent_id != root.character_id:
            raise ValueError("Variant parent does not match the root identity")
        if not root.tenant_id or not project_id or not root.character_id:
            raise ValueError("Tenant, project and character IDs are required")
        if type(canon_revision) is not int or canon_revision < 1:
            raise ValueError("Canon revision must be a positive integer")
        for budget in asdict(root.mutation_policy).values():
            if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or not 0 <= budget <= 1:
                raise ValueError("Mutation budgets must be finite values in [0, 1]")
        # Detach nested values before merging; resolution never changes its inputs.
        root = deepcopy(root)
        variant = deepcopy(variant)
        amendments = deepcopy(amendments)
        scene_overrides = deepcopy(scene_overrides)
        # 1. Base phenotype (immutable root)
        resolved_phenotype = {
            "face_embedding": list(root.face_embedding) if root.face_embedding else [],
            "face_geometry": dict(root.face_geometry),
            "persistent_marks": list(root.persistent_marks),
            "body": dict(root.body),
        }

        # 2. Base presentation (mutable root)
        resolved_presentation = {
            "hair": dict(root.base_hair),
            "wardrobe": {},
            "expression": "neutral",
            "pose": "neutral_standing",
            "environment": "studio_neutral"
        }

        # 3. Apply valid amendments (if any)
        if amendments:
            for am in amendments:
                if am.get("target") == "phenotype":
                    resolved_phenotype.update(am.get("delta", {}))
                elif am.get("target") == "presentation":
                    resolved_presentation.update(am.get("delta", {}))

        # 4. Apply variant deltas (temporal, route, causal branch)
        variant_id = "prime"
        if variant:
            variant_id = variant.variant_id
            if variant.age_delta:
                resolved_phenotype["age_modifiers"] = variant.age_delta
            if variant.mark_delta:
                # E.g., adding or updating a route-specific scar
                resolved_phenotype["persistent_marks"].append(variant.mark_delta)
            if variant.hair_delta:
                resolved_presentation["hair"].update(variant.hair_delta)
            if variant.body_delta:
                resolved_phenotype["body"].update(variant.body_delta)
            if variant.wardrobe_delta:
                resolved_presentation["wardrobe"].update(variant.wardrobe_delta)

        # 5. Apply scene overrides (within permitted mutation boundaries)
        if scene_overrides:
            for key, val in scene_overrides.items():
                if key in ["expression", "pose", "environment", "lighting", "camera"]:
                    resolved_presentation[key] = val
                elif key in ["hair_arrangement", "wardrobe"]:
                    resolved_presentation[key] = val
                elif key in ["face_geometry", "skin_identity"]:
                    # Scene input cannot authorize a canonical phenotype mutation.
                    continue

        # 6. Freeze Contract
        policy_dict = {
            "face_geometry": root.mutation_policy.face_geometry,
            "skin_identity": root.mutation_policy.skin_identity,
            "persistent_marks": root.mutation_policy.persistent_marks,
            "body_proportions": root.mutation_policy.body_proportions,
            "hair_arrangement": root.mutation_policy.hair_arrangement,
            "expression": root.mutation_policy.expression,
            "wardrobe": root.mutation_policy.wardrobe,
            "pose": root.mutation_policy.pose,
            "environment": root.mutation_policy.environment,
        }

        payload = {
            "schema": "nougen.character_contract.v1",
            "tenant_id": root.tenant_id,
            "project_id": project_id,
            "character_id": root.character_id,
            "variant_id": variant_id,
            "canon_revision": canon_revision,
            "phenotype": resolved_phenotype,
            "presentation": resolved_presentation,
            "policy": policy_dict,
            "causal_state": {
                "timeline": variant.timeline_state if variant else None,
                "route": variant.route_state if variant else None,
                "scene": variant.scene_state if variant else None,
            },
            "amendments": amendments or [],
            "scene_overrides": scene_overrides or {},
        }
        contract = FrozenCharacterContract(
            transaction_id=str(uuid.uuid4()),
            character_id=root.character_id,
            variant_id=variant_id,
            canon_revision=canon_revision,
            contract_hash="",
            resolved_phenotype=resolved_phenotype,
            resolved_presentation=resolved_presentation,
            mutation_policy=policy_dict,
            canonical_references=[],
            negative_constraints=["genetic_drift", "facial_proportions_mutation"],
            fidelity_level=0,
            tenant_id=root.tenant_id,
            project_id=project_id,
            causal_state=payload["causal_state"],
            resolution_inputs={"amendments": payload["amendments"], "scene_overrides": payload["scene_overrides"]},
        )
        return replace(contract, contract_hash=contract.compute_hash())
