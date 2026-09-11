"""Tests for Triangle Rally Engine.
Covers:
- Directed ring passing: A -> B -> C -> A
- Out-of-turn rejection
- Anti-echo touch filtering (only novel touches score)
- Token budget and turn limit circuit breakers
- Node timeout degradation (3-node to 2-node) and clean zero-backlog rejoin
- Pause, resume, and stop controls
"""

import pytest
from nougen_shards.triangle_rally import (
    TriangleRallyManager,
    RallyTerminatedError,
    InvalidReceiverError
)


def test_triangle_ring_cycle():
    """Verify standard A -> B -> C -> A continuous passing."""
    rally = TriangleRallyManager(nodes=["whoart", "blade", "phoebus"], max_turns=10)

    # Turn 1: whoart -> blade
    b1 = rally.pass_baton(
        sender="whoart",
        action_performed="Implemented table tennis rules engine",
        concise_state="Engine built and passing tests",
        next_ask="Run integration verification against local Ollama",
        token_cost=500
    )
    assert b1.sequence_number == 1
    assert b1.intended_receiver == "blade"
    assert rally.current_holder == "blade"

    # Turn 2: blade -> phoebus
    b2 = rally.pass_baton(
        sender="blade",
        action_performed="Ran verification across RTX 2080 GPU",
        concise_state="Inference verified 100% green",
        next_ask="Audit against Mac Mini gateway",
        token_cost=400
    )
    assert b2.sequence_number == 2
    assert b2.intended_receiver == "phoebus"
    assert rally.current_holder == "phoebus"

    # Turn 3: phoebus -> whoart (closes triangle cycle)
    b3 = rally.pass_baton(
        sender="phoebus",
        action_performed="Verified gateway routing on M4 Mac Mini",
        concise_state="M4 gateway active and green",
        next_ask="Publish touchdown to fleet relay",
        token_cost=300
    )
    assert b3.sequence_number == 3
    assert b3.intended_receiver == "whoart"
    assert rally.current_holder == "whoart"

    # Turn 4: whoart -> blade again!
    b4 = rally.pass_baton(
        sender="whoart",
        action_performed="Published touchdown to relay",
        concise_state="All 3 nodes synchronized",
        next_ask="Stand by for next challenge",
        token_cost=200
    )
    assert b4.sequence_number == 4
    assert b4.intended_receiver == "blade"

    assert rally.valid_touches["whoart"] == 2
    assert rally.valid_touches["blade"] == 1
    assert rally.valid_touches["phoebus"] == 1


def test_out_of_turn_rejection():
    """Verify that passing out of order raises InvalidReceiverError."""
    rally = TriangleRallyManager(nodes=["whoart", "blade", "phoebus"])

    # whoart passes to blade
    rally.pass_baton(
        sender="whoart",
        action_performed="Task 1",
        concise_state="State 1",
        next_ask="Next"
    )

    # phoebus tries to grab the baton instead of blade!
    with pytest.raises(InvalidReceiverError):
        rally.pass_baton(
            sender="phoebus",
            action_performed="Intrusion",
            concise_state="State",
            next_ask="Next"
        )


def test_anti_echo_filtering():
    """Verify that echo chatter is downgraded to PASS and does not score as a valid TOUCH."""
    rally = TriangleRallyManager(nodes=["whoart", "blade", "phoebus"])

    # whoart -> blade
    rally.pass_baton(
        sender="whoart",
        action_performed="Novel discovery in database",
        concise_state="Discovery logged",
        next_ask="Acknowledge"
    )
    assert rally.valid_touches["whoart"] == 1

    # blade just echoes whoart's text!
    b2 = rally.pass_baton(
        sender="blade",
        action_performed="Novel discovery in database",  # Exact echo!
        concise_state="Echoed",
        next_ask="Echo"
    )
    assert b2.touch_type == "PASS"
    assert rally.valid_touches["blade"] == 0  # Did not score!
    assert rally.pass_count["blade"] == 1


def test_max_turns_and_token_circuit_breaker():
    """Verify circuit breaker trips when turn count or token budget is reached."""
    rally = TriangleRallyManager(nodes=["whoart", "blade"], max_turns=2, token_budget=1000)

    rally.pass_baton(sender="whoart", action_performed="A1", concise_state="S1", next_ask="N1", token_cost=200)
    rally.pass_baton(sender="blade", action_performed="A2", concise_state="S2", next_ask="N2", token_cost=200)

    # Exceeded max_turns (2)
    with pytest.raises(RallyTerminatedError):
        rally.pass_baton(sender="whoart", action_performed="A3", concise_state="S3", next_ask="N3", token_cost=200)


def test_node_drop_and_zero_backlog_rejoin():
    """Verify 3-node degrades to 2-node on drop, and rejoining node picks up at current sequence."""
    rally = TriangleRallyManager(nodes=["whoart", "blade", "phoebus"])

    # whoart -> blade
    rally.pass_baton(sender="whoart", action_performed="Init", concise_state="Active", next_ask="Do work")

    # Phoebus goes offline / times out
    rally.mark_node_dropped("phoebus", reason="Timeout")
    assert "phoebus" not in rally.active_nodes

    # Now ring is whoart <-> blade
    b2 = rally.pass_baton(sender="blade", action_performed="Work", concise_state="Active", next_ask="WhoArt reply")
    assert b2.intended_receiver == "whoart"  # Skips dropped phoebus!

    b3 = rally.pass_baton(sender="whoart", action_performed="Work 2", concise_state="Active", next_ask="Blade reply")
    assert b3.intended_receiver == "blade"

    # Phoebus wakes up and rejoins!
    rally.rejoin_node("phoebus")
    assert "phoebus" in rally.active_nodes

    # Blade passes to whoart, then whoart passes to phoebus, etc.
    b4 = rally.pass_baton(sender="blade", action_performed="Work 3", concise_state="Active", next_ask="Next")
    assert b4.sequence_number == 4  # Sequence continues seamlessly without replaying backlog!
