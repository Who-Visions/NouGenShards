"""
Unit tests for BAC 2027 Lilith Project Model and Who Visions Producer Fee Compliance.
Validates:
1. Budget allocations for $5k (Tier A) and $10k (Tier B) tiers.
2. Producer fee ceiling compliance (<= 20.0% BAC statutory cap).
3. Direct artist allocation (>= 50.0% of total budget).
4. Full budget sum invariant (sum of line items == total request).
"""
import pytest
from pathlib import Path


TIER_A_BUDGET = {
    "artist_fee": 2500.0,
    "materials": 1200.0,
    "venue_public": 400.0,
    "producer_fee": 900.0,
    "total": 5000.0,
}

TIER_B_BUDGET = {
    "artist_fee": 5000.0,
    "materials": 2200.0,
    "venue_public": 1000.0,
    "producer_fee": 1800.0,
    "total": 10000.0,
}


def test_tier_a_budget_math_and_caps():
    items_sum = (
        TIER_A_BUDGET["artist_fee"]
        + TIER_A_BUDGET["materials"]
        + TIER_A_BUDGET["venue_public"]
        + TIER_A_BUDGET["producer_fee"]
    )
    assert items_sum == TIER_A_BUDGET["total"]
    
    producer_pct = (TIER_A_BUDGET["producer_fee"] / TIER_A_BUDGET["total"]) * 100.0
    assert producer_pct <= 20.0, f"Producer fee {producer_pct}% exceeds BAC 20% cap"
    assert producer_pct == 18.0

    artist_pct = (TIER_A_BUDGET["artist_fee"] / TIER_A_BUDGET["total"]) * 100.0
    assert artist_pct >= 50.0, f"Artist allocation {artist_pct}% must be >= 50%"


def test_tier_b_budget_math_and_caps():
    items_sum = (
        TIER_B_BUDGET["artist_fee"]
        + TIER_B_BUDGET["materials"]
        + TIER_B_BUDGET["venue_public"]
        + TIER_B_BUDGET["producer_fee"]
    )
    assert items_sum == TIER_B_BUDGET["total"]
    
    producer_pct = (TIER_B_BUDGET["producer_fee"] / TIER_B_BUDGET["total"]) * 100.0
    assert producer_pct <= 20.0, f"Producer fee {producer_pct}% exceeds BAC 20% cap"
    assert producer_pct == 18.0

    artist_pct = (TIER_B_BUDGET["artist_fee"] / TIER_B_BUDGET["total"]) * 100.0
    assert artist_pct >= 50.0, f"Artist allocation {artist_pct}% must be >= 50%"


def test_dossier_file_exists_and_contains_invariants():
    import os
    dossier_path = Path(os.environ.get("WATCHTOWER_DIR", Path.home() / "Watchtower")) / "BAC_2027_LILITH_PROJECT_PRODUCER_MODEL.md"
    if not dossier_path.exists():
        pytest.skip(f"Dossier {dossier_path} not mounted in test environment")
    
    content = dossier_path.read_text(encoding="utf-8")
    assert "Brooklyn Arts Council" in content
    assert "18.0%" in content
    assert "@lilith.s_wardrobe" in content
    assert "Who Visions LLC" in content
    assert "Exploratory / Planning Artifact" in content
