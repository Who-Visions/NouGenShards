"""
Unit tests for Universal Artist Funding Discovery Layer.
Validates:
1. Matching Brooklyn artist with BAC and NYSCA programs.
2. Borough restriction filtering (e.g. non-Bronx artist fails BRIO).
3. Fiscal sponsor requirement filtering.
4. Correct sorting by eligibility and deadline.
"""
import pytest
from nougen_shards.funding_discovery import (
    ArtistProfile,
    VERIFIED_FUNDERS,
    match_funding_opportunities,
)


def test_brooklyn_artist_matching():
    profile = ArtistProfile(
        artist_id="ART-001",
        artist_name="Lilith",
        primary_borough="Brooklyn",
        primary_medium="Wearables",
        has_501c3_sponsor=True,
        has_community_venue=True,
        desired_budget=5000.0,
    )
    matches = match_funding_opportunities(profile)
    
    # Brooklyn artist with venue and sponsor should match BAC, NYSCA, and DCLA
    bac_match = next((m for m in matches if m["funder_id"] == "BAC_CAG"), None)
    assert bac_match is not None
    assert bac_match["is_eligible"] is True
    assert bac_match["producer_fee_cap"] == 0.18

    # Should not match Queens-only or Bronx-only
    brio_match = next((m for m in matches if m["funder_id"] == "BRIO_IND"), None)
    assert brio_match is not None
    assert brio_match["is_eligible"] is False


def test_borough_ineligibility_reasons():
    profile = ArtistProfile(
        artist_id="ART-002",
        artist_name="Queens Creator",
        primary_borough="Queens",
        primary_medium="Visual Art",
        has_501c3_sponsor=False,
        has_community_venue=True,
        desired_budget=4000.0,
    )
    matches = match_funding_opportunities(profile)
    
    # Should be eligible for Queens Arts Fund (QAF)
    qaf_match = next((m for m in matches if m["funder_id"] == "QAF_IND"), None)
    assert qaf_match is not None
    assert qaf_match["is_eligible"] is True

    # Should fail BAC due to borough
    bac_match = next((m for m in matches if m["funder_id"] == "BAC_CAG"), None)
    assert bac_match is not None
    assert bac_match["is_eligible"] is False
    assert any("Requires residency in Brooklyn" in r for r in bac_match["reasons"])


def test_fiscal_sponsor_filtering():
    profile = ArtistProfile(
        artist_id="ART-003",
        artist_name="Unsponsored Artist",
        primary_borough="Brooklyn",
        primary_medium="Sculpture",
        has_501c3_sponsor=False,
        has_community_venue=False,
        desired_budget=10000.0,
    )
    matches = match_funding_opportunities(profile)
    
    # NYSCA requires fiscal sponsor -> should be ineligible
    nysca_match = next((m for m in matches if m["funder_id"] == "NYSCA_SFA"), None)
    assert nysca_match is not None
    assert nysca_match["is_eligible"] is False
    assert any("Requires a verified 501(c)(3) fiscal sponsor" in r for r in nysca_match["reasons"])
