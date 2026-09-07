"""
Full 10-Stage Pipeline for Shadow Dweller Remix Refinery:
HARVEST -> ATOMIZE -> STRIP -> ANCHOR -> MUTATE -> BRAID -> COLLIDE -> SCORE -> PROVE -> SHARD
"""

import re
from typing import List, Dict, Any, Optional
from .models import (
    ProcessDonorCard,
    CanonAnchor,
    MutationOperator,
    MutationTrace,
    CandidateMechanism,
    CollisionReport,
    TransformationScore,
    ProvenanceLedger,
    MechanismStatus,
)
from .mutations import MutationEngine
from .scoring import ScoringEngine
from .canon_gate import CanonGate
from .provenance import ProvenanceManager
from .adapters.shards import ShardRefineryAdapter


class RemixRefineryPipeline:
    """Executes end-to-end creative compilation of process donors into native canon."""

    def __init__(self, provenance_manager: Optional[ProvenanceManager] = None):
        self.prov_mgr = provenance_manager or ProvenanceManager()

    def run(
        self,
        donor_card: ProcessDonorCard,
        canon_anchors: List[CanonAnchor],
        independent_sources: List[str],
        mutation_ops: Optional[List[MutationOperator]] = None,
        scene_applications: Optional[List[str]] = None,
        target_sharding: bool = True,
    ) -> CandidateMechanism:
        # Stage 1: HARVEST - already captured in donor_card.creative_problem
        # Stage 2: ATOMIZE - techniques extracted in donor_card.extracted_techniques
        # Stage 3: STRIP - Purge forbidden surface elements from atom descriptions
        stripped_atoms = []
        stripped_hits = []
        for atom in donor_card.extracted_techniques:
            atom_mech = atom.mechanism
            for forbidden in donor_card.forbidden_surface_elements:
                pattern = re.compile(r'\b' + re.escape(forbidden) + r'\b', re.IGNORECASE)
                if pattern.search(atom_mech):
                    stripped_hits.append(forbidden)
                    atom_mech = pattern.sub("[STRIPPED_DONOR_ELEMENT]", atom_mech)
            atom_copy = atom.model_copy(update={"mechanism": atom_mech})
            stripped_atoms.append(atom_copy)

        # Stage 4: ANCHOR - Combine stripped atoms with native canon anchors
        raw_native_draft = " ".join([a.mechanism for a in stripped_atoms])
        anchor_context = " | ".join([f"[{anc.lineage}: {anc.concept}]" for anc in canon_anchors])

        # Stage 5: MUTATE - Apply at least 3 distinct mutation operators
        if not mutation_ops:
            mutation_ops = [
                MutationOperator.CULTURAL_GROUNDING,
                MutationOperator.PHYSICS_REWRITE,
                MutationOperator.SYMBOLIC_SUBSTITUTION,
                MutationOperator.CONSEQUENCE_INVERSION,
            ]
        
        mutated_text, mutation_traces = MutationEngine.apply_chain(
            raw_native_draft, mutation_ops, context=anchor_context
        )

        # Stage 6: BRAID - Interleave with independent sources
        braided_expression = (
            f"{mutated_text}\n\n"
            f"**Braided Synthesis**: Cross-fused with independent sources ({', '.join(independent_sources)}) "
            f"and rooted in {len(canon_anchors)} native Veilverse anchor vectors."
        )

        # Stage 7: COLLIDE - Canon governance & contradiction check
        collision_report = CanonGate.evaluate_collision(
            braided_expression, [a.concept for a in canon_anchors]
        )

        # Stage 8: SCORE - Calculate donor_leakage and veil_distance
        scores = ScoringEngine.calculate(
            expression_text=braided_expression,
            forbidden_elements=donor_card.forbidden_surface_elements,
            canon_anchors=[a.concept for a in canon_anchors],
            independent_sources=independent_sources,
            mutations_count=len(mutation_traces),
        )

        # Determine final status
        status = CanonGate.determine_status(collision_report, scores)

        candidate = CandidateMechanism(
            atoms=stripped_atoms,
            canon_anchors=canon_anchors,
            mutations=mutation_traces,
            independent_donors=independent_sources,
            native_expression=braided_expression,
            scene_applications=scene_applications or [
                "Shadow Dweller infiltration through Veil resonance perimeter",
                "Marasa ancestral consultation during temporal threshold collapse",
            ],
            status=status,
            collision_report=collision_report,
            scores=scores,
        )

        # Stage 9: PROVE - Persist transformation ledger
        ledger = ProvenanceLedger(
            donor_id=donor_card.donor_id,
            candidate_id=candidate.candidate_id,
            creative_problem=donor_card.creative_problem,
            abstracted_elements=[a.function for a in stripped_atoms],
            stripped_forbidden_matches=stripped_hits,
            mutations_applied=[m.operator for m in mutation_traces],
            braided_sources=independent_sources,
            scores=scores,
            status=status,
        )

        # Stage 10: SHARD - Ingest native mechanism if approved
        if target_sharding and status in [MechanismStatus.CANON_CANDIDATE, MechanismStatus.REVIEW, MechanismStatus.EXPERIMENTAL]:
            shard_id = ShardRefineryAdapter.capture_to_shards(candidate, ledger)
            candidate.candidate_id = f"{candidate.candidate_id}_shard_{shard_id}" if shard_id else candidate.candidate_id
            ledger.shard_id = shard_id

        self.prov_mgr.record(ledger)
        return candidate