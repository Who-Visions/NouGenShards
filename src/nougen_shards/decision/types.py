"""Typed contract for the Decision Plane. Frozen, hashable, JSON-serialisable."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple, Union


class DecisionKind(str, Enum):
    CHOICE = "choice"
    SCORE = "score"
    NOUL = "noul"  # nullable yes/no: the answer may legitimately be "neither"


class Escalation(str, Enum):
    ACCEPT = "accept"
    RETRY = "retry"
    LLM = "llm"
    HUMAN = "human"
    RULE = "rule"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class ChoiceSpec:
    key: str
    options: Tuple[str, ...]
    description: str = ""
    kind: DecisionKind = DecisionKind.CHOICE

    def __post_init__(self) -> None:
        if not self.options or len(set(self.options)) != len(self.options):
            raise ValueError(f"choice {self.key!r}: options must be non-empty and unique")


@dataclass(frozen=True)
class ScoreSpec:
    key: str
    minimum: float
    maximum: float
    description: str = ""
    kind: DecisionKind = DecisionKind.SCORE

    def __post_init__(self) -> None:
        if not self.minimum < self.maximum:
            raise ValueError(f"score {self.key!r}: minimum must be < maximum")


@dataclass(frozen=True)
class NoulSpec:
    key: str
    description: str = ""
    kind: DecisionKind = DecisionKind.NOUL


QuestionSpec = Union[ChoiceSpec, ScoreSpec, NoulSpec]


@dataclass(frozen=True)
class DecisionRequest:
    namespace: str
    schema_version: str
    state: Mapping[str, Any]
    questions: Tuple[QuestionSpec, ...]
    criticality: str = "normal"
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        keys = [q.key for q in self.questions]
        if not keys or len(set(keys)) != len(keys):
            raise ValueError("request questions must be non-empty with unique keys")


@dataclass(frozen=True)
class DecisionValue:
    key: str
    value: Any
    # 0.0 means "no calibrated confidence", NOT "confident it is wrong".
    # Constrained decoding yields a valid label, never a probability.
    confidence: float = 0.0
    probabilities: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionReceipt:
    request_hash: str
    namespace: str
    schema_version: str
    backend: str
    model: Optional[str]
    model_version: Optional[str]
    values: Tuple[DecisionValue, ...]
    escalation: Escalation
    latency_ms: float
    estimated_cost_usd: float
    cache_hit: bool
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def value(self, key: str) -> Any:
        for v in self.values:
            if v.key == key:
                return v.value
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["escalation"] = self.escalation.value
        return d
