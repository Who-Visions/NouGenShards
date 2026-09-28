"""
Mathematical Algorithm & Vector Space Subsystem for Persona Resolution.

Implements formal mathematical metrics for dialogue modeling, Big Five (OCEAN) vectorization,
Shannon lexical entropy, syntactic velocity, and Bayesian trait prior updates.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class OCEANVector:
    """Big Five (OCEAN) personality trait vector in [0.0, 1.0]^5 space."""
    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5

    def to_dict(self) -> Dict[str, float]:
        return {
            "O": round(self.openness, 4),
            "C": round(self.conscientiousness, 4),
            "E": round(self.extraversion, 4),
            "A": round(self.agreeableness, 4),
            "N": round(self.neuroticism, 4)
        }

    def magnitude(self) -> float:
        return math.sqrt(
            self.openness**2 +
            self.conscientiousness**2 +
            self.extraversion**2 +
            self.agreeableness**2 +
            self.neuroticism**2
        )


@dataclass
class MannerismMetrics:
    """Mathematical metrics for dialogue mannerisms and lexical dynamics."""
    shannon_entropy: float = 0.0      # H(X) = -sum p(x) log2 p(x)
    imperative_velocity: float = 0.0  # Ratio of imperative action directives
    correction_gradient: float = 0.0  # Restatement/correction frequency gradient
    syntactic_cohesion: float = 0.0  # 1 - (stddev(words) / mean(words))
    ocean_vector: OCEANVector = field(default_factory=OCEANVector)


def compute_shannon_entropy(words: List[str]) -> float:
    """Calculates Shannon Lexical Entropy H(X) = -sum P(x) log2 P(x)."""
    if not words:
        return 0.0
    total = len(words)
    counts: Dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return round(entropy, 4)


def compute_syntactic_cohesion(word_lengths: List[int]) -> float:
    """Computes stylistic length cohesion S_cohesion = 1 - (stdev / (mean + eps))."""
    if not word_lengths or len(word_lengths) < 2:
        return 1.0
    mean_val = statistics.mean(word_lengths)
    if mean_val == 0:
        return 1.0
    stdev_val = statistics.stdev(word_lengths)
    cohesion = max(0.0, 1.0 - (stdev_val / (mean_val + 1e-6)))
    return round(cohesion, 4)


def compute_ocean_vector(
    shannon_entropy: float,
    imperative_ratio: float,
    correction_ratio: float,
    median_words: float,
    lexicon_hits: int
) -> OCEANVector:
    """
    Computes deterministic OCEAN vector using non-linear sigmoid projections:
    - Openness: Driven by lexical entropy H(X) and lexicon diversity
    - Conscientiousness: Proportional to low noise & structured imperative clarity
    - Extraversion: Proportional to log(1 + median_words) and lexicon hits
    - Agreeableness: Inverse to correction gradient (1 - correction_ratio)
    - Neuroticism: Proportional to correction ratio and lexical turbulence
    """
    def sigmoid(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-x))

    # Normalized inputs
    norm_entropy = min(1.0, shannon_entropy / 8.0)
    norm_length = min(1.0, math.log1p(median_words) / 5.0)
    norm_hits = min(1.0, lexicon_hits / 10.0)

    # Sigmoid trait activations centered around baseline zero-mean weights
    o = sigmoid(3.0 * norm_entropy + 2.0 * norm_hits - 2.5)
    c = sigmoid(3.0 * imperative_ratio - 2.0 * correction_ratio + 0.5)
    e = sigmoid(3.0 * norm_length + 2.0 * norm_hits - 2.0)
    a = sigmoid(3.0 * (1.0 - correction_ratio) - 1.5)
    n = sigmoid(4.0 * correction_ratio - 1.5)

    return OCEANVector(
        openness=round(o, 4),
        conscientiousness=round(c, 4),
        extraversion=round(e, 4),
        agreeableness=round(a, 4),
        neuroticism=round(n, 4)
    )


class BayesianTraitPrior:
    """
    Bayesian update framework for archetype probabilities:
    P(Archetype | Evidence) = P(Evidence | Archetype) * P(Archetype) / P(Evidence)
    """
    def __init__(self, archetypes: List[str]):
        self.archetypes = archetypes
        n = len(archetypes) or 1
        # Uniform prior initialization
        self.priors: Dict[str, float] = {a: 1.0 / n for a in archetypes}

    def update(self, likelihoods: Dict[str, float]) -> Dict[str, float]:
        """Performs Bayesian update step and normalizes posterior probability vector."""
        unnormalized = {}
        total = 0.0
        for arch in self.archetypes:
            prior = self.priors.get(arch, 0.0)
            lh = likelihoods.get(arch, 0.01)
            post = prior * lh
            unnormalized[arch] = post
            total += post

        if total > 0:
            self.priors = {k: round(v / total, 4) for k, v in unnormalized.items()}
        return self.priors
