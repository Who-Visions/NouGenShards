"""
NouGen Multimodal Visual Identity Capsule Specification (v2)
Universal, multi-tenant schema definitions.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import hashlib
import json

@dataclass
class IdentityHeader:
    character_id: str
    canonical_name: str
    status: str = "canon"
    tenant_id: str = "global"

@dataclass
class CanonicalReference:
    asset_id: str
    sha256: str
    role: str  # "identity_anchor", "pose_variant", "detail_crop"
    view: Dict[str, float]  # yaw, pitch, roll
    quality: float  # 0.0 to 1.0
    redundancy: float = 0.0  # calculated dynamically
    uri: Optional[str] = None

@dataclass
class IdentityEmbedding:
    model: str
    dimension: int
    centroid: List[float]
    reference_vectors: List[List[float]] = field(default_factory=list)
    normalization: str = "l2"

@dataclass
class FaceGeometry:
    coordinate_system: str = "interocular_normalized"
    landmarks: Dict[str, List[float]] = field(default_factory=dict)
    ratios: Dict[str, float] = field(default_factory=dict)
    angles: Dict[str, float] = field(default_factory=dict)

@dataclass
class PersistentMark:
    mark_id: str
    mark_type: str  # "scar", "tattoo", "mole", "piercing"
    anchors: Dict[str, str]  # e.g., {"origin": "left_brow_outer", "termination": "left_upper_cheek"}
    polyline_normalized: List[List[float]] = field(default_factory=list)
    width_profile: List[float] = field(default_factory=list)

@dataclass
class HairTopology:
    base: str
    type: str
    length_ratio: float
    volume_ratio: float
    accent_distribution: Dict[str, float] = field(default_factory=dict)
    hardware: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BodyProportions:
    proportions: Dict[str, float] = field(default_factory=dict)
    silhouette_embedding: Optional[List[float]] = None

@dataclass
class WardrobeInvariants:
    hard_invariants: List[str] = field(default_factory=list)
    soft_invariants: List[str] = field(default_factory=list)

@dataclass
class NegativeIdentity:
    forbidden_features: List[str] = field(default_factory=list)
    known_failure_modes: List[str] = field(default_factory=list)

@dataclass
class IdentityThresholds:
    identity_similarity_min: float = 0.85
    geometry_error_max: float = 0.12
    mark_error_max: float = 0.10
    hair_error_max: float = 0.15

@dataclass
class ProvenanceManifest:
    created_utc: str
    source_shards: List[str] = field(default_factory=list)
    approved_assets: List[str] = field(default_factory=list)
    generator_independent: bool = True
    author: str = "fleet"

@dataclass
class VisualIdentityCapsule:
    schema: str = "nougen.visual_identity.v2"
    schema_version: int = 2
    identity: Optional[IdentityHeader] = None
    references: List[CanonicalReference] = field(default_factory=list)
    embedding: Optional[IdentityEmbedding] = None
    face_geometry: Optional[FaceGeometry] = None
    persistent_marks: List[PersistentMark] = field(default_factory=list)
    hair: Optional[HairTopology] = None
    body: Optional[BodyProportions] = None
    wardrobe: Optional[WardrobeInvariants] = None
    negative_identity: Optional[NegativeIdentity] = None
    thresholds: Optional[IdentityThresholds] = None
    provenance: Optional[ProvenanceManifest] = None

    def to_dict(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self, default=lambda o: o.__dict__))

    def content_hash(self) -> str:
        serialized = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
