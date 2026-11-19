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
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Provider brands forbidden in a generalized behaviour or target, matched whole-word.
# "cursor" is deliberately absent here and handled case-sensitively by _CURSOR_RE, so
# the common noun stays legal while the product name Cursor does not.
_BRAND_RE = re.compile(r"\b(?:claude|codex|gemini|openai|anthropic)\b", re.IGNORECASE)
_CURSOR_RE = re.compile(r"\bCursor\b")


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
    # Strongest -> weakest: runtime_reproduction > targeted_test > paper_body > static > abstract_only > model.
    # Default is the WEAKEST: an evidence row that doesn't say how it was obtained is an assertion.
    evidence_type: str = "model"
    provenance: Optional[str] = None


# Verifiability ceiling per evidence type. A candidate's verifiability can never exceed what
# its strongest evidence supports: a number read in an abstract is not a verified number.
EVIDENCE_CEILING: Dict[str, float] = {
    "runtime_reproduction": 1.0,  # we ran it and saw it
    "targeted_test": 0.9,         # a test we wrote exercises it
    "paper_body": 0.8,            # every key claim found in the paper's own text (nougen-radar morph_gate)
    "static": 0.6,                # code / docs read, not executed
    "abstract_only": 0.4,         # claims seen only in an abstract
    "model": 0.3,                 # asserted by a model or a person, unverified
}
NO_EVIDENCE_CEILING = 0.3


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

    def verifiability_ceiling(self) -> float:
        if not self.evidence:
            return NO_EVIDENCE_CEILING
        return max(EVIDENCE_CEILING.get(e.evidence_type, NO_EVIDENCE_CEILING) for e in self.evidence)

    def effective_score(self) -> float:
        """MorphScore with verifiability capped by the strongest evidence actually held."""
        v = min(self.verifiability, self.verifiability_ceiling())
        return self.usefulness * self.generalizability * v * self.compatibility * self.reversibility - self.integration_cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "donor_source": self.donor_source,
            "donor_behavior": self.donor_behavior,
            "generalized_behavior": self.generalized_behavior,
            "nougen_target": self.nougen_target,
            "score": round(self.morph_score(), 4),
            "effective_score": round(self.effective_score(), 4),
            "verifiability_ceiling": self.verifiability_ceiling(),
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
        # Hard Invariant: provider brand NAMES must not exist in generalized behavior
        # or target. Matched on word boundaries, not substrings: the old substring test
        # quarantined the ordinary word "cursor" (a pagination cursor) and anything
        # containing "codex"/"gemini" as a fragment. "cursor" is only a brand when it is
        # the capitalised proper noun Cursor; the rest are brands in any case.
        for text in (candidate.generalized_behavior, candidate.nougen_target):
            if _BRAND_RE.search(text) or _CURSOR_RE.search(text):
                candidate.state = AdoptionState.QUARANTINED
                self.candidates[candidate.name] = candidate
                return False, candidate.effective_score()

        score = candidate.effective_score()
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
