"""
Mutation Operators for Creative Process Donors.
Provides 12 transformation operators that mutate structural techniques into native expressions.
Minimum recommended depth = 3 distinct operators.
"""

from typing import List, Tuple
from .models import MutationOperator, MutationTrace


class MutationEngine:
    """Executes semantic and structural mutations across technique atoms."""

    OPERATORS = {
        MutationOperator.INVERT: "Inverts polarity, advantage, or flow direction of the mechanism.",
        MutationOperator.TRANSPOSE: "Transposes the domain (e.g. from physical warfare to spiritual/informational resonance).",
        MutationOperator.TEMPORAL_SHIFT: "Shifts timing, sequence, or causality horizon.",
        MutationOperator.POV_SHIFT: "Re-anchors perspective from protagonist/ruler to margin, ghost, or target.",
        MutationOperator.CULTURAL_GROUNDING: "Infuses Haitian-Japanese ancestral memory, Kreyol ritual grammar, or Shinto-animist pacts.",
        MutationOperator.PHYSICS_REWRITE: "Translates into Veil impedance, shadow density, acoustic resonance, or light bleed.",
        MutationOperator.SYMBOLIC_SUBSTITUTION: "Substitutes donor motifs with native Veilverse symbols (marasa, veve, threshold, ink).",
        MutationOperator.SCALE_SHIFT: "Expands or collapses scale from cosmic/empire to cellular, intimate, or neighborhood.",
        MutationOperator.CONSEQUENCE_INVERSION: "Flips the cost: what was cheap becomes catastrophic, what was lethal becomes liberating.",
        MutationOperator.RITUALIZATION: "Encodes the mechanism into formal ceremonial protocol, debt obligation, or blood cadence.",
        MutationOperator.COMPRESSION: "Compresses expansive timelines or systems into immediate visceral gestures.",
        MutationOperator.FRAGMENTATION: "Breaks a centralized system into decentralized, asynchronous shards.",
    }

    @classmethod
    def apply_operator(cls, op: MutationOperator, text: str, context: str = "") -> MutationTrace:
        """Applies a single mutation operator to text and records provenance trace."""
        before = text
        op_name = op.value

        # Transformation templates applying deep domain mappings
        if op == MutationOperator.CULTURAL_GROUNDING:
            after = (
                f"{before} (Grounding: Rooted in Haitian-Japanese dual ancestral obligations, "
                f"where every pact requires blood-weight reciprocity and spiritual witness)"
            )
            rationale = "Grounds abstract mechanism in specific Haitian-Japanese lineage and spiritual debt."

        elif op == MutationOperator.PHYSICS_REWRITE:
            after = (
                f"{before} (Veil Physics: Mediated via shadow impedance, where the Veil acts as a high-viscosity "
                f"filter attenuating physical impact while amplifying acoustic resonance)"
            )
            rationale = "Replaces physical mechanics with native Veilverse field equations."

        elif op == MutationOperator.SYMBOLIC_SUBSTITUTION:
            after = (
                f"{before} (Symbolic: Replaced with Marasa duality, veve perimeter inscriptions, "
                f"and ink-threshold transitions)"
            )
            rationale = "Purges donor iconography and substitutes native Veilverse sacred geometry."

        elif op == MutationOperator.INVERT:
            after = f"Inverse mechanism: Instead of proactive assertion, operates via reactive vacuum: {before}"
            rationale = "Inverts functional direction to eliminate predictable donor trajectories."

        elif op == MutationOperator.TRANSPOSE:
            after = f"Transposed domain: Shifted from external material conflict to internal resonance lattice: {before}"
            rationale = "Transposes physical mechanism into perceptual and psychic substrate."

        elif op == MutationOperator.RITUALIZATION:
            after = f"Ritual cadence: Requires formal invocation, boundary tracing, and sacrificial payment: {before}"
            rationale = "Encodes utilitarian action into high-density cultural protocol."

        elif op == MutationOperator.FRAGMENTATION:
            after = f"Decentralized shards: Distributed across multiple non-local actors: {before}"
            rationale = "Breaks imperial/centralized donor structure into distributed Veil shards."

        elif op == MutationOperator.CONSEQUENCE_INVERSION:
            after = f"Inverted consequence: Immediate success exacts long-term perceptual blindness: {before}"
            rationale = "Subverts expected genre payoffs with native tragic debt."

        elif op == MutationOperator.POV_SHIFT:
            after = f"Shifted POV: Witnessed entirely through the sensory aperture of the collateral casualty: {before}"
            rationale = "Strips heroic epic framing down to intimate visceral reality."

        elif op == MutationOperator.SCALE_SHIFT:
            after = f"Scale shifted: Micro-scale physiological contagion acting as macro-political mirror: {before}"
            rationale = "Compresses planetary scale into intimate biological space."

        elif op == MutationOperator.TEMPORAL_SHIFT:
            after = f"Non-linear temporal causality: The consequence precedes the invocation: {before}"
            rationale = "Replaces chronological progression with Veil atemporal resonance."

        elif op == MutationOperator.COMPRESSION:
            after = f"Compressed gesture: Centuries of dynastic calculation collapsed into a single inhalation: {before}"
            rationale = "Eliminates leisurely exposition in favor of instantaneous pressure."

        else:
            after = f"Mutated ({op_name}): {before}"
            rationale = f"Applied {op_name} transformation."

        return MutationTrace(operator=op_name, before=before, after=after, rationale=rationale)

    @classmethod
    def apply_chain(cls, text: str, operators: List[MutationOperator], context: str = "") -> Tuple[str, List[MutationTrace]]:
        """Applies a chain of mutation operators sequentially."""
        traces = []
        current = text
        for op in operators:
            trace = cls.apply_operator(op, current, context=context)
            traces.append(trace)
            current = trace.after
        return current, traces