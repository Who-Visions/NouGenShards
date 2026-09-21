"""Deterministic arm. A domain supplies ``fn(request) -> (values, decisive, rule_id)``.
Decisive rule answers are ACCEPTed at confidence 1.0; indecisive ones return
RULE so the plane falls through to the classifiers."""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Tuple

from ..types import DecisionRequest, DecisionReceipt, DecisionValue, Escalation
from .base import receipt

RuleFn = Callable[[DecisionRequest], Tuple[Tuple[DecisionValue, ...], bool, str]]


class RulesBackend:
    name = "rules"

    def __init__(self, fn: RuleFn, version: str = "rules-1"):
        self.fn = fn
        self.version = version

    def available(self) -> bool:
        return True

    def decide(self, request: DecisionRequest) -> DecisionReceipt:
        t0 = time.monotonic()
        values, decisive, rule_id = self.fn(request)
        r = receipt(request, "rules", None, self.version, values, (time.monotonic() - t0) * 1000)
        return replace(r, escalation=Escalation.ACCEPT if decisive else Escalation.RULE,
                       provenance={**r.provenance, "rule": rule_id})
