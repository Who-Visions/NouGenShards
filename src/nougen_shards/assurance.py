"""Evidence assurance routed through Iris.

This layer labels claims for operator review. It never promotes, deletes, or
otherwise mutates shards from an automated verdict.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from .brain_scan.redaction import redact_content
from .structured import parse_json_content


STATUSES = frozenset({"VERIFIED", "CONTRADICTED", "UNCERTAIN", "UNVERIFIED"})


def _fallback(claim: str, caveat: str) -> dict:
    return {
        "claim": redact_content(claim),
        "status": "UNVERIFIED",
        "confidence": 0.0,
        "rationale": "Iris did not return a valid assurance verdict.",
        "evidence_used": [],
        "caveats": [redact_content(caveat)],
        "verifier": "Iris",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "operator_gate_required": True,
    }


def assess_claim(
    claim: str,
    evidence: Optional[Iterable[str]] = None,
    iris_runner: Optional[Callable[[str], str]] = None,
) -> dict:
    """Ask Iris to label a claim, failing closed to ``UNVERIFIED``.

    Inputs and outputs are secret-pattern redacted. Every result remains behind
    an operator gate; this function performs no shard mutation.
    """
    safe_claim = redact_content((claim or "").strip())
    safe_evidence = [redact_content(str(item)) for item in (evidence or [])]
    if not safe_claim:
        return _fallback("", "No claim was supplied.")

    if iris_runner is None:
        from .agents import run_agent

        def iris_runner(prompt: str) -> str:
            return run_agent("Iris", prompt)

    evidence_block = "\n".join(f"- {item}" for item in safe_evidence) or "- none supplied"
    prompt = redact_content(
        "Assess this claim against only the supplied evidence and return one JSON object.\n"
        "Allowed status values: VERIFIED, CONTRADICTED, UNCERTAIN, UNVERIFIED.\n"
        "Required fields: status (string), confidence (number 0..1), rationale "
        "(string), evidence_used (array of strings), caveats (array of strings).\n"
        "Do not browse or imply external verification unless a supplied evidence item "
        "contains the result. Never recommend automatic promotion or deletion.\n\n"
        f"CLAIM:\n{safe_claim}\n\nEVIDENCE:\n{evidence_block}"
    )

    try:
        raw = redact_content(iris_runner(prompt))
        parsed = parse_json_content(raw)
        status = str(parsed.get("status", "")).upper()
        confidence = parsed.get("confidence")
        rationale = parsed.get("rationale")
        evidence_used = parsed.get("evidence_used")
        caveats = parsed.get("caveats")
        if status not in STATUSES:
            raise ValueError(f"invalid status: {status or '<empty>'}")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        if not isinstance(rationale, str):
            raise ValueError("rationale must be a string")
        if not isinstance(evidence_used, list) or not all(isinstance(v, str) for v in evidence_used):
            raise ValueError("evidence_used must be an array of strings")
        if not isinstance(caveats, list) or not all(isinstance(v, str) for v in caveats):
            raise ValueError("caveats must be an array of strings")
    except Exception as exc:
        return _fallback(safe_claim, str(exc))

    return {
        "claim": safe_claim,
        "status": status,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "rationale": redact_content(rationale),
        "evidence_used": [redact_content(v) for v in evidence_used],
        "caveats": [redact_content(v) for v in caveats],
        "verifier": "Iris",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "operator_gate_required": True,
    }
