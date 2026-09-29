"""Generator adapter contracts and character state compilation for Visual Identity Capsules.

Preserves the Fleet Rule: "Memory survives model replacement".
These adapters compile canonical character contracts into generator-specific
prompts, conditioning embeddings, and control signals without altering canon.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GeneratorConditioning:
    positive_prompt: str
    negative_prompt: str
    reference_assets: tuple[Mapping[str, Any], ...]
    control_signals: Mapping[str, Any]
    contract_hash: str


class IdentityCompiler:
    """Compiles resolved Character State and Causal State into an immutable execution contract."""

    @staticmethod
    def compute_contract_hash(contract: Mapping[str, Any]) -> str:
        serialized = json.dumps(contract, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def compile_contract(
        cls,
        capsule: Mapping[str, Any],
        *,
        scene_overrides: Mapping[str, Any] | None = None,
        timeline_state: Mapping[str, Any] | None = None,
        route_state: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        contract = {
            "tenant_id": capsule.get("tenant_id"),
            "character_id": capsule.get("character_id"),
            "capsule_id": capsule.get("capsule_id"),
            "revision": capsule.get("revision"),
            "immutable": capsule.get("identity", {}),
            "references": capsule.get("references", []),
            "timeline_state": dict(timeline_state or {}),
            "route_state": dict(route_state or {}),
            "scene_overrides": dict(scene_overrides or {}),
            "mutation_budget": dict(capsule.get("mutation_budget") or {}),
            "negative_constraints": list(capsule.get("negative_constraints") or []),
        }
        contract["contract_hash"] = cls.compute_contract_hash(contract)
        return contract


class BaseGeneratorAdapter(ABC):
    """Abstract interface for generator-specific compilers."""

    @abstractmethod
    def compile(self, contract: Mapping[str, Any]) -> GeneratorConditioning:
        """Transform resolved contract into provider-specific conditioning signals."""
        pass


class FluxIdentityAdapter(BaseGeneratorAdapter):
    """Adapter for FLUX.1 / IP-Adapter / ControlNet conditioning."""

    def compile(self, contract: Mapping[str, Any]) -> GeneratorConditioning:
        immutable = contract.get("immutable", {})
        claims = {c.get("key"): c.get("value") for c in immutable.get("claims", []) if isinstance(c, Mapping)}
        scene = contract.get("scene_overrides", {})
        
        prompt_parts = []
        if "role" in claims:
            prompt_parts.append(str(claims["role"]))
        if "hair_color" in claims:
            prompt_parts.append(f"{claims['hair_color']} hair")
        if "environment" in scene:
            prompt_parts.append(f"in {scene['environment']}")
        if "pose" in scene:
            prompt_parts.append(str(scene["pose"]))

        positive = ", ".join(prompt_parts) if prompt_parts else "canonical character portrait"
        negative = ", ".join(contract.get("negative_constraints", []))

        refs = tuple(contract.get("references", []))
        controls = {
            "flux_lora_scale": 0.85,
            "controlnet_ip_adapter": True,
            "mutation_budget": contract.get("mutation_budget", {}),
        }
        return GeneratorConditioning(
            positive_prompt=positive,
            negative_prompt=negative,
            reference_assets=refs,
            control_signals=controls,
            contract_hash=contract.get("contract_hash", ""),
        )


class SDXLIdentityAdapter(BaseGeneratorAdapter):
    """Adapter for Stable Diffusion XL / ConsistentID conditioning."""

    def compile(self, contract: Mapping[str, Any]) -> GeneratorConditioning:
        immutable = contract.get("immutable", {})
        claims = {c.get("key"): c.get("value") for c in immutable.get("claims", []) if isinstance(c, Mapping)}
        scene = contract.get("scene_overrides", {})

        prompt_parts = []
        if "role" in claims:
            prompt_parts.append(str(claims["role"]))
        if "hair_color" in claims:
            prompt_parts.append(f"{claims['hair_color']} hair")
        if "lighting" in scene:
            prompt_parts.append(f"{scene['lighting']}")

        positive = f"photorealistic cinematic portrait, {', '.join(prompt_parts)}"
        negative = ", ".join(list(contract.get("negative_constraints", [])) + ["distorted geometry", "extra limbs"])

        refs = tuple(contract.get("references", []))
        controls = {
            "sdxl_ip_adapter_scale": 0.80,
            "controlnet_openpose": bool(scene.get("pose")),
        }
        return GeneratorConditioning(
            positive_prompt=positive,
            negative_prompt=negative,
            reference_assets=refs,
            control_signals=controls,
            contract_hash=contract.get("contract_hash", ""),
        )


class VeoIdentityAdapter(BaseGeneratorAdapter):
    """Adapter for Veo video / sequential keyframe conditioning."""

    def compile(self, contract: Mapping[str, Any]) -> GeneratorConditioning:
        scene = contract.get("scene_overrides", {})
        timeline = contract.get("timeline_state", {})
        
        positive = f"temporal character action sequence, timeline {timeline.get('epoch', 'prime')}, scene {scene.get('action', 'neutral')}"
        negative = ", ".join(contract.get("negative_constraints", []))
        refs = tuple(contract.get("references", []))
        controls = {
            "veo_temporal_consistency": 0.95,
            "fps": 24,
        }
        return GeneratorConditioning(
            positive_prompt=positive,
            negative_prompt=negative,
            reference_assets=refs,
            control_signals=controls,
            contract_hash=contract.get("contract_hash", ""),
        )
