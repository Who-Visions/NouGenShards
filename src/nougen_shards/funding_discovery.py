"""
Universal Deterministic Artist Funding Discovery Layer Module.
Indexes, evaluates, and matches artist profiles against verified municipal,
state, and national grant programs with statutory eligibility enforcement.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class FunderOpportunity:
    funder_id: str
    program_name: str
    agency_name: str
    max_award: float
    eligible_boroughs: List[str]  # e.g. ["Brooklyn"], ["*"] for all
    requires_501c3_sponsor: bool
    requires_community_venue: bool
    producer_fee_cap: float
    deadline_date: str  # YYYY-MM-DD
    description: str

    def check_eligibility(self, profile: ArtistProfile) -> Dict[str, Any]:
        eligible = True
        reasons = []

        # Borough check
        if "*" not in self.eligible_boroughs and profile.primary_borough not in self.eligible_boroughs:
            eligible = False
            reasons.append(f"Requires residency in {', '.join(self.eligible_boroughs)} (artist is in {profile.primary_borough})")

        # Fiscal sponsor check
        if self.requires_501c3_sponsor and not profile.has_501c3_sponsor:
            eligible = False
            reasons.append("Requires a verified 501(c)(3) fiscal sponsor")

        # Community venue / public component check
        if self.requires_community_venue and not profile.has_community_venue:
            eligible = False
            reasons.append("Requires a confirmed free public community venue / component")

        # Budget ceiling check
        if profile.desired_budget > self.max_award:
            reasons.append(f"Desired budget ${profile.desired_budget:,.2f} exceeds program max award ${self.max_award:,.2f}")

        return {
            "funder_id": self.funder_id,
            "program_name": self.program_name,
            "agency_name": self.agency_name,
            "is_eligible": eligible,
            "max_award": self.max_award,
            "deadline": self.deadline_date,
            "reasons": reasons,
            "producer_fee_cap": self.producer_fee_cap,
        }


@dataclass
class ArtistProfile:
    artist_id: str
    artist_name: str
    primary_borough: str
    primary_medium: str
    has_501c3_sponsor: bool
    has_community_venue: bool
    desired_budget: float


# Canonical registry of verified funders
VERIFIED_FUNDERS: List[FunderOpportunity] = [
    FunderOpportunity(
        funder_id="BAC_CAG",
        program_name="Community Arts Grants",
        agency_name="Brooklyn Arts Council",
        max_award=10000.0,
        eligible_boroughs=["Brooklyn"],
        requires_501c3_sponsor=False,  # Direct up to $5k, sponsored up to $10k
        requires_community_venue=True,
        producer_fee_cap=0.18,
        deadline_date="2026-10-11",
        description="Supports Brooklyn-based artists creating public community arts experiences.",
    ),
    FunderOpportunity(
        funder_id="NYSCA_SFA",
        program_name="Support for Artists",
        agency_name="New York State Council on the Arts",
        max_award=10000.0,
        eligible_boroughs=["*"],
        requires_501c3_sponsor=True,
        requires_community_venue=False,
        producer_fee_cap=0.15,
        deadline_date="2026-11-15",
        description="Statewide support for independent artists creating new original works.",
    ),
    FunderOpportunity(
        funder_id="DCLA_CDF",
        program_name="Cultural Development Fund",
        agency_name="NYC Department of Cultural Affairs",
        max_award=25000.0,
        eligible_boroughs=["*"],
        requires_501c3_sponsor=True,
        requires_community_venue=True,
        producer_fee_cap=0.20,
        deadline_date="2026-11-30",
        description="Supports cultural programming across all five boroughs of NYC.",
    ),
    FunderOpportunity(
        funder_id="BRIO_IND",
        program_name="BRIO Artist Award",
        agency_name="Bronx Council on the Arts",
        max_award=5000.0,
        eligible_boroughs=["Bronx"],
        requires_501c3_sponsor=False,
        requires_community_venue=False,
        producer_fee_cap=0.0,
        deadline_date="2026-12-01",
        description="Direct individual artist awards for Bronx-resident creators.",
    ),
    FunderOpportunity(
        funder_id="QAF_IND",
        program_name="Queens Arts Fund",
        agency_name="New York Foundation for the Arts / QCA",
        max_award=5000.0,
        eligible_boroughs=["Queens"],
        requires_501c3_sponsor=False,
        requires_community_venue=True,
        producer_fee_cap=0.15,
        deadline_date="2026-12-15",
        description="Grants for Queens-based artists to produce free public cultural events.",
    ),
]


def match_funding_opportunities(profile: ArtistProfile) -> List[Dict[str, Any]]:
    matches = []
    for funder in VERIFIED_FUNDERS:
        eval_res = funder.check_eligibility(profile)
        matches.append(eval_res)
    
    # Sort eligible opportunities first, then by deadline
    matches.sort(key=lambda x: (not x["is_eligible"], x["deadline"]))
    return matches
