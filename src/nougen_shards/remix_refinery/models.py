"""
Core Data Models for Shadow Dweller Remix Refinery.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
import datetime
import uuid


class ProcessDonorType(str, Enum):
    PROCESS_ONLY = "PROCESS_ONLY"


class MechanismStatus(str, Enum):
    EXPERIMENTAL = "experimental"
    QUARANTINED = "quarantined"
    REVIEW = "review"
    CANON_CANDIDATE = "canon_candidate"
    REJECTED = "rejected"


class TechniqueAtom(BaseModel):
    """An abstracted technique extracted from a donor creative problem."""
    atom_id: str = Field(default_factory=lambda: f"atom_{uuid.uuid4().hex[:8]}")
    function: str
    preconditions: List[str] = Field(default_factory=list)
    mechanism: str
    intended_effect: str
    narrative_cost: str
    abstraction_level: str = "structural"  # structural, operational, perceptual


class ProcessDonorCard(BaseModel):
    """
    A process donor card admitting external mechanism while strictly forbidding
    surface identity or copyrighted expressions.
    """
    donor_id: str
    source_title: str
    donor_type: ProcessDonorType = ProcessDonorType.PROCESS_ONLY
    creative_problem: str
    extracted_techniques: List[TechniqueAtom] = Field(default_factory=list)
    forbidden_surface_elements: List[str] = Field(default_factory=list)
    abstraction_notes: str = ""
    process_reference: str = ""


class CanonAnchor(BaseModel):
    """Binds abstracted atoms to native Shadow Dweller canon, lore, physics, and wounds."""
    anchor_id: str = Field(default_factory=lambda: f"anchor_{uuid.uuid4().hex[:8]}")
    lineage: str  # e.g., 'Haitian-Japanese', 'Veil physics', 'character wound', 'faction', 'ritual'
    shard_ref: Optional[int] = None
    concept: str
    constraints: List[str] = Field(default_factory=list)


class MutationOperator(str, Enum):
    INVERT = "invert"
    TRANSPOSE = "transpose"
    TEMPORAL_SHIFT = "temporal_shift"
    POV_SHIFT = "pov_shift"
    CULTURAL_GROUNDING = "cultural_grounding"
    PHYSICS_REWRITE = "physics_rewrite"
    SYMBOLIC_SUBSTITUTION = "symbolic_substitution"
    SCALE_SHIFT = "scale_shift"
    CONSEQUENCE_INVERSION = "consequence_inversion"
    RITUALIZATION = "ritualization"
    COMPRESSION = "compression"
    FRAGMENTATION = "fragmentation"


class MutationTrace(BaseModel):
    """Record of an applied mutation operation."""
    operator: str
    before: str
    after: str
    rationale: str


class CollisionReport(BaseModel):
    """Canon collision detection outcome."""
    has_collision: bool = False
    contradictions: List[str] = Field(default_factory=list)
    action: str = "pass"  # pass, quarantine, reject
    notes: str = ""


class TransformationScore(BaseModel):
    """
    Governance heuristics and review triggers measuring transformation depth,
    donor leakage, and native veil integration.
    """
    surface_similarity: float = 0.0
    plot_similarity: float = 0.0
    terminology_similarity: float = 0.0
    staging_similarity: float = 0.0
    iconography_similarity: float = 0.0
    donor_leakage: float = 0.0

    canon_fit: float = 1.0
    cultural_grounding: float = 1.0
    veil_physics_rewrite: float = 1.0
    symbolic_transformation: float = 1.0
    source_diversity: float = 1.0
    veil_distance: float = 1.0

    gate_verdict: str = "CANON_CANDIDATE"
    gate_reasons: List[str] = Field(default_factory=list)


class CandidateMechanism(BaseModel):
    """The mutated, braided native mechanism candidate."""
    candidate_id: str = Field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:8]}")
    atoms: List[TechniqueAtom] = Field(default_factory=list)
    canon_anchors: List[CanonAnchor] = Field(default_factory=list)
    mutations: List[MutationTrace] = Field(default_factory=list)
    independent_donors: List[str] = Field(default_factory=list)
    native_expression: str
    scene_applications: List[str] = Field(default_factory=list)
    status: MechanismStatus = MechanismStatus.EXPERIMENTAL
    collision_report: Optional[CollisionReport] = None
    scores: Optional[TransformationScore] = None


class ProvenanceLedger(BaseModel):
    """Immutable audit trail demonstrating abstraction, transformation, and leakage proof."""
    ledger_id: str = Field(default_factory=lambda: f"ledg_{uuid.uuid4().hex[:8]}")
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    donor_id: str
    candidate_id: str
    creative_problem: str
    abstracted_elements: List[str] = Field(default_factory=list)
    stripped_forbidden_matches: List[str] = Field(default_factory=list)
    mutations_applied: List[str] = Field(default_factory=list)
    braided_sources: List[str] = Field(default_factory=list)
    scores: TransformationScore
    status: MechanismStatus
    shard_id: Optional[int] = None