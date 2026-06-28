"""
Hermetic tests for Griot's verification-gated consolidation.

Covers the adversarial verifier (`_parse_verdict`, `verify_invariant`), the
verification gate inside `consolidate`, conflict detection (`_detect_conflict`,
`find_conflicts`), and offline backward-compatibility. All tests run without a
reachable Ollama; the verifier path is exercised by monkeypatching
`_verifier_available` / `verify_invariant` / `_complete` directly.
"""

import tempfile
from pathlib import Path

import pytest

from nougen_shards import griot
import nougen_shards.core as core


# ---------------------------------------------------------------------------
# Temp-DB fixture (pattern copied from tests/test_dual_system.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(monkeypatch):
    """Isolated single-DB environment routed entirely to index 1."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(core, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(core, "get_db_path", mock_get_db_path)

        monkeypatch.setattr(core, "get_routing_index", lambda fhash: 1)
        monkeypatch.setattr(core, "get_write_index", lambda fhash: 1)

        core.init_db(1)
        yield temp_path


def _insert_rule(subject, predicate, confidence=1.0):
    """Insert a semantic_knowledge row directly into index-1 DB."""
    conn = core.get_connection(1)
    try:
        conn.execute(
            "INSERT INTO semantic_knowledge "
            "(subject, predicate, confidence_score, domain_key, updated_at) "
            "VALUES (?, ?, ?, 'global', '2026-06-28T00:00:00Z')",
            (subject, predicate, confidence))
        conn.commit()
    finally:
        conn.close()


def _all_rules():
    """Read every semantic_knowledge row from index-1 DB."""
    conn = core.get_connection(1)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT subject, predicate, confidence_score FROM semantic_knowledge")]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. _parse_verdict
# ---------------------------------------------------------------------------

def test_parse_verdict_accept_json():
    out = griot.Griot._parse_verdict('{"verdict": "accept", "reason": "supported"}')
    assert out["verdict"] == "accept"
    assert out["reason"] == "supported"


def test_parse_verdict_reject_json():
    out = griot.Griot._parse_verdict('{"verdict": "reject", "reason": "speculative"}')
    assert out["verdict"] == "reject"
    assert out["reason"] == "speculative"


def test_parse_verdict_prose_accept():
    out = griot.Griot._parse_verdict("After review I would accept this rule.")
    assert out["verdict"] == "accept"
    assert out["reason"] == "heuristic"


def test_parse_verdict_ambiguous_garbage_rejects():
    out = griot.Griot._parse_verdict("asdf qwerty 12345 ???")
    assert out["verdict"] == "reject"


def test_parse_verdict_both_accept_and_reject_rejects():
    # "accept" present but "reject" also present -> default to reject.
    out = griot.Griot._parse_verdict("I could accept but I will reject this.")
    assert out["verdict"] == "reject"


# ---------------------------------------------------------------------------
# 2. verify_invariant
# ---------------------------------------------------------------------------

# The shipped VERIFICATION_PROMPT contains literal JSON braces that str.format
# would treat as replacement fields; supply a format-safe template so the test
# exercises verify_invariant's real control flow (prompt -> _complete -> parse)
# without editing the source module.
_SAFE_VERIFY_PROMPT = "verify {content} :: {subject} :: {predicate}"


def test_verify_invariant_unavailable_when_complete_none(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(griot, "VERIFICATION_PROMPT", _SAFE_VERIFY_PROMPT)
    monkeypatch.setattr(g, "_complete", lambda messages: None)
    out = g.verify_invariant("source text", {"subject": "X", "predicate": "Y"})
    assert out == {"verdict": "accept", "reason": "verification_unavailable"}


def test_verify_invariant_reject_json(monkeypatch):
    g = griot.Griot()
    monkeypatch.setattr(griot, "VERIFICATION_PROMPT", _SAFE_VERIFY_PROMPT)
    monkeypatch.setattr(
        g, "_complete",
        lambda messages: '{"verdict": "reject", "reason": "not supported"}')
    out = g.verify_invariant("source text", {"subject": "X", "predicate": "Y"})
    assert out["verdict"] == "reject"
    assert out["reason"] == "not supported"


# ---------------------------------------------------------------------------
# 3. Offline backward-compat: no model -> verifier inactive, old-loop behavior
# ---------------------------------------------------------------------------

def test_consolidate_offline_backward_compat(temp_db):
    g = griot.Griot()
    # No Ollama in tests -> verifier unavailable.
    assert g._verifier_available() is False

    core.capture(
        event_type="TEST",
        title="Offline Log",
        content="Interaction about Memory which is unconsolidated.")

    def extractor(content):
        return [
            {"subject": "Alpha", "predicate": "must be deterministic"},
            {"subject": "Beta", "predicate": "should persist offline"},
        ]

    result = g.consolidate(limit=10, extractor=extractor, verify=True)

    assert result["verified"] is False
    assert result["rejected"] == []
    assert result["new_invariants_extracted"] == 2
    assert result["shards_consolidated"] == 1

    subjects = {r["subject"] for r in _all_rules()}
    assert subjects == {"Alpha", "Beta"}


# ---------------------------------------------------------------------------
# 4. Verification gating: accept one subject, reject another
# ---------------------------------------------------------------------------

def test_consolidate_verification_gates_rejected_invariants(temp_db, monkeypatch):
    g = griot.Griot()

    core.capture(
        event_type="TEST",
        title="Gated Log",
        content="Source content for verification gating.")

    monkeypatch.setattr(g, "_verifier_available", lambda: True)

    def fake_verify(source_content, invariant):
        if invariant["subject"] == "Keep":
            return {"verdict": "accept", "reason": "ok"}
        return {"verdict": "reject", "reason": "no support"}
    monkeypatch.setattr(g, "verify_invariant", fake_verify)

    def extractor(content):
        return [
            {"subject": "Keep", "predicate": "P1"},
            {"subject": "Drop", "predicate": "P2"},
        ]

    result = g.consolidate(limit=10, extractor=extractor, verify=True)

    assert result["verified"] is True
    assert result["new_invariants_extracted"] == 1

    rejected_subjects = {r["subject"] for r in result["rejected"]}
    assert "Drop" in rejected_subjects
    assert "Keep" not in rejected_subjects

    # Only "Keep" persisted.
    persisted = {r["subject"] for r in _all_rules()}
    assert persisted == {"Keep"}

    listed = {r["subject"] for r in griot.Griot.list_rules()}
    assert "Keep" in listed
    assert "Drop" not in listed


# ---------------------------------------------------------------------------
# 5. Conflict detection during consolidate (verify off to isolate)
# ---------------------------------------------------------------------------

def test_consolidate_detects_conflict(temp_db):
    g = griot.Griot()

    _insert_rule("Docker", "must use read-only root")

    core.capture(
        event_type="TEST",
        title="Docker Log",
        content="Today we discussed Docker root filesystem policy.")

    def extractor(content):
        return [{"subject": "Docker", "predicate": "may use writable root"}]

    result = g.consolidate(limit=10, extractor=extractor, verify=False)

    assert result["verified"] is False
    assert len(result["conflicts"]) == 1
    conflict = result["conflicts"][0]
    assert conflict["subject"] == "Docker"
    assert conflict["candidate"] == "may use writable root"
    assert conflict["existing"] == "must use read-only root"


# ---------------------------------------------------------------------------
# 6. find_conflicts
# ---------------------------------------------------------------------------

def test_find_conflicts_returns_only_conflicting_group(temp_db):
    _insert_rule("Cache", "must be write-through")
    _insert_rule("Cache", "must be write-back")
    _insert_rule("Queue", "must be FIFO")

    conflicts = griot.Griot.find_conflicts()

    assert len(conflicts) == 1
    group = conflicts[0]
    assert group["subject"].lower() == "cache"
    predicates = {r["predicate"] for r in group["rules"]}
    assert predicates == {"must be write-through", "must be write-back"}
