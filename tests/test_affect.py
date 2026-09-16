"""Unit tests for nougen_shards.affect deterministic emotion + persona engine."""
import pytest
from nougen_shards.affect import (
    SCALE,
    AffectVector,
    CharacterMind,
    EmotionState,
    Observation,
    PersonaBlend,
    classify_emotion,
    decay_toward_baseline,
    expression_from_emotion,
    normalize_persona_weights,
    resolve_character,
    update_emotion,
)


def test_pure_determinism_same_inputs_same_fingerprint():
    """Verify that identical inputs produce 100% identical vectors and fingerprints."""
    kaedra_personas = {
        "charming": 35,
        "witty": 25,
        "genius": 20,
        "detective": 10,
        "streetwise": 10,
    }

    state1 = EmotionState(timestamp_ms=1_000_000)
    obs1 = Observation(
        timestamp_ms=1_010_000,
        text="BABY!!! This shit fucking worked!!! I love this!",
    )
    res1 = resolve_character(state1, obs1, kaedra_personas)

    state2 = EmotionState(timestamp_ms=1_000_000)
    obs2 = Observation(
        timestamp_ms=1_010_000,
        text="BABY!!! This shit fucking worked!!! I love this!",
    )
    res2 = resolve_character(state2, obs2, kaedra_personas)

    assert res1.emotion.label == res2.emotion.label
    assert res1.emotion.intensity == res2.emotion.intensity
    assert res1.emotion.vector == res2.emotion.vector
    assert res1.expression == res2.expression
    assert res1.fingerprint == res2.fingerprint
    assert len(res1.fingerprint) == 16


def test_emotional_inertia_and_hysteresis():
    """Verify that a single mildly anxious prompt does not flip an ecstatic state directly to terrified."""
    initial_state = EmotionState(timestamp_ms=1_000_000)

    # 1. First trigger strong positive state
    obs1 = Observation(
        timestamp_ms=1_010_000,
        text="AMAZING victory! Everything is completely perfect and winning!",
    )
    state_ecstatic = update_emotion(initial_state, obs1)
    assert state_ecstatic.vector.joy > 3000
    assert state_ecstatic.vector.valence > 4000

    # 2. Introduce mild doubt
    obs2 = Observation(
        timestamp_ms=1_020_000,
        text="Wait. Something is wrong. Why is Blade reporting offline again?",
    )
    state_after_doubt = update_emotion(state_ecstatic, obs2)

    # It should retain inertia and not instantly become 'terrified' or 'enraged'
    assert state_after_doubt.label in ("excited", "joyful", "hopeful", "curious", "ecstatic", "calm", "content")
    assert state_after_doubt.vector.curiosity > 0
    assert state_after_doubt.vector.fear == 0  # No panic words in mild doubt

    # 3. Sustained confirmed failure moves it progressively
    obs3 = Observation(
        timestamp_ms=1_030_000,
        text="No. It is actually offline and we lost the process. Danger and panic!",
        event_fear=4500,
        event_uncertainty=5000,
    )
    state_after_crisis = update_emotion(state_after_doubt, obs3)
    assert state_after_crisis.vector.fear > state_after_doubt.vector.fear
    assert state_after_crisis.vector.valence < state_after_doubt.vector.valence


def test_coexistence_of_contradictory_emotions():
    """Verify affection and anger can coexist in the same affect vector."""
    state = EmotionState(timestamp_ms=1_000_000)
    obs = Observation(
        timestamp_ms=1_010_000,
        text="I love you sweetheart, but you are being a complete idiot and I am so pissed right now!",
    )
    updated = update_emotion(state, obs)
    assert updated.vector.affection > 0
    assert updated.vector.anger > 0


def test_persona_weights_normalization():
    """Verify weights normalize accurately to 10,000 basis points."""
    raw = {"charming": 35, "witty": 25, "genius": 20, "detective": 10, "streetwise": 10}
    blend = normalize_persona_weights(raw)
    total_bp = sum(p.weight for p in blend.personas)
    assert 9990 <= total_bp <= 10000
    assert len(blend.personas) == 5


def test_character_mind_and_receipt():
    """Verify CharacterMind perceptions, stress, mood, and mathematical receipts."""
    mind = CharacterMind(
        base_identity="Kaedra",
        persona_weights={"charming": 4000, "genius": 3000, "witty": 3000},
    )

    obs = Observation(
        timestamp_ms=1_005_000,
        text="Brilliant discovery in the shard index! We solved the puzzle!",
    )
    next_mind = mind.perceive(obs)

    receipt = next_mind.format_receipt()
    assert "=== AFFECT TRANSITION RECEIPT ===" in receipt
    assert "Transition Alpha:" in receipt
    assert "Resolved Valence / Arousal / Dominance:" in receipt
    assert "State Fingerprint:" in receipt

    char_state = next_mind.current_character_state()
    prompt = char_state.system_prompt("Kaedra")
    assert "Base Identity: Kaedra." in prompt
    assert "Personality Composition:" in prompt
    assert "Active Emotion:" in prompt
    assert "Expressive Constraints:" in prompt


def test_decay_toward_baseline():
    """Verify emotional states decay gently over elapsed time towards calm baseline."""
    high_anger = EmotionState(
        vector=AffectVector(valence=-8000, arousal=8000, dominance=7000, anger=8000),
        label="furious",
        intensity=8000,
        timestamp_ms=1_000_000,
    )

    # 5 minutes later without further stimuli
    decayed = decay_toward_baseline(high_anger, timestamp_ms=1_300_000)
    assert decayed.vector.anger < high_anger.vector.anger
    assert abs(decayed.vector.valence) < abs(high_anger.vector.valence)
