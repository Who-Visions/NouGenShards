"""
Unit tests for BAC 2027 Tiffany Independent Artist Project Model and Who Visions Production Scope.
Validates:
1. Budget allocations for $5k (Tier A) and $10k (Tier B) tiers.
2. Who Visions production scope fee compliance (<= 20.0% statutory cap, exactly 17.0%).
3. Direct artist allocation (>= 50.0% of total grant budget, exactly 52.0%).
4. Sum of line items invariant (sum of all line items == total grant request).
5. Document integrity and structural invariants.
"""
import pytest
from pathlib import Path


TIER_A_BUDGET = {
    "artist_stipend": 2600.0,
    "materials": 1100.0,
    "venue_public": 450.0,
    "production_scope": 850.0,
    "total": 5000.0,
}

TIER_B_BUDGET = {
    "artist_stipend": 5200.0,
    "materials": 2100.0,
    "venue_public": 1000.0,
    "production_scope": 1700.0,
    "total": 10000.0,
}


def test_tier_a_tiffany_budget_math_and_caps():
    items_sum = (
        TIER_A_BUDGET["artist_stipend"]
        + TIER_A_BUDGET["materials"]
        + TIER_A_BUDGET["venue_public"]
        + TIER_A_BUDGET["production_scope"]
    )
    assert items_sum == TIER_A_BUDGET["total"]

    prod_pct = (TIER_A_BUDGET["production_scope"] / TIER_A_BUDGET["total"]) * 100.0
    assert prod_pct <= 20.0, f"Production scope fee {prod_pct}% exceeds BAC 20% cap"
    assert prod_pct == 17.0

    artist_pct = (TIER_A_BUDGET["artist_stipend"] / TIER_A_BUDGET["total"]) * 100.0
    assert artist_pct >= 50.0, f"Artist allocation {artist_pct}% must be >= 50%"
    assert artist_pct == 52.0


def test_tier_b_tiffany_budget_math_and_caps():
    items_sum = (
        TIER_B_BUDGET["artist_stipend"]
        + TIER_B_BUDGET["materials"]
        + TIER_B_BUDGET["venue_public"]
        + TIER_B_BUDGET["production_scope"]
    )
    assert items_sum == TIER_B_BUDGET["total"]

    prod_pct = (TIER_B_BUDGET["production_scope"] / TIER_B_BUDGET["total"]) * 100.0
    assert prod_pct <= 20.0, f"Production scope fee {prod_pct}% exceeds BAC 20% cap"
    assert prod_pct == 17.0

    artist_pct = (TIER_B_BUDGET["artist_stipend"] / TIER_B_BUDGET["total"]) * 100.0
    assert artist_pct >= 50.0, f"Artist allocation {artist_pct}% must be >= 50%"
    assert artist_pct == 52.0


def test_tiffany_dossier_file_exists_and_contains_invariants():
    dossier_path = Path(r"C:\Users\super\Watchtower\BAC_2027_TIFFANY_ARTIST_PROJECT_MODEL.md")
    assert dossier_path.exists(), "BAC Tiffany Artist Project Model document must exist"

    content = dossier_path.read_text(encoding="utf-8")
    assert "Brooklyn Arts Council" in content
    assert "17.0%" in content
    assert "Tiffany" in content
    assert "Who Visions LLC" in content
    assert "100% Artist-Owned Project" in content
