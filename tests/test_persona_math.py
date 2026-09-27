"""
Tests for persona_math module.
"""
from nougen_shards.persona_math import (
    compute_shannon_entropy,
    compute_syntactic_cohesion,
    compute_ocean_vector,
    BayesianTraitPrior,
    OCEANVector
)

def test_shannon_entropy():
    words = ["make", "build", "make", "run", "ship"]
    entropy = compute_shannon_entropy(words)
    assert isinstance(entropy, float)
    assert entropy > 0.0

def test_syntactic_cohesion():
    lengths = [4, 5, 4, 6, 5]
    cohesion = compute_syntactic_cohesion(lengths)
    assert 0.0 <= cohesion <= 1.0

def test_ocean_vector():
    vec = compute_ocean_vector(
        shannon_entropy=3.5,
        imperative_ratio=0.8,
        correction_ratio=0.1,
        median_words=12.0,
        lexicon_hits=4
    )
    assert isinstance(vec, OCEANVector)
    d = vec.to_dict()
    assert all(k in d for k in ["O", "C", "E", "A", "N"])
    assert all(0.0 <= v <= 1.0 for v in d.values())

def test_bayesian_prior():
    archetypes = ["fleet-operator", "canon-keeper", "stream-creator"]
    btp = BayesianTraitPrior(archetypes)
    updated = btp.update({"fleet-operator": 0.8, "canon-keeper": 0.1, "stream-creator": 0.1})
    assert updated["fleet-operator"] > updated["canon-keeper"]
    assert sum(updated.values()) == 1.0
