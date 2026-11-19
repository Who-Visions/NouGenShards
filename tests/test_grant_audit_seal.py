"""Test suite for Grant Compiler Audit Seal generation and cryptographic verification."""
from nougen_shards.grant_compiler import (
    ArtistProjectSpec,
    GrantBudget,
    verify_grant_audit_seal,
)


def test_audit_seal_generation_on_valid_grant():
    budget = GrantBudget(
        artist_stipend=3000.0,
        materials_budget=1000.0,
        venue_budget=200.0,
        producer_fee=800.0,
        total_request=5000.0,
    )
    spec = ArtistProjectSpec(
        project_id="PROJ-SAKURA-2027",
        project_title="Sakura Soiree 2027",
        lead_artist="Dave Meralus",
        primary_borough="Brooklyn",
        target_funder="BAC_CAG",
        public_event_type="Exhibition & Tea Ceremony",
        free_public_access=True,
        budget=budget,
        narrative_summary="Community cultural gathering with high-contrast obsidian aesthetic.",
    )
    compiled = spec.compile_package()
    
    assert compiled["is_valid"] is True
    assert "audit_seal" in compiled
    seal = compiled["audit_seal"]
    assert seal["status"] == "AUDIT_VERIFIED"
    assert seal["project_id"] == "PROJ-SAKURA-2027"
    assert seal["statutory_compliance"]["artist_stipend_ratio"] == 0.60
    assert seal["statutory_compliance"]["producer_fee_ratio"] == 0.16
    assert seal["statutory_compliance"]["artist_retained_ip"] is True
    assert verify_grant_audit_seal(compiled, spec) is True


def test_audit_seal_tamper_detection():
    budget = GrantBudget(
        artist_stipend=3000.0,
        materials_budget=1000.0,
        venue_budget=200.0,
        producer_fee=800.0,
        total_request=5000.0,
    )
    spec = ArtistProjectSpec(
        project_id="PROJ-TAMPER-001",
        project_title="Original Project",
        lead_artist="Lead Artist",
        primary_borough="Brooklyn",
        target_funder="BAC_CAG",
        public_event_type="Performance",
        free_public_access=True,
        budget=budget,
        narrative_summary="Original narrative.",
    )
    compiled = spec.compile_package()
    
    # Tamper with compiled payload
    tampered_package = dict(compiled)
    tampered_package["seal_hash"] = "tampered_hash_value"
    
    assert verify_grant_audit_seal(tampered_package, spec) is False
