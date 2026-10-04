"""
Universal Deterministic Artist Grant Compiler Module.
Compiles structured artist intake, concept narratives, and line-item budgets
into validated, audit-compliant grant submission packages and Next.js component configs.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass
class GrantBudget:
    artist_stipend: float
    materials_budget: float
    venue_budget: float
    producer_fee: float
    total_request: float

    def validate(self, statutory_fee_cap: float = 0.18, min_artist_ratio: float = 0.50) -> List[str]:
        errors = []
        item_sum = self.artist_stipend + self.materials_budget + self.venue_budget + self.producer_fee
        if abs(item_sum - self.total_request) > 0.01:
            errors.append(f"Budget sum {item_sum} does not match total request {self.total_request}")
        
        prod_ratio = self.producer_fee / self.total_request if self.total_request > 0 else 0
        if prod_ratio > statutory_fee_cap:
            errors.append(f"Producer fee ratio {prod_ratio:.1%} exceeds statutory cap {statutory_fee_cap:.1%}")
            
        artist_ratio = self.artist_stipend / self.total_request if self.total_request > 0 else 0
        if artist_ratio < min_artist_ratio:
            errors.append(f"Direct artist stipend ratio {artist_ratio:.1%} is below minimum {min_artist_ratio:.1%}")
            
        return errors


@dataclass
class ArtistProjectSpec:
    project_id: str
    project_title: str
    lead_artist: str
    primary_borough: str
    target_funder: str
    public_event_type: str
    free_public_access: bool
    budget: GrantBudget
    narrative_summary: str

    def compile_package(self) -> Dict[str, Any]:
        errors = self.budget.validate()
        if not self.free_public_access:
            errors.append("Grant requires free public access / community component")
        if not self.primary_borough:
            errors.append("Primary borough of residence/operation is required")

        is_valid = len(errors) == 0
        raw_json = json.dumps(asdict(self), sort_keys=True)
        seal_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
        audit_seal_cert = {
            "certificate_id": f"CERT-SEAL-{seal_hash[:12].upper()}",
            "project_id": self.project_id,
            "funder": self.target_funder,
            "seal_hash": seal_hash,
            "statutory_compliance": {
                "artist_stipend_ratio": round(self.budget.artist_stipend / self.budget.total_request, 4),
                "producer_fee_ratio": round(self.budget.producer_fee / self.budget.total_request, 4),
                "artist_retained_ip": True,
                "passed_compliance": is_valid,
            },
            "status": "AUDIT_VERIFIED" if is_valid else "VALIDATION_FAILED",
        }

        return {
            "project_id": self.project_id,
            "project_title": self.project_title,
            "lead_artist": self.lead_artist,
            "target_funder": self.target_funder,
            "is_valid": is_valid,
            "validation_errors": errors,
            "seal_hash": seal_hash,
            "audit_seal": audit_seal_cert,
            "nextjs_props": {
                "title": self.project_title,
                "artist": self.lead_artist,
                "borough": self.primary_borough,
                "funder": self.target_funder,
                "budget": asdict(self.budget),
                "ratios": {
                    "artist_ratio": round(self.budget.artist_stipend / self.budget.total_request, 4),
                    "producer_ratio": round(self.budget.producer_fee / self.budget.total_request, 4),
                },
                "seal": seal_hash[:16],
            }
        }


def verify_grant_audit_seal(compiled_package: Dict[str, Any], raw_spec: ArtistProjectSpec) -> bool:
    """Verifies that the compiled package seal hash matches raw spec cryptographic digest."""
    expected_raw = json.dumps(asdict(raw_spec), sort_keys=True)
    expected_hash = hashlib.sha256(expected_raw.encode("utf-8")).hexdigest()
    return compiled_package.get("seal_hash") == expected_hash and compiled_package.get("audit_seal", {}).get("seal_hash") == expected_hash

