"""NouGen Decision Plane: bounded probabilistic judgment as a typed primitive.

Rich state in, a versioned finite decision space out. The model is not the
workflow -- the decision schema plus the code around it is. Law:

    exact and computable            -> deterministic code
    bounded, needs interpretation   -> this plane
    open-ended language             -> a generative reasoner

Every decision leaves a receipt that names which backends were tried, why each
fell through, and which one (if any) was accepted. Fallback never hides failure.
"""
from .types import (ChoiceSpec, DecisionKind, DecisionReceipt, DecisionRequest,
                    DecisionValue, Escalation, NoulSpec, ScoreSpec)
from .policy import DecisionPolicy, can_auto_accept, margin, normalized_entropy
from .plane import DecisionPlane, canonical_hash

__all__ = [
    "ChoiceSpec", "DecisionKind", "DecisionReceipt", "DecisionRequest", "DecisionValue",
    "Escalation", "NoulSpec", "ScoreSpec", "DecisionPolicy", "can_auto_accept", "margin",
    "normalized_entropy", "DecisionPlane", "canonical_hash",
]
