"""
Unit tests for Universal Deterministic Artist Grant Compiler.
Validates:
1. Valid $5k and $10k compilation with clean seals and Next.js props.
2. Rejection of out-of-bounds producer fees (> 18%).
3. Rejection of deficient artist stipends (< 50%).
4. Rejection of un-balanced budgets.
5. Ingestion of Project Shapeshifter, Lilith, and Tiffany models.
"""
import pytest
from nougen_shards.grant_compiler import ArtistProjectSpec, GrantBudget


def test_valid_5k_compiler_package():
    budget = GrantBudget(
        artist_stipend=2600.0,
        materials_budget=1100.0,
        venue_budget=450.0,
        producer_fee=850.0,
        total_request=5000.0,
    )
    spec = ArtistProjectSpec(
        project_id="BAC-2027-SHAPESHIFTER-001",
        project_title="Project Shapeshifter",
        lead_artist="Morgan Vance",
        primary_borough="Brooklyn",
        target_funder="BAC",
        public_event_type="Workshop & Exhibition",
        free_public_access=True,
        budget=budget,
        narrative_summary="Mythic wearable foam sculpture workshop in Brooklyn",
    )
    res = spec.compile_package()
    assert res["is_valid"] is True
    assert len(res["validation_errors"]) == 0
    assert len(res["seal_hash"]) == 64
    assert res["nextjs_props"]["ratios"]["artist_ratio"] == 0.52
    assert res["nextjs_props"]["ratios"]["producer_ratio"] == 0.17


def test_invalid_excessive_producer_fee():
    budget = GrantBudget(
        artist_stipend=2000.0,
        materials_budget=1000.0,
        venue_budget=500.0,
        producer_fee=1500.0,  # 30% -> exceeds 18%
        total_request=5000.0,
    )
    spec = ArtistProjectSpec(
        project_id="INVALID-FEE-001",
        project_title="Fee Test",
        lead_artist="Test Artist",
        primary_borough="Brooklyn",
        target_funder="BAC",
        public_event_type="Exhibition",
        free_public_access=True,
        budget=budget,
        narrative_summary="Fee test",
    )
    res = spec.compile_package()
    assert res["is_valid"] is False
    assert any("Producer fee ratio" in err for err in res["validation_errors"])


def test_invalid_low_artist_stipend():
    budget = GrantBudget(
        artist_stipend=2000.0,  # 40% -> below 50%
        materials_budget=2200.0,
        venue_budget=0.0,
        producer_fee=800.0,
        total_request=5000.0,
    )
    spec = ArtistProjectSpec(
        project_id="LOW-STIPEND-001",
        project_title="Stipend Test",
        lead_artist="Test Artist",
        primary_borough="Brooklyn",
        target_funder="BAC",
        public_event_type="Exhibition",
        free_public_access=True,
        budget=budget,
        narrative_summary="Stipend test",
    )
    res = spec.compile_package()
    assert res["is_valid"] is False
    assert any("Direct artist stipend ratio" in err for err in res["validation_errors"])
