"""
Heuristic Scoring & Governance Gates for Remix Refinery.
Calculates donor_leakage and veil_distance heuristics according to canonical formula:
donor_leakage = .30*surface + .25*plot + .20*terminology + .15*staging + .10*iconography
veil_distance = .25*(1-leakage) + .20*canon_fit + .15*cultural + .15*physics + .10*symbolic + .15*diversity
"""

import re
from typing import List
from .models import TransformationScore


class ScoringEngine:
    """Calculates leakage and veil integration scores."""

    @classmethod
    def calculate(
        cls,
        expression_text: str,
        forbidden_elements: List[str],
        canon_anchors: List[str],
        independent_sources: List[str],
        mutations_count: int,
    ) -> TransformationScore:
        text_lower = expression_text.lower()

        # 1. Check surface leakage (exact or fuzzy matches of forbidden words)
        forbidden_hits = []
        for element in forbidden_elements:
            el_clean = element.strip().lower()
            if el_clean and re.search(r'\b' + re.escape(el_clean) + r'\b', text_lower):
                forbidden_hits.append(element)

        leakage_ratio = len(forbidden_hits) / max(len(forbidden_elements), 1) if forbidden_elements else 0.0

        surface_similarity = min(1.0, leakage_ratio * 1.5)
        plot_similarity = 0.0
        terminology_similarity = min(1.0, leakage_ratio * 1.2)
        staging_similarity = 0.05 if leakage_ratio > 0 else 0.0
        iconography_similarity = min(1.0, leakage_ratio * 1.0)

        donor_leakage = (
            0.30 * surface_similarity
            + 0.25 * plot_similarity
            + 0.20 * terminology_similarity
            + 0.15 * staging_similarity
            + 0.10 * iconography_similarity
        )

        # 2. Check native Veil integration
        cultural_keywords = ["haitian", "japanese", "ancestral", "pact", "kreyol", "marasa", "blood", "debt"]
        physics_keywords = ["veil", "shadow", "impedance", "resonance", "frequency", "bleed", "density", "threshold"]
        symbolic_keywords = ["veve", "ink", "mirror", "crossroad", "carrefour", "perimeter", "sacred"]

        cultural_hits = sum(1 for kw in cultural_keywords if kw in text_lower)
        physics_hits = sum(1 for kw in physics_keywords if kw in text_lower)
        symbolic_hits = sum(1 for kw in symbolic_keywords if kw in text_lower)

        cultural_grounding = min(1.0, 0.4 + (cultural_hits * 0.15))
        veil_physics_rewrite = min(1.0, 0.4 + (physics_hits * 0.15))
        symbolic_transformation = min(1.0, 0.4 + (symbolic_hits * 0.15))

        # Diversity: at least 2 independent sources gives 1.0, 1 gives 0.6, 0 gives 0.2
        num_sources = len(independent_sources)
        if num_sources >= 2:
            source_diversity = 1.0
        elif num_sources == 1:
            source_diversity = 0.65
        else:
            source_diversity = 0.20

        # Canon fit scales with depth of mutations and presence of canon anchors
        canon_fit = min(1.0, 0.5 + (len(canon_anchors) * 0.15) + (min(mutations_count, 4) * 0.1))

        # Canonical formula
        veil_distance = (
            0.25 * (1.0 - donor_leakage)
            + 0.20 * canon_fit
            + 0.15 * cultural_grounding
            + 0.15 * veil_physics_rewrite
            + 0.10 * symbolic_transformation
            + 0.15 * source_diversity
        )

        # Gate verdicts
        gate_reasons = []
        if donor_leakage > 0.30:
            verdict = "REJECTED"
            gate_reasons.append(f"CRITICAL LEAKAGE ({donor_leakage:.2f} > 0.30): Forbidden surface elements detected: {forbidden_hits}")
        elif donor_leakage >= 0.15:
            verdict = "QUARANTINED"
            gate_reasons.append(f"LEAKAGE WARNING ({donor_leakage:.2f} in 0.15..0.30): Must mutate again before canon admission.")
        elif veil_distance < 0.70:
            verdict = "EXPERIMENTAL"
            gate_reasons.append(f"LOW VEIL DISTANCE ({veil_distance:.2f} < 0.70): Insufficiently native to Veilverse.")
        elif canon_fit < 0.85:
            verdict = "REVIEW"
            gate_reasons.append(f"CANON FIT GAP ({canon_fit:.2f} < 0.85): Needs narrative alignment review.")
        elif num_sources < 2:
            verdict = "REVIEW"
            gate_reasons.append(f"INSUFFICIENT SOURCES ({num_sources} < 2): Minimum 2 independent donor sources required for automatic canon graduation.")
        else:
            verdict = "CANON_CANDIDATE"
            gate_reasons.append("All gates passed cleanly: zero donor leakage, deep veil distance, multi-source braided.")

        return TransformationScore(
            surface_similarity=round(surface_similarity, 3),
            plot_similarity=round(plot_similarity, 3),
            terminology_similarity=round(terminology_similarity, 3),
            staging_similarity=round(staging_similarity, 3),
            iconography_similarity=round(iconography_similarity, 3),
            donor_leakage=round(donor_leakage, 3),
            canon_fit=round(canon_fit, 3),
            cultural_grounding=round(cultural_grounding, 3),
            veil_physics_rewrite=round(veil_physics_rewrite, 3),
            symbolic_transformation=round(symbolic_transformation, 3),
            source_diversity=round(source_diversity, 3),
            veil_distance=round(veil_distance, 3),
            gate_verdict=verdict,
            gate_reasons=gate_reasons,
        )