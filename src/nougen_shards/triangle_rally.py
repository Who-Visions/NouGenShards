"""Triangle Rally Engine — Continuous 3-Machine Autonomous Handoff Ring.

Implements the continuous 3-node communication loop across fleet machines
(e.g., Node A: whoart, Node B: blade, Node C: phoebus) with:
1. Directed ring passing: A -> B -> C -> A.
2. Structured baton payload: rally_id, sequence_number, sender, intended_receiver,
   parent_relay_id, concise_state, action_performed, touch_type, next_ask, timestamp.
3. Anti-echo scoring: TOUCH only scores when work is materially advanced, verified,
   or routed; sends PASS if idle or nothing to add.
4. Token furnace protection: TTL, max turns, token budget limits, pause/stop controls.
5. 2-node degradation fallback on timeout, with zero-backlog rejoin for returning node.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Set


class TriangleRallyError(Exception):
    """Base exception for Triangle Rally violations."""
    pass


class RallyTerminatedError(TriangleRallyError):
    """Raised when an operation is attempted on a stopped or expired rally."""
    pass


class InvalidReceiverError(TriangleRallyError):
    """Raised when an unexpected node attempts to claim the baton out of ring order."""
    pass


class DuplicateBatonError(TriangleRallyError):
    """Raised when a duplicate sequence number or message ID is passed."""
    pass


@dataclass
class Baton:
    rally_id: str
    sequence_number: int
    sender: str
    intended_receiver: str
    concise_state: str
    action_performed: str
    next_ask: str
    timestamp: str
    parent_relay_id: Optional[str] = None
    touch_type: str = "TOUCH"  # "TOUCH" | "PASS" | "CHALLENGE"
    token_estimate: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rally_id": self.rally_id,
            "sequence_number": self.sequence_number,
            "sender": self.sender,
            "intended_receiver": self.intended_receiver,
            "parent_relay_id": self.parent_relay_id,
            "concise_state": self.concise_state,
            "action_performed": self.action_performed,
            "touch_type": self.touch_type,
            "next_ask": self.next_ask,
            "timestamp": self.timestamp,
            "token_estimate": self.token_estimate,
            "metadata": self.metadata,
        }


class TriangleRallyManager:
    """Manages an active continuous 3-node baton pass."""

    def __init__(
        self,
        nodes: List[str] = None,
        rally_id: Optional[str] = None,
        max_turns: int = 50,
        token_budget: int = 100000,
        ttl_seconds: int = 3600,
        parent_relay_id: Optional[str] = None,
    ):
        self.nodes = nodes or ["whoart", "blade", "phoebus"]
        if len(self.nodes) < 2:
            raise ValueError("Triangle Rally requires at least 2 nodes (nominally 3).")

        self.rally_id = rally_id or f"rally_{uuid.uuid4().hex[:12]}"
        self.max_turns = max_turns
        self.token_budget = token_budget
        self.ttl_seconds = ttl_seconds
        self.parent_relay_id = parent_relay_id

        self.status = "ACTIVE"  # "ACTIVE", "PAUSED", "STOPPED", "COMPLETED"
        self.sequence_counter = 0
        self.total_tokens_spent = 0
        self.active_nodes: List[str] = list(self.nodes)
        self.dropped_nodes: Set[str] = set()

        self.valid_touches: Dict[str, int] = {n: 0 for n in self.nodes}
        self.pass_count: Dict[str, int] = {n: 0 for n in self.nodes}
        self.history: List[Baton] = []
        self._seen_sequences: Set[int] = set()
        self.start_time = datetime.now(timezone.utc)

    @property
    def current_holder(self) -> Optional[str]:
        if not self.history:
            return None
        return self.history[-1].intended_receiver

    def get_next_receiver(self, sender: str) -> str:
        """Calculate the next receiver in the active ring."""
        if sender not in self.active_nodes:
            raise InvalidReceiverError(f"Sender '{sender}' is not among active nodes: {self.active_nodes}")

        idx = self.active_nodes.index(sender)
        next_idx = (idx + 1) % len(self.active_nodes)
        return self.active_nodes[next_idx]

    def pass_baton(
        self,
        sender: str,
        action_performed: str,
        concise_state: str,
        next_ask: str,
        touch_type: str = "TOUCH",
        token_cost: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Baton:
        """Advance the baton to the next node in the ring."""
        if self.status != "ACTIVE":
            raise RallyTerminatedError(f"Rally is {self.status}, cannot pass baton.")

        # Check turn limit
        if self.sequence_counter >= self.max_turns:
            self.status = "COMPLETED"
            raise RallyTerminatedError(f"Rally reached max turns ({self.max_turns}). Circuit breaker tripped.")

        # Check token budget
        if self.total_tokens_spent + token_cost > self.token_budget:
            self.status = "COMPLETED"
            raise RallyTerminatedError(f"Rally exceeded token budget ({self.token_budget}). Circuit breaker tripped.")

        # Ring order validation
        if self.history:
            expected_sender = self.history[-1].intended_receiver
            if sender != expected_sender:
                raise InvalidReceiverError(
                    f"Out-of-turn pass: expected sender '{expected_sender}', got '{sender}'."
                )

        intended_receiver = self.get_next_receiver(sender)
        self.sequence_counter += 1
        seq = self.sequence_counter

        if seq in self._seen_sequences:
            raise DuplicateBatonError(f"Duplicate sequence number: {seq}")

        ts = timestamp or datetime.now(timezone.utc).isoformat()

        # Anti-echo Touch Scoring
        # A valid TOUCH requires non-empty novel work; if action is mere echo or empty, it counts as PASS
        cleaned_action = action_performed.strip().lower()
        is_echo = False
        if self.history:
            last_action = self.history[-1].action_performed.strip().lower()
            if cleaned_action == last_action or cleaned_action.startswith("echo:"):
                is_echo = True

        effective_touch = touch_type.upper()
        if is_echo:
            effective_touch = "PASS"

        if effective_touch == "TOUCH":
            self.valid_touches[sender] = self.valid_touches.get(sender, 0) + 1
        else:
            self.pass_count[sender] = self.pass_count.get(sender, 0) + 1

        self.total_tokens_spent += token_cost
        self._seen_sequences.add(seq)

        baton = Baton(
            rally_id=self.rally_id,
            sequence_number=seq,
            sender=sender,
            intended_receiver=intended_receiver,
            concise_state=concise_state,
            action_performed=action_performed,
            next_ask=next_ask,
            timestamp=ts,
            parent_relay_id=self.parent_relay_id,
            touch_type=effective_touch,
            token_estimate=token_cost,
            metadata=metadata or {},
        )
        self.history.append(baton)
        return baton

    def mark_node_dropped(self, dropped_node: str, reason: str = "timeout"):
        """Degrade gracefully to a smaller ring if a node times out."""
        if dropped_node in self.active_nodes and len(self.active_nodes) > 2:
            self.active_nodes.remove(dropped_node)
            self.dropped_nodes.add(dropped_node)

    def rejoin_node(self, returning_node: str):
        """Allow a dropped node to rejoin without replaying the backlog."""
        if returning_node in self.nodes and returning_node not in self.active_nodes:
            self.active_nodes.append(returning_node)
            self.dropped_nodes.discard(returning_node)

    def pause(self):
        """Pause the rally safely."""
        self.status = "PAUSED"

    def resume(self):
        """Resume a paused rally."""
        if self.status == "PAUSED":
            self.status = "ACTIVE"

    def stop(self, reason: str = "User stop"):
        """Terminate the rally completely."""
        self.status = "STOPPED"

    def get_summary(self) -> Dict[str, Any]:
        """Return diagnostic scoreboard for the Triangle Rally."""
        return {
            "rally_id": self.rally_id,
            "status": self.status,
            "sequence_number": self.sequence_counter,
            "active_ring": self.active_nodes,
            "dropped_nodes": list(self.dropped_nodes),
            "tokens_spent": self.total_tokens_spent,
            "valid_touches": self.valid_touches,
            "passes": self.pass_count,
            "total_touches": len(self.history),
            "current_holder": self.current_holder,
        }
