"""Plane orchestration: rules get first right of refusal, then bounded
classifier backends in policy order. Every fall-through is written into the
receipt's ``attempts`` -- a fallback that hides why it fell back is a bug."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .cache import NullCache
from .policy import DecisionPolicy, can_auto_accept
from .telemetry import MemorySink
from .types import DecisionReceipt, DecisionRequest, Escalation

DEFAULT_ORDER = ("jev", "ollama", "structured_llm")


def canonical_hash(request: DecisionRequest, backend_version: str) -> str:
    payload = {
        "namespace": request.namespace,
        "schema_version": request.schema_version,
        "state": request.state,
        "questions": [asdict(q) for q in request.questions],
        "criticality": request.criticality,
        "backend_version": backend_version,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def abstain_receipt(request: DecisionRequest, attempts: List[Dict[str, Any]]) -> DecisionReceipt:
    return DecisionReceipt(
        request_hash=canonical_hash(request, "abstain"), namespace=request.namespace,
        schema_version=request.schema_version, backend="none", model=None, model_version=None,
        values=(), escalation=Escalation.ABSTAIN, latency_ms=0.0, estimated_cost_usd=0.0,
        cache_hit=False, provenance={**request.provenance, "attempts": attempts})


class DecisionPlane:
    def __init__(self, backends: Mapping[str, Any], policy: Optional[DecisionPolicy] = None,
                 receipt_sink: Any = None, cache: Any = None,
                 order: Sequence[str] = DEFAULT_ORDER):
        self.backends = dict(backends)
        self.policy = policy or DecisionPolicy()
        self.receipt_sink = receipt_sink if receipt_sink is not None else MemorySink()
        self.cache = cache if cache is not None else NullCache()
        self.order = tuple(order)

    def _route(self, request: DecisionRequest, receipt: DecisionReceipt) -> Escalation:
        if request.criticality in self.policy.criticality_force_escalation:
            return self.policy.high_criticality_route
        if receipt.values and all(can_auto_accept(v, self.policy) for v in receipt.values):
            return Escalation.ACCEPT
        return self.policy.low_confidence_route

    def decide(self, request: DecisionRequest) -> DecisionReceipt:
        attempts: List[Dict[str, Any]] = []

        rule = self.backends.get("rules")
        if rule is not None and rule.available():
            receipt = rule.decide(request)
            attempts.append({"backend": "rules", "outcome": receipt.escalation.value})
            if receipt.escalation == Escalation.ACCEPT:
                if request.criticality in self.policy.criticality_force_escalation:
                    receipt = replace(receipt, escalation=self.policy.high_criticality_route)
                receipt = replace(receipt, provenance={**receipt.provenance, "attempts": attempts})
                self.receipt_sink.write(receipt)
                return receipt

        for name in self.order:
            backend = self.backends.get(name)
            if backend is None:
                continue
            if not backend.available():
                attempts.append({"backend": name, "outcome": "unavailable"})
                continue
            key = canonical_hash(request, getattr(backend, "version", "unknown"))
            cached = self.cache.get(key)
            if cached is not None:
                attempts.append({"backend": name, "outcome": "cache_hit"})
                return replace(cached, cache_hit=True,
                               provenance={**cached.provenance, "attempts": attempts})
            t0 = time.monotonic()
            try:
                receipt = backend.decide(request)
            except Exception as exc:
                attempts.append({"backend": name, "outcome": "error",
                                 "error": type(exc).__name__,
                                 "ms": round((time.monotonic() - t0) * 1000, 1)})
                continue
            if not receipt.values:
                attempts.append({"backend": name, "outcome": "off_menu"})
                continue
            escalation = self._route(request, receipt)
            attempts.append({"backend": name, "outcome": escalation.value})
            receipt = replace(receipt, escalation=escalation,
                              provenance={**receipt.provenance, "attempts": attempts})
            self.receipt_sink.write(receipt)
            self.cache.put(key, receipt)
            return receipt

        receipt = abstain_receipt(request, attempts)
        self.receipt_sink.write(receipt)
        return receipt
