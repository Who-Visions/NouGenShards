"""
Unit tests for Deterministic Grant State Machine.
Validates:
1. Valid end-to-end forward progression through all 6 transitions.
2. Rejection of state skips (e.g. UNKNOWN -> BUDGET_BALANCED).
3. Rejection of backward transitions (e.g. READY_TO_SUBMIT -> INTAKE_VERIFIED).
4. Full audit history logging.
"""
import pytest
from nougen_shards.grant_state_machine import (
    GrantState,
    GrantStateMachine,
    InvalidStateTransitionError,
)


def test_valid_forward_state_progression():
    sm = GrantStateMachine(project_id="BAC-2027-SAKURA-001")
    assert sm.current_state == GrantState.UNKNOWN

    sm.transition_to(GrantState.INTAKE_VERIFIED, evidence={"artist": "Dave Meralus"})
    assert sm.current_state == GrantState.INTAKE_VERIFIED

    sm.transition_to(GrantState.FUNDER_MATCHED, evidence={"funder": "BAC_CAG"})
    assert sm.current_state == GrantState.FUNDER_MATCHED

    sm.transition_to(GrantState.BUDGET_BALANCED, evidence={"total": 10000.0})
    assert sm.current_state == GrantState.BUDGET_BALANCED

    sm.transition_to(GrantState.SECTIONS_HASHED, evidence={"hash_count": 4})
    assert sm.current_state == GrantState.SECTIONS_HASHED

    sm.transition_to(GrantState.ARTIST_SIGNED, evidence={"ed25519": True})
    assert sm.current_state == GrantState.ARTIST_SIGNED

    sm.transition_to(GrantState.READY_TO_SUBMIT, evidence={"sealed": True})
    assert sm.current_state == GrantState.READY_TO_SUBMIT
    assert len(sm.history) == 6


def test_rejection_of_state_skips():
    sm = GrantStateMachine(project_id="SKIP-TEST-001")
    
    # Attempt to skip straight to BUDGET_BALANCED from UNKNOWN
    with pytest.raises(InvalidStateTransitionError) as excinfo:
        sm.transition_to(GrantState.BUDGET_BALANCED)
    
    assert "Illegal state transition from UNKNOWN to BUDGET_BALANCED" in str(excinfo.value)


def test_rejection_of_terminal_transitions():
    sm = GrantStateMachine(project_id="TERMINAL-TEST-001")
    sm.current_state = GrantState.READY_TO_SUBMIT
    
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(GrantState.UNKNOWN)
