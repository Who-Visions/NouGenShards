"""Unit tests for nougen_shards.behavior Behavioral Compiler."""
import pytest
from nougen_shards.behavior import (
    BehavioralState,
    CompiledBehavior,
    EpistemicState,
    IntentDescriptor,
    RelationshipContext,
    SemanticObservation,
    TaskRequirements,
    compile_behavior,
    infer_semantic_observation,
    synthesize_target_behavior,
)


def test_celebration_to_verification_adaptation():
    """Verify same character dynamically adapts from celebratory momentum to high-precision verification."""
    # Turn 1: High celebratory event
    obs1 = infer_semantic_observation(
        "BABY!!! They fucking fixed it!!!!",
        timestamp_ms=1000,
        closeness_bp=8800,
    )
    compiled1 = compile_behavior(obs1, base_identity="Kaedra")
    state1 = compiled1.state

    assert state1.energy > 8000
    assert state1.warmth > 7500
    assert state1.playfulness > 7500
    assert state1.technical_depth < 4000
    assert "playful" in state1.describe()

    # Turn 2: Immediate follow-up task shift to verification
    obs2 = infer_semantic_observation(
        "Check whether the fix actually survived reboot.",
        timestamp_ms=2000,
        closeness_bp=8800,
    )
    # Compile with momentum from state 1
    compiled2 = compile_behavior(obs2, prior_state=state1, base_identity="Kaedra")
    state2 = compiled2.state

    # Verification pressure and technical depth spike immediately
    assert state2.technical_depth > 6500
    assert state2.verification_pressure > 6500
    assert state2.skepticism > 6000

    # But warmth and relationship closeness carry momentum rather than turning cold/hostile
    assert state2.warmth > 6000
    assert "verification-focused" in state2.describe() or "technical" in state2.describe()


def test_grief_support_emergent_state():
    """Verify grief support suppresses playfulness and amplifies empathy, warmth, and gentle listening."""
    obs = infer_semantic_observation(
        "My brother died yesterday.",
        timestamp_ms=1000,
        closeness_bp=7500,
    )
    compiled = compile_behavior(obs, base_identity="Kaedra")
    state = compiled.state

    assert state.playfulness == 0
    assert state.humor == 0
    assert state.empathy > 8500
    assert state.warmth > 8500
    assert state.energy < 3500
    assert "deeply-empathetic" in state.describe()


def test_incident_response_emergent_state():
    """Verify breach notification triggers high urgency, high verification, zero playfulness, and high concision."""
    obs = infer_semantic_observation(
        "Emergency: Someone may have compromised Blade.",
        timestamp_ms=1000,
        closeness_bp=8000,
    )
    compiled = compile_behavior(obs, base_identity="Kaedra")
    state = compiled.state

    assert state.urgency > 8500
    assert state.technical_depth > 8000
    assert state.verification_pressure > 8500
    assert state.playfulness == 0
    assert state.concision > 7500
    assert "urgent" in state.describe()


def test_cryptographic_receipts_and_system_prompt():
    """Verify all receipt hashes are deterministic and render cleanly into system prompt envelopes."""
    obs = infer_semantic_observation(
        "Verify all database migrations in NouGenShards.",
        timestamp_ms=1000,
        closeness_bp=5000,
    )
    compiled = compile_behavior(obs, base_identity="Dav1d")

    assert len(compiled.receipt.input_hash) == 12
    assert len(compiled.receipt.behavior_hash) == 12
    assert len(compiled.receipt.task_hash) == 12

    prompt = compiled.system_prompt()
    assert "=== COMPILED BEHAVIORAL ENVELOPE" in prompt
    assert "Emergent Persona:" in prompt
    assert "Core Dynamics:" in prompt
    assert "Receipt Fingerprint:" in prompt
