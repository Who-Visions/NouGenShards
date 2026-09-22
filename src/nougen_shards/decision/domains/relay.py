"""Relay triage as the Decision Plane's first proving ground.

Rules (``relay_triage``, #465) decide first. Two cases are deliberately NOT
decisive and fall through to the classifiers:

  * UNKNOWN -- no rule matched.
  * a CLOSED verdict on a leg whose record shows failed attempts, or a
    ``dead_letter`` leg -- measured 2026-09-21: 20260920T141749Z reads
    ``status: complete`` with ``retry_count: 2`` and a non-zero-exit failure
    list. A terminal status is a claim, not evidence; it cannot close a leg
    on its own.

Shadow-first: ``triage_leg`` returns the receipt; callers decide delivery.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from ...relay_triage import LABELS, SURFACE, classify
from ...relay_triage_model import _GLOSS
from ..backends import JevBackend, OllamaBackend, RulesBackend, StructuredLLMBackend
from ..plane import DecisionPlane
from ..types import ChoiceSpec, DecisionRequest, DecisionValue

NAMESPACE = "relay.triage"
SCHEMA_VERSION = "1"
QUESTION = ChoiceSpec("label", tuple(LABELS), "How should this node treat the relay leg?")
STATE_KEYS = ("id", "machine", "agent", "status", "state", "goal", "body", "message",
              "created_utc", "retry_count", "failures")


def request_for(leg: Mapping[str, Any], me: Optional[str] = None) -> DecisionRequest:
    state = {k: leg[k] for k in STATE_KEYS if k in leg}
    state["me"] = me or ""
    return DecisionRequest(NAMESPACE, SCHEMA_VERSION, state, (QUESTION,),
                           provenance={"leg_id": leg.get("id")})


def _rule(request: DecisionRequest) -> Tuple[Tuple[DecisionValue, ...], bool, str]:
    leg: Dict[str, Any] = dict(request.state)
    v = classify(leg, leg.get("me") or None)
    status = str(leg.get("status") or leg.get("state") or "").strip().lower()
    failed = str(leg.get("failures") or "").strip() not in ("", "[]", "None")
    unproven_close = v.label == "CLOSED" and (failed or status == "dead_letter")
    decisive = v.label != "UNKNOWN" and not unproven_close and status != "dead_letter"
    return (DecisionValue("label", v.label, 1.0 if decisive else 0.0),), decisive, v.rule


def default_plane(**kw: Any) -> DecisionPlane:
    glosses = dict(_GLOSS)
    return DecisionPlane({
        "rules": RulesBackend(_rule, version="relay_triage-465"),
        "jev": JevBackend(),
        "ollama": OllamaBackend(glosses=glosses),
        "structured_llm": StructuredLLMBackend(glosses=glosses),
    }, **kw)


def triage_leg(leg: Mapping[str, Any], me: Optional[str] = None,
               plane: Optional[DecisionPlane] = None):
    return (plane or default_plane()).decide(request_for(leg, me))


def surfaces(receipt) -> bool:
    """Surface when the accepted label says so, or whenever nothing was accepted:
    an unresolved decision goes to a human, never to silence."""
    label = receipt.value("label")
    if receipt.escalation.value != "accept":
        return True
    return label in SURFACE
