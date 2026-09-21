"""Backend protocol and the shared prompt/schema/parse helpers for model backends."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Protocol, Tuple

from ..types import (ChoiceSpec, DecisionReceipt, DecisionRequest, DecisionValue,
                     Escalation, NoulSpec, ScoreSpec)

STATE_CHARS = 4000


class DecisionBackend(Protocol):
    name: str
    version: str

    def available(self) -> bool: ...

    def decide(self, request: DecisionRequest) -> DecisionReceipt: ...


def json_schema(request: DecisionRequest) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    for q in request.questions:
        if isinstance(q, ChoiceSpec):
            props[q.key] = {"type": "string", "enum": list(q.options)}
        elif isinstance(q, ScoreSpec):
            props[q.key] = {"type": "number", "minimum": q.minimum, "maximum": q.maximum}
        elif isinstance(q, NoulSpec):
            props[q.key] = {"type": ["boolean", "null"]}
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}


def prompt(request: DecisionRequest, glosses: Optional[Dict[str, str]] = None) -> str:
    lines = [f"Decision namespace: {request.namespace} (schema {request.schema_version}).",
             "Answer every question. Reply with JSON only.", "", "Questions:"]
    for q in request.questions:
        if isinstance(q, ChoiceSpec):
            opts = ", ".join(f"{o} ({glosses[o]})" if glosses and o in glosses else o for o in q.options)
            lines.append(f"- {q.key}: pick one of [{opts}]. {q.description}")
        elif isinstance(q, ScoreSpec):
            lines.append(f"- {q.key}: number {q.minimum}..{q.maximum}. {q.description}")
        else:
            lines.append(f"- {q.key}: true, false, or null if neither. {q.description}")
    state = json.dumps(dict(request.state), default=str, ensure_ascii=False)[:STATE_CHARS]
    lines += ["", "State:", state]
    return "\n".join(lines)


def parse_values(request: DecisionRequest, text: str) -> Tuple[DecisionValue, ...]:
    """Validate a model reply against the menu. Any off-menu field voids the
    whole reply: a partial answer is not a decision."""
    try:
        obj = json.loads(text)
    except (TypeError, ValueError):
        return ()
    if not isinstance(obj, dict):
        return ()
    out = []
    for q in request.questions:
        v = obj.get(q.key, ...)
        if isinstance(q, ChoiceSpec):
            if v not in q.options:
                return ()
        elif isinstance(q, ScoreSpec):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not q.minimum <= v <= q.maximum:
                return ()
        elif v is ... or v not in (True, False, None):
            return ()
        out.append(DecisionValue(q.key, v))  # confidence 0.0: uncalibrated
    return tuple(out)


def receipt(request: DecisionRequest, backend: str, model: Optional[str], version: str,
            values: Tuple[DecisionValue, ...], ms: float, cost: float = 0.0) -> DecisionReceipt:
    from ..plane import canonical_hash
    return DecisionReceipt(
        request_hash=canonical_hash(request, version), namespace=request.namespace,
        schema_version=request.schema_version, backend=backend, model=model,
        model_version=version, values=values, escalation=Escalation.RETRY,
        latency_ms=round(ms, 1), estimated_cost_usd=cost, cache_hit=False,
        provenance=dict(request.provenance))
