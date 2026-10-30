"""Truth Anchor Shard Gate (Layer 4 Deterministic Enforcement).

Enforces the Truth Anchor & Epistemic Invariant (AUTHORITY.md Directive & AGENTS.md Rule 0.11):
Prevents agents or workflows from saving shards claiming task completion, bug fixes,
or successful execution without attached, independently verifiable Scoreboard evidence
(command executed, exit_code 0, and physical non-empty stdout / output hash).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


SUCCESS_EVENT_TYPES = {
    "completion",
    "resolution",
    "task_completion",
    "task_complete",
    "fix",
    "bugfix",
    "success",
    "verified",
    "passed",
    "milestone_complete",
}

SUCCESS_TAGS = {
    "completed",
    "resolved",
    "fix",
    "bugfix",
    "passed",
    "verified",
    "solution",
    "#completed",
    "#resolved",
    "#fix",
    "#bugfix",
    "#passed",
    "#verified",
    "#solution",
}

SUCCESS_PATTERNS = [
    re.compile(r"\b(?:task|issue|bug|problem|ticket)\s+(?:is\s+)?(?:fixed|resolved|completed|closed|solved)\b", re.I),
    re.compile(r"\b(?:fix|solution|resolution|patch)\s+(?:landed|deployed|verified|complete|successful)\b", re.I),
    re.compile(r"\ball\s+tests?\s+(?:pass|passed|passing)\b", re.I),
    re.compile(r"\bverification\s+(?:passed|successful|complete)\b", re.I),
    re.compile(r"^\[(?:FIX|RESOLVED|COMPLETED|SUCCESS|VERIFIED)\]", re.I),
]


class ShardEvidenceRejectionError(ValueError):
    """Raised when a shard asserts success without verified scoreboard execution evidence."""


@dataclass(frozen=True)
class ShardGateDecision:
    """Decision emitted by the ShardGate."""
    allowed: bool
    reason: str
    is_success_claim: bool
    evidence_found: bool
    evidence_payload: Optional[Dict[str, Any]] = None


class ShardGate:
    """Evaluates whether a shard's claims are backed by required evidence."""

    @classmethod
    def is_success_claim(
        cls,
        title: str,
        content: str,
        event_type: str = "",
        tags: Optional[Sequence[str]] = None,
    ) -> Tuple[bool, str]:
        """Detect if the shard asserts task completion, resolution, or success."""
        norm_event = str(event_type or "").strip().lower()
        if norm_event in SUCCESS_EVENT_TYPES:
            return True, f"event_type '{norm_event}' indicates completion"

        if tags:
            for tag in tags:
                norm_tag = str(tag or "").strip().lower()
                if norm_tag in SUCCESS_TAGS:
                    return True, f"tag '{norm_tag}' indicates completion"

        norm_title = str(title or "").strip()
        for pattern in SUCCESS_PATTERNS:
            if pattern.search(norm_title):
                return True, f"title matches success pattern: {pattern.pattern}"

        norm_content = str(content or "")[:2000]
        for pattern in SUCCESS_PATTERNS:
            if pattern.search(norm_content):
                return True, f"content matches success pattern: {pattern.pattern}"

        return False, "no success claim detected"

    @classmethod
    def extract_scoreboard_evidence(
        cls,
        content: str,
        evidence: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Validate or parse execution evidence from mapping or content body."""
        # 1. Direct structured evidence dictionary
        if evidence and isinstance(evidence, (dict, Mapping)):
            payload = dict(evidence)
            # Support either flat keys or nested test_evidence
            if "test_evidence" in payload and isinstance(payload["test_evidence"], dict):
                inner = payload["test_evidence"]
                command = inner.get("command") or inner.get("runner")
                exit_code = inner.get("exit_code")
                stdout = inner.get("stdout") or inner.get("output") or inner.get("stdout_hash")
            else:
                command = payload.get("command") or payload.get("runner")
                exit_code = payload.get("exit_code")
                stdout = payload.get("stdout") or payload.get("output") or payload.get("stdout_hash") or payload.get("stdout_digest")

            if not command or not str(command).strip():
                return False, None, "evidence missing non-empty 'command' or 'runner'"
            if exit_code is None:
                return False, None, "evidence missing 'exit_code'"
            try:
                if int(exit_code) != 0:
                    return False, None, f"evidence reports failing exit_code: {exit_code}"
            except (ValueError, TypeError):
                return False, None, f"evidence has invalid exit_code format: {exit_code}"

            if not stdout or not str(stdout).strip():
                return False, None, "evidence missing command stdout/output proof"

            return True, {
                "command": str(command).strip(),
                "exit_code": int(exit_code),
                "output": str(stdout).strip()[:1000],
            }, "valid structured evidence mapping"

        # 2. Parse scoreboard code blocks in content: ```scoreboard ... ``` or ```evidence ... ```
        block_match = re.search(
            r"```(?:scoreboard|evidence|poe|test-evidence)\s*\n(.*?)```",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if block_match:
            block_text = block_match.group(1).strip()
            # Try JSON first
            if block_text.startswith("{") and block_text.endswith("}"):
                try:
                    data = json.loads(block_text)
                    return cls.extract_scoreboard_evidence("", evidence=data)
                except Exception:
                    pass

            # Parse key-value lines
            lines = [l.strip() for l in block_text.splitlines() if l.strip()]
            parsed: Dict[str, Any] = {}
            for line in lines:
                if ":" in line:
                    k, v = line.split(":", 1)
                    parsed[k.strip().lower().replace(" ", "_")] = v.strip()

            cmd = parsed.get("command") or parsed.get("runner")
            ec = parsed.get("exit_code")
            out = parsed.get("output") or parsed.get("stdout") or parsed.get("scoreboard")
            if cmd and ec is not None:
                return cls.extract_scoreboard_evidence("", evidence={
                    "command": cmd,
                    "exit_code": ec,
                    "stdout": out or "verified via scoreboard block"
                })

        return False, None, "no valid scoreboard evidence found in payload or markdown block"

    @classmethod
    def evaluate_shard(
        cls,
        title: str,
        content: str,
        event_type: str = "",
        tags: Optional[Sequence[str]] = None,
        evidence: Optional[Mapping[str, Any]] = None,
        raise_on_reject: bool = False,
    ) -> ShardGateDecision:
        """Evaluate shard against Truth Anchor requirements."""
        is_claim, claim_reason = cls.is_success_claim(title, content, event_type, tags)
        if not is_claim:
            return ShardGateDecision(
                allowed=True,
                reason="Advisory: No task success or resolution claim detected.",
                is_success_claim=False,
                evidence_found=False,
            )

        valid_evidence, payload, ev_reason = cls.extract_scoreboard_evidence(content, evidence)
        if valid_evidence:
            return ShardGateDecision(
                allowed=True,
                reason=f"Allowed: Success claim verified by Scoreboard proof ({ev_reason}).",
                is_success_claim=True,
                evidence_found=True,
                evidence_payload=payload,
            )

        rejection_reason = (
            f"REJECTED by Truth Anchor Shard Gate: Shard asserts task completion ({claim_reason}) "
            f"without verifiable Scoreboard evidence ({ev_reason}). Rule 0.11 forbids unverified success claims."
        )
        if raise_on_reject:
            raise ShardEvidenceRejectionError(rejection_reason)

        return ShardGateDecision(
            allowed=False,
            reason=rejection_reason,
            is_success_claim=True,
            evidence_found=False,
        )
