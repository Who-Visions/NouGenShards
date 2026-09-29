"""
NouGenMorph: Evolutionary Cognitive Ingestion & Behavior De-Branding Engine.

Formalizes the transformation:
    M(S) = P o D o E o N o V

Where:
    S = external source observation
    E = extract observable behaviors
    D = decompose behavior from implementation
    N = normalize into provider-independent primitives
    V = validate against NouGen's existing architecture
    P = persist validated discoveries into fleet Shards

And evaluates candidates via MorphScore:
    MorphScore = (U * G * V * C * R) - I
Where:
    U = Usefulness (0.0 - 1.0)
    G = Generalizability (0.0 - 1.0)
    V = Verifiability (0.0 - 1.0)
    C = Architectural Compatibility (0.0 - 1.0)
    R = Reversibility (0.0 - 1.0)
    I = Integration Cost (0.0 - 1.0)

Enforces:
    Role != Provider
    Hardcoding = Architecture Debt
    Disagreement Must Survive Synthesis (Evidence-Weighted Non-Democratic Arbitration)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


class MorphKind(str, Enum):
    FACT = "fact"
    PATTERN = "pattern"
    BEHAVIOR = "behavior"
    MECHANISM = "mechanism"
    ALGORITHM = "algorithm"
    ANTI_PATTERN = "anti_pattern"
    EXPERIMENT = "experiment"
    NOUGEN_CANDIDATE = "nougen_candidate"
    NOUGEN_PRIMITIVE = "nougen_primitive"


class AdoptionState(str, Enum):
    DISCOVERED = "discovered"
    EXTRACTED = "extracted"
    GENERALIZED = "generalized"
    CANDIDATE = "candidate"
    SIMULATED = "simulated"
    TESTED = "tested"
    VERIFIED = "verified"
    ADOPTED = "adopted"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class MorphEvidence:
    source: str
    claim: str
    confidence: float
    evidence_type: str = "runtime_reproduction"  # runtime_reproduction > targeted_test > static > model
    provenance: Optional[str] = None


@dataclass
class MorphCandidate:
    name: str
    kind: MorphKind
    donor_source: str
    donor_behavior: str
    generalized_behavior: str
    nougen_target: str
    evidence: List[MorphEvidence] = field(default_factory=list)
    usefulness: float = 0.0
    generalizability: float = 0.0
    verifiability: float = 0.0
    compatibility: float = 0.0
    reversibility: float = 1.0
    integration_cost: float = 0.0
    state: AdoptionState = AdoptionState.DISCOVERED
    created_at: float = field(default_factory=time.time)

    def morph_score(self) -> float:
        """Computes objective MorphScore."""
        positive = (
            self.usefulness
            * self.generalizability
            * self.verifiability
            * self.compatibility
            * self.reversibility
        )
        return positive - self.integration_cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "donor_source": self.donor_source,
            "donor_behavior": self.donor_behavior,
            "generalized_behavior": self.generalized_behavior,
            "nougen_target": self.nougen_target,
            "score": round(self.morph_score(), 4),
            "state": self.state.value,
            "metrics": {
                "usefulness": self.usefulness,
                "generalizability": self.generalizability,
                "verifiability": self.verifiability,
                "compatibility": self.compatibility,
                "reversibility": self.reversibility,
                "integration_cost": self.integration_cost,
            },
            "evidence": [
                {"source": e.source, "claim": e.claim, "confidence": e.confidence, "type": e.evidence_type}
                for e in self.evidence
            ],
        }


@dataclass
class MorphFinding:
    claim_id: str
    statement: str
    severity: float  # 0.0 - 1.0
    evidence_weight: float  # 0.0 - 1.0
    confidence: float  # 0.0 - 1.0
    blast_radius: float  # 0.0 - 1.0
    resolved: bool = False

    def blocking_risk(self) -> float:
        """Senior engineering law: blocking risk = severity * evidence * confidence * blast_radius."""
        if self.resolved:
            return 0.0
        return self.severity * self.evidence_weight * self.confidence * self.blast_radius


class NouGenMorphEngine:
    """The cognitive compiler transforming external intelligence into fleet invariants."""

    def __init__(self, acceptance_threshold: float = 0.50) -> None:
        self.acceptance_threshold = acceptance_threshold
        self.candidates: Dict[str, MorphCandidate] = {}

    def ingest_candidate(self, candidate: MorphCandidate) -> Tuple[bool, float]:
        """Ingests and scores a candidate against architecture invariants."""
        # Hard Invariant: Provider brand names must NOT exist in generalized behavior or target
        forbidden_brands = ["claude", "codex", "cursor", "gemini", "openai", "anthropic"]
        gen_lower = candidate.generalized_behavior.lower()
        target_lower = candidate.nougen_target.lower()

        for brand in forbidden_brands:
            if brand in gen_lower or brand in target_lower:
                candidate.state = AdoptionState.QUARANTINED
                self.candidates[candidate.name] = candidate
                return False, candidate.morph_score()

        score = candidate.morph_score()
        if score >= self.acceptance_threshold:
            candidate.state = AdoptionState.CANDIDATE
            self.candidates[candidate.name] = candidate
            return True, score
        else:
            candidate.state = AdoptionState.QUARANTINED
            self.candidates[candidate.name] = candidate
            return False, score

    @staticmethod
    def calculate_latent_spec_completion(
        explicit_reqs: int,
        valid_inferred_reqs: int,
        hallucinated_reqs: int,
        lambda_penalty: float = 2.0,
    ) -> float:
        """
        Computes Latent Specification Completion (LSC):
            LSC = |R_i| / (|R_i| + lambda * |R_h|)
        where lambda > 1 heavily penalizes ungrounded hallucinations.
        """
        if valid_inferred_reqs == 0 and hallucinated_reqs == 0:
            return 1.0 if explicit_reqs > 0 else 0.0
        denominator = valid_inferred_reqs + (lambda_penalty * hallucinated_reqs)
        if denominator == 0:
            return 0.0
        return valid_inferred_reqs / denominator

    @staticmethod
    def evaluate_arbitration(findings: Sequence[MorphFinding], critical_threshold: float = 0.60) -> Tuple[bool, float]:
        """
        Evidence-Weighted Non-Democratic Arbitration:
        A critical unresolved finding supported by strong evidence dominates cosmetic approvals.
        Returns: (can_ship, max_blocking_risk)
        """
        if not findings:
            return True, 0.0

        max_risk = max((f.blocking_risk() for f in findings), default=0.0)
        can_ship = max_risk < critical_threshold
        return can_ship, max_risk
