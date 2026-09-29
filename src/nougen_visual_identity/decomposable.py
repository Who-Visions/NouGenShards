"""
NouGen Multimodal Visual Identity Capsule Specification (v2.1)
Universal, multi-tenant, decomposable identity and inheritance models.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections.abc import Mapping
from types import MappingProxyType
from dataclasses import fields
import hashlib
import json


def freeze(value):
    """Detach and recursively freeze JSON-compatible contract data."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("Contract values must be JSON-compatible")


def thaw(value):
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value

@dataclass(frozen=True)
class MutationPolicy:
    """Explicit permission space for property changes. 0.0 = immutable, 1.0 = full freedom."""
    face_geometry: float = 0.00
    skin_identity: float = 0.00
    persistent_marks: float = 0.00
    body_proportions: float = 0.05
    hair_arrangement: float = 0.20
    expression: float = 0.40
    wardrobe: float = 0.70
    pose: float = 1.00
    environment: float = 1.00

@dataclass
class IdentityRoot:
    """The immutable root: 'Who is this entity?'"""
    character_id: str
    canonical_name: str
    tenant_id: str = "global"
    face_embedding: Optional[List[float]] = None
    face_geometry: Dict[str, Any] = field(default_factory=dict)
    persistent_marks: List[Dict[str, Any]] = field(default_factory=list)
    base_hair: Dict[str, Any] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)
    mutation_policy: MutationPolicy = field(default_factory=MutationPolicy)

@dataclass
class IdentityVariant:
    """Causal, temporal, or route branch inheriting from IdentityRoot."""
    variant_id: str
    parent_id: str
    timeline_state: Optional[str] = None  # e.g., "vol_1", "2155"
    route_state: Optional[str] = None     # e.g., "prime", "sdx", "x2"
    scene_state: Optional[str] = None     # e.g., "level_9_combat"
    age_delta: Dict[str, Any] = field(default_factory=dict)
    hair_delta: Dict[str, Any] = field(default_factory=dict)
    mark_delta: Dict[str, Any] = field(default_factory=dict)
    body_delta: Dict[str, Any] = field(default_factory=dict)
    wardrobe_delta: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class FrozenCharacterContract:
    """Immutable contract frozen for a single render transaction."""
    transaction_id: str
    character_id: str
    variant_id: str
    canon_revision: int
    contract_hash: str
    resolved_phenotype: Dict[str, Any]
    resolved_presentation: Dict[str, Any]
    mutation_policy: Dict[str, float]
    canonical_references: List[Dict[str, Any]]
    negative_constraints: List[str]
    fidelity_level: int = 0  # No verified visual assets or adapter evidence yet.
    tenant_id: str = "global"
    project_id: str = "default"
    causal_state: Dict[str, Any] = field(default_factory=dict)
    resolution_inputs: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "nougen.character_contract.v1"

    def __post_init__(self):
        for item in fields(self):
            object.__setattr__(self, item.name, freeze(getattr(self, item.name)))

    def to_dict(self) -> Dict[str, Any]:
        return {item.name: thaw(getattr(self, item.name)) for item in fields(self)}

    def compute_hash(self) -> str:
        payload = self.to_dict()
        payload.pop("transaction_id")
        payload.pop("contract_hash")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
