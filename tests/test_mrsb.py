"""Unit tests for the Learn With Mrs. B project engine (nougen_shards.mrsb)."""

import pytest
from nougen_shards import mrsb


def test_audit_assets():
    """Verify asset audit returns expected structure."""
    res = mrsb.audit_assets()
    assert "svgs" in res
    assert "alphabet_plates" in res
    assert "unit_see_plates" in res
    assert "manifests" in res
    assert res["alphabet_plates"]["total"] >= 26
    assert len(res["alphabet_plates"]["missing_letters"]) == 0


def test_lineage_and_character_dna():
    """Verify character DNA lookup for core and community helpers."""
    lineage = mrsb.get_lineage()
    assert "characters" in lineage
    
    mrs_b = mrsb.get_character_dna("mrs_b")
    assert mrs_b is not None
    assert "Meralus" in mrs_b.get("name", "")

    kam = mrsb.get_character_dna("kam_the_police_helper")
    assert kam is not None
    assert "Kam" in kam.get("name", "")


def test_recursion_map():
    """Verify the 4-stage recursive lesson ledger for all units."""
    rec_map = mrsb.get_recursion_map()
    assert len(rec_map) == 8
    for uid in range(1, 9):
        assert uid in rec_map
        unit = rec_map[uid]
        assert "setup" in unit
        assert "first_echo" in unit
        assert "inversion" in unit
        assert "final_payoff" in unit

    u4 = mrsb.get_recursion_map(4)
    assert u4["unit"] == 4
    assert "Officer Kam" in u4["setup"]


def test_project_status():
    """Verify project status dashboard structure."""
    status = mrsb.project_status()
    assert status["project"] == "Learn With Mrs. B: ESOL Coloring & Activity Masterclass"
    assert status["status"]["alphabet_complete"] is True
    assert status["pricing"]["usd"] == 9.99


def test_recall_shards():
    """Verify shard recall surfaces Mrs. B and recursion intelligence."""
    results = mrsb.recall_shards("Mrs. B", limit=3)
    assert isinstance(results, list)
    assert len(results) > 0
    assert any("Mrs. B" in r["title"] or "Mrs. B" in r["snippet"] for r in results)
