"""Unit tests for the Recurse Engine."""
import pytest
from tools.recurse_engine import RecurseEntry, add_entry, list_entries, audit_ledger


def test_recurse_entry_lifecycle(tmp_path):
    db_file = tmp_path / "test_recurse.db"
    entry = RecurseEntry(
        id="xoah-01",
        entity="xoah",
        category="dialogue",
        title="Dust on the Lens",
        setup="The wind always blows from the graves.",
        setup_context="Vol 1 Act 1 Scene 2",
        first_echo="The dust never settled, did it?",
        first_echo_context="Vol 2 Act 2",
        inversion="The wind isn't coming from the graves; it's blowing towards them.",
        inversion_context="Vol 3 Act 3 SDX",
        final_payoff="I was the wind.",
        final_payoff_context="Vol 5 Climax",
        rewatch_score=10
    )

    eid = add_entry(entry, db_path=db_file)
    assert eid == "xoah-01"

    entries = list_entries(entity="xoah", db_path=db_file)
    assert len(entries) == 1
    assert entries[0].title == "Dust on the Lens"
    assert entries[0].is_complete() is True

    audit = audit_ledger(db_path=db_file)
    assert audit["complete_entries"] == 1
    assert audit["total_entries"] == 1
    assert len(audit["issues"]) == 0


def test_recurse_entry_guardrail_detection(tmp_path):
    db_file = tmp_path / "test_recurse.db"
    bad_entry = RecurseEntry(
        id="bad-01",
        entity="xoah",
        category="combat_line",
        title="Premature Power",
        setup="I will use tear traversal to finish you.",
        setup_context="Vol 1 Act 1",
    )
    add_entry(bad_entry, db_path=db_file)

    audit = audit_ledger(db_path=db_file)
    assert audit["complete_entries"] == 0
    assert len(audit["issues"]) == 1
    warnings = audit["issues"][0]["warnings"]
    assert any("violates Vol 1 Level 1-3 ceiling" in w for w in warnings)
