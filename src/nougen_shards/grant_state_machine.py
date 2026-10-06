"""
Deterministic Grant State Transition Engine.
Enforces strict forward-only, skip-free transitions:
UNKNOWN -> INTAKE_VERIFIED -> FUNDER_MATCHED -> BUDGET_BALANCED -> SECTIONS_HASHED -> ARTIST_SIGNED -> READY_TO_SUBMIT
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class GrantState(str, enum.Enum):
    UNKNOWN = "UNKNOWN"
    INTAKE_VERIFIED = "INTAKE_VERIFIED"
    FUNDER_MATCHED = "FUNDER_MATCHED"
    BUDGET_BALANCED = "BUDGET_BALANCED"
    SECTIONS_HASHED = "SECTIONS_HASHED"
    ARTIST_SIGNED = "ARTIST_SIGNED"
    READY_TO_SUBMIT = "READY_TO_SUBMIT"


TRANSITION_RULES: Dict[GrantState, List[GrantState]] = {
    GrantState.UNKNOWN: [GrantState.INTAKE_VERIFIED],
    GrantState.INTAKE_VERIFIED: [GrantState.FUNDER_MATCHED],
    GrantState.FUNDER_MATCHED: [GrantState.BUDGET_BALANCED],
    GrantState.BUDGET_BALANCED: [GrantState.SECTIONS_HASHED],
    GrantState.SECTIONS_HASHED: [GrantState.ARTIST_SIGNED],
    GrantState.ARTIST_SIGNED: [GrantState.READY_TO_SUBMIT],
    GrantState.READY_TO_SUBMIT: [],
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal or skip transition is attempted."""
    pass


@dataclass
class GrantStateHistoryEntry:
    from_state: GrantState
    to_state: GrantState
    timestamp: float
    actor: str
    evidence: Dict[str, Any]


@dataclass
class GrantStateMachine:
    project_id: str
    current_state: GrantState = GrantState.UNKNOWN
    history: List[GrantStateHistoryEntry] = field(default_factory=list)

    def transition_to(
        self,
        target_state: GrantState,
        actor: str = "antigravity",
        evidence: Optional[Dict[str, Any]] = None,
    ) -> GrantStateHistoryEntry:
        allowed = TRANSITION_RULES.get(self.current_state, [])
        if target_state not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal state transition from {self.current_state.value} to {target_state.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

        entry = GrantStateHistoryEntry(
            from_state=self.current_state,
            to_state=target_state,
            timestamp=time.time(),
            actor=actor,
            evidence=evidence or {},
        )
        self.current_state = target_state
        self.history.append(entry)
        return entry
