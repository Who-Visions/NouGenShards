"""Unit tests for the Universal Deterministic Information-Gain Primitive."""
import pytest
from nougen_shards.information_gain import InformationGainState, tokenize


def test_tokenize_deterministic():
    text = "Hello World! This is an arXiv:2609.34785 test-case."
    tokens = tokenize(text)
    assert "hello" in tokens
    assert "world" in tokens
    assert "arxiv:2609.34785" in tokens or "2609.34785" in tokens


def test_exact_duplicate_yields_zero_gain():
    state = InformationGainState()
    base_text = "NVIDIA RTX 2080 Super Max-Q Stadium GPU liveness nominal"
    state.update(base_text)
    
    env = state.evaluate(base_text)
    assert env.raw_observation["is_exact_seen"] is True
    assert env.inferred_relationship["novelty_score"] == 0.0
    assert env.inferred_relationship["conditional_information_gain_bits"] == 0.0
    assert env.action_recommendation["deduplication_verdict"] == "duplicate"
    assert env.action_recommendation["action_allowed"] is False
    assert env.action_recommendation["relay_urgency"] == "routine"


def test_repeated_information_approaches_zero_marginal_gain():
    state = InformationGainState()
    corpus = [
        "quantum computing lattice cryptography fault tolerant qubit",
        "quantum lattice cryptography qubit stabilization",
        "fault tolerant quantum cryptography error correction",
    ]
    for doc in corpus:
        state.update(doc)
    
    repeated_event = "quantum computing qubit fault tolerant lattice"
    novel_event = "neuro-symbolic synthetic biology ribosomal genome transcription"
    
    rep_env = state.evaluate(repeated_event)
    nov_env = state.evaluate(novel_event)
    
    # Repeated information must yield low gain
    assert rep_env.inferred_relationship["novelty_score"] < 0.35
    # Novel information must yield high gain
    assert nov_env.inferred_relationship["novelty_score"] > rep_env.inferred_relationship["novelty_score"]
    assert nov_env.inferred_relationship["novelty_score"] >= 0.70
    assert nov_env.action_recommendation["relay_urgency"] in ("elevated", "beacon")


def test_provenance_strict_separation():
    state = InformationGainState()
    state.update("Initial baseline state of the memory cluster")
    env = state.evaluate("New incoming observation")
    d = env.to_dict()
    
    # 3 distinct envelopes
    assert "raw_observation" in d
    assert "inferred_relationship" in d
    assert "action_recommendation" in d
    
    # Verify strict boundary flags
    assert d["raw_observation"]["provenance_layer"] == "raw_observation"
    assert d["inferred_relationship"]["is_inferred"] is True
    assert d["inferred_relationship"]["provenance_layer"] == "inferred_relationship"
    assert d["action_recommendation"]["is_recommendation"] is True
    assert d["action_recommendation"]["provenance_layer"] == "action_recommendation"
    
    # Raw observation must never contain inferred scores
    assert "novelty_score" not in d["raw_observation"]
    assert "deduplication_verdict" not in d["raw_observation"]


def test_six_vector_projections():
    state = InformationGainState()
    state.update("Alpha Beta Gamma")
    
    # Completely novel event
    env = state.evaluate("Zeta Theta Iota Kappa Lambda", confidence=0.85)
    inferred = env.inferred_relationship
    action = env.action_recommendation
    
    # 1. Novelty score in [0, 1]
    assert 0.0 <= inferred["novelty_score"] <= 1.0
    # 2. Deduplication verdict
    assert action["deduplication_verdict"] == "novel"
    # 3. Retrieval boost >= 1.0
    assert inferred["retrieval_boost"] > 1.2
    # 4. Causal edge weight factored by confidence
    assert inferred["edge_weight"] > 0.5
    # 5. Relay urgency
    assert action["relay_urgency"] in ("elevated", "beacon")
    # 6. Action gating
    assert action["action_allowed"] is True
