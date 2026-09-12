"""
Canon Collision Gate & Governance for Remix Refinery.
Enforces non-negotiable invariant:
'The donor must become unrecognizable before canon can recognize it.'
"""

from typing import List
from .models import CollisionReport, MechanismStatus, TransformationScore


class CanonGate:
    """Validates mechanisms against existing domain canon and invariants."""

    CANON_INVARIANTS = [
        "The Veil cannot be bypassed without energetic or physical reciprocity.",
        "Marasa lineage binds Haitian and Japanese ancestral spiritual obligations.",
        "No single character possesses omniscient or unearned prophetic clarity.",
        "Technology in the Veilverse functions through resonance and acoustic impedance, not clean magic.",
    ]

    @classmethod
    def evaluate_collision(cls, expression: str, anchors: List[str]) -> CollisionReport:
        """Checks expression against canon invariants and collision thresholds."""
        contradictions = []
        text_lower = expression.lower()

        # Check for unearned omniscience / prophecy (violates Veilverse human vulnerability)
        if "omniscient" in text_lower or "sees all futures" in text_lower:
            contradictions.append("Violates human vulnerability invariant: unearned prescience detected.")

        # Check for zero-cost Veil traversal
        if "free traversal" in text_lower or "without cost" in text_lower:
            contradictions.append("Violates energetic reciprocity: Veil transit must incur cost or resonance toll.")

        has_collision = len(contradictions) > 0
        action = "quarantine" if has_collision else "pass"
        notes = "; ".join(contradictions) if contradictions else "Clean alignment with Veilverse invariants."

        return CollisionReport(
            has_collision=has_collision,
            contradictions=contradictions,
            action=action,
            notes=notes,
        )

    @classmethod
    def determine_status(cls, collision: CollisionReport, scores: TransformationScore) -> MechanismStatus:
        """Assigns candidate status based on collision report and governance scores."""
        if collision.has_collision or scores.gate_verdict == "REJECTED":
            return MechanismStatus.REJECTED
        if scores.gate_verdict == "QUARANTINED":
            return MechanismStatus.QUARANTINED
        if scores.gate_verdict == "EXPERIMENTAL":
            return MechanismStatus.EXPERIMENTAL
        if scores.gate_verdict == "REVIEW":
            return MechanismStatus.REVIEW
        return MechanismStatus.CANON_CANDIDATE