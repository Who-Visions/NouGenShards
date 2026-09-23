"""mix.diagnostic (NouGenMix, WhoArt slice) wrapped in Decision Plane types.

NouGenMix owns the contract: plain dicts from
``fl_studio_mcp.theory.mix_decisions`` (``request()``, ``rules_decide()``),
namespace ``mix.diagnostic``, schema 1. This module converts those dicts to
and from ``nougen_shards.decision`` types WITHOUT changing them, and never
imports NouGenMix -- callers inject ``rules_decide`` so neither repo depends
on the other's install.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Dict, Mapping, Tuple

from ..backends import RulesBackend
from ..types import (ChoiceSpec, DecisionReceipt, DecisionRequest, DecisionValue,
                     NoulSpec, QuestionSpec, ScoreSpec)

NAMESPACE = "mix.diagnostic"
SCHEMA_VERSION = "1"

RulesDecide = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _question(q: Mapping[str, Any]) -> QuestionSpec:
    kind = q.get("kind")
    if kind == "choice":
        return ChoiceSpec(q["key"], tuple(q["options"]), q.get("description", ""))
    if kind == "score":
        return ScoreSpec(q["key"], float(q["minimum"]), float(q["maximum"]), q.get("description", ""))
    if kind == "noul":
        return NoulSpec(q["key"], q.get("description", ""))
    raise ValueError(f"unknown question kind {kind!r}")


def from_dict(req: Mapping[str, Any]) -> DecisionRequest:
    """NouGenMix ``request()`` dict -> DecisionRequest. Refuses a foreign
    namespace or schema rather than guessing across versions."""
    if req.get("namespace") != NAMESPACE or str(req.get("schema_version")) != SCHEMA_VERSION:
        raise ValueError(f"not {NAMESPACE} v{SCHEMA_VERSION}: "
                         f"{req.get('namespace')} v{req.get('schema_version')}")
    return DecisionRequest(NAMESPACE, SCHEMA_VERSION, dict(req.get("state") or {}),
                           tuple(_question(q) for q in req["questions"]),
                           criticality=req.get("criticality", "normal"),
                           provenance=dict(req.get("provenance") or {}))


def _values(result: Mapping[str, Any]) -> Tuple[DecisionValue, ...]:
    return tuple(DecisionValue(v["key"], v.get("value"), float(v.get("confidence") or 0.0),
                               dict(v.get("probabilities") or {}))
                 for v in result.get("values") or ())


def rules_backend(rules_decide: RulesDecide, version: str = "nougenmix-rules-1") -> RulesBackend:
    """Wrap NouGenMix's deterministic arm. Its own escalation decides: only
    ``accept`` is decisive; ``abstain`` falls through to the classifiers."""
    def fn(request: DecisionRequest):
        result = rules_decide(dict(request.state))
        reasons = result.get("reasons") or []
        return (_values(result), result.get("escalation") == "accept",
                "; ".join(map(str, reasons)) or "nougenmix-rules")
    return RulesBackend(fn, version=version)


def to_dict(receipt: DecisionReceipt) -> Dict[str, Any]:
    """Receipt -> the dict shape ``rules_decide`` returns, plus receipt fields."""
    d = receipt.to_dict()
    d["values"] = [asdict(v) for v in receipt.values]
    return d
