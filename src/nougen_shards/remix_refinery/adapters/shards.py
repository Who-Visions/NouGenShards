"""
Shards Ingestion Adapter for Remix Refinery.
Only ingests canon-safe native mechanisms. Strips all donor surface references.
Attaches provenance metadata as process_reference:* tags.
"""

from typing import Optional, Dict, Any, List
from ..models import CandidateMechanism, ProvenanceLedger, MechanismStatus


class ShardRefineryAdapter:
    """Converts surviving native mechanisms into durable NouGen Shards."""

    @classmethod
    def capture_to_shards(
        cls,
        candidate: CandidateMechanism,
        ledger: ProvenanceLedger,
        author: str = "remix_refinery",
    ) -> Optional[int]:
        """
        Persists a verified native mechanism into NouGenShards.
        Refuses to shard rejected or quarantined candidates.
        """
        if candidate.status in [MechanismStatus.REJECTED, MechanismStatus.QUARANTINED]:
            raise ValueError(f"Cannot shard candidate with status {candidate.status}: leakage or collision present.")

        # Build clean native payload
        title = f"Shadow Dweller Mechanism: {candidate.candidate_id}"
        
        content = (
            f"# {title}\n\n"
            f"**Status**: {candidate.status.value.upper()}\n"
            f"**Veil Distance**: {candidate.scores.veil_distance:.2f} | **Donor Leakage**: {candidate.scores.donor_leakage:.2f}\n\n"
            f"## Native Expression\n{candidate.native_expression}\n\n"
            f"## Scene Applications\n" + "\n".join(f"- {app}" for app in candidate.scene_applications) + "\n\n"
            f"## Lineage & Anchors\n" + "\n".join(f"- [{anc.lineage}] {anc.concept}" for anc in candidate.canon_anchors) + "\n\n"
            f"## Provenance\n"
            f"- Ledger ID: `{ledger.ledger_id}`\n"
            f"- Braided Sources: {', '.join(candidate.independent_donors)}\n"
            f"- Mutations Applied: {len(candidate.mutations)} distinct operators\n"
        )

        tags = [
            "shadow-dweller",
            "veilverse",
            "native-mechanism",
            "remix-refinery",
            f"status:{candidate.status.value}",
            f"ledger:{ledger.ledger_id}",
            f"process_reference:{ledger.donor_id}",
        ]

        # Ingest using core capture
        try:
            from nougen_shards.core import capture
            success = capture(
                event_type="creative_mechanism",
                title=title,
                content=content,
                tags=tags,
                source_uri=f"remix_refinery/{ledger.ledger_id}",
            )
            return 1 if success else None
        except Exception as e:
            # Fallback or offline simulation
            print(f"[!] Warning: capture failed: {e}")
            return None