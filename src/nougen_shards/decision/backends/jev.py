"""Jev (Typesafe) arm -- placeholder, deliberately unavailable.

The fleet has no JEV key and has not verified Jev's API shape, so this arm
reports unavailable rather than guess an endpoint. When a key exists, implement
``decide`` against the documented API (it returns per-option probabilities,
which is the one thing the local arms cannot give the policy gate).
"""
from __future__ import annotations

from ..types import DecisionReceipt, DecisionRequest


class JevBackend:
    name = "jev"
    version = "jev:unimplemented"

    def available(self) -> bool:
        return False

    def decide(self, request: DecisionRequest) -> DecisionReceipt:
        raise NotImplementedError("Jev backend not implemented: no key and no verified API contract")
