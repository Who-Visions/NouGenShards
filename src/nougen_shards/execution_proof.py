"""Validation for evidence attached to live-message lifecycle transitions."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .poe_validator import PoEValidator


_ARTIFACT_STATES = {"CHECKPOINTED", "FAILED", "BLOCKED"}


def _parse_evidence(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("evidence must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("evidence must be a JSON object")
    return value


def create_context_binding(message_id: str, payload_sha256: str, consumer: str) -> Dict[str, Any]:
    """Snapshot the message and execution selectors when a worker takes it."""
    version = os.environ.get("NOUGEN_WORKFLOW_VERSION", "nougen-live-v1").strip()
    snapshot = {
        "message_id": str(message_id),
        "payload_sha256": str(payload_sha256),
        "consumer": str(consumer),
        "workflow_version": version,
        "agent": os.environ.get("NOUGEN_AGENT", "codex"),
        "lane": os.environ.get("NOUGEN_LANE", "unknown"),
        "model": os.environ.get("CODEX_MODEL", os.environ.get("NOUGEN_AGENT_MODEL", "unknown")),
        "policy_fingerprint": os.environ.get("NOUGEN_POLICY_SHA256", "unbound"),
    }
    digest = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {"workflow_version": version, "context_hash": digest, "snapshot": snapshot}


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"execution_receipt.{field} is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"execution_receipt.{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"execution_receipt.{field} must include a timezone")
    return parsed


def _verify_artifacts(evidence: Dict[str, Any], workspace_root: Optional[Path]) -> list[str]:
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return ["artifacts must contain at least one path and SHA-256 digest"]
    if workspace_root is None:
        return ["workspace_root is required to verify artifact digests"]
    root = Path(workspace_root).expanduser().resolve()
    errors = []
    for index, artifact in enumerate(artifacts):
        label = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{label} must be an object")
            continue
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(relative, str) or not relative.strip():
            errors.append(f"{label}.path is required")
            continue
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append(f"{label}.path must stay within workspace_root")
            continue
        if not isinstance(expected, str) or len(expected) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in expected):
            errors.append(f"{label}.sha256 must be a 64-character hexadecimal digest")
            continue
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append(f"{label}.path escapes workspace_root")
            continue
        try:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError as exc:
            errors.append(f"{label}.path cannot be read: {exc.__class__.__name__}")
            continue
        if actual.lower() != expected.lower():
            errors.append(f"{label}.sha256 does not match file contents")
    return errors


def verify_lifecycle_evidence(
    state: str,
    value: Any,
    *,
    message_id: str,
    consumer: str,
    workspace_root: Optional[Path] = None,
    expected_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate proof before a checkpoint or terminal lifecycle transition.

    COMPLETE requires the repository's PoE tuple and a physically present git
    commit. Other evidence-bearing states require a worker-bound execution
    receipt, semantic context binding, and artifacts whose SHA-256 values are
    recomputed from files under the configured workspace.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        proof = _parse_evidence(value)
        if proof.get("message_id") != message_id:
            raise ValueError("evidence.message_id does not match the lifecycle record")

        receipt = proof.get("execution_receipt")
        if not isinstance(receipt, dict):
            raise ValueError("execution_receipt object is required")
        if not str(receipt.get("execution_id") or "").strip():
            raise ValueError("execution_receipt.execution_id is required")
        if str(receipt.get("worker") or "").strip() != str(consumer):
            raise ValueError("execution_receipt.worker must match the advancing consumer")
        started = _parse_time(receipt.get("started_at"), "started_at")
        finished_value = receipt.get("finished_at")
        if finished_value:
            finished = _parse_time(finished_value, "finished_at")
            if finished < started:
                raise ValueError("execution_receipt.finished_at precedes started_at")

        context = proof.get("context_binding")
        if not isinstance(context, dict):
            raise ValueError("context_binding object is required")
        if not str(context.get("workflow_version") or "").strip():
            raise ValueError("context_binding.workflow_version is required")
        context_hash = str(context.get("context_hash") or "").strip()
        if len(context_hash) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in context_hash):
            raise ValueError("context_binding.context_hash must be a SHA-256 digest")
        if expected_context and context != expected_context:
            raise ValueError("context_binding does not match the context captured when the task was claimed")
        if expected_context:
            snapshot = expected_context.get("snapshot")
            if not isinstance(snapshot, dict):
                raise ValueError("acknowledged context snapshot is missing")
            material = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if hashlib.sha256(material.encode("utf-8")).hexdigest() != context_hash:
                raise ValueError("context_hash does not match the acknowledged context snapshot")
            current = {
                "workflow_version": os.environ.get("NOUGEN_WORKFLOW_VERSION", "nougen-live-v1").strip(),
                "agent": os.environ.get("NOUGEN_AGENT", "codex"),
                "lane": os.environ.get("NOUGEN_LANE", "unknown"),
                "model": os.environ.get("CODEX_MODEL", os.environ.get("NOUGEN_AGENT_MODEL", "unknown")),
                "policy_fingerprint": os.environ.get("NOUGEN_POLICY_SHA256", "unbound"),
            }
            if any(snapshot.get(key) != value for key, value in current.items()):
                raise ValueError("execution context changed after claim; re-plan before advancing")
            if snapshot.get("consumer") != consumer or snapshot.get("message_id") != message_id:
                raise ValueError("acknowledged context is bound to a different consumer or message")

        state = str(state).upper()
        expected_kind = {"CHECKPOINTED": "checkpoint", "COMPLETE": "complete",
                         "FAILED": "failure", "BLOCKED": "blocked"}.get(state)
        if proof.get("kind") != expected_kind:
            raise ValueError(f"evidence.kind must be {expected_kind!r} for {state}")
        if state in {"COMPLETE", "FAILED", "BLOCKED"} and not finished_value:
            raise ValueError("execution_receipt.finished_at is required for terminal transitions")
        if state == "COMPLETE":
            poe = proof.get("poe")
            if not isinstance(poe, dict):
                raise ValueError("poe object is required for COMPLETE")
            git_info = poe.get("git") if isinstance(poe.get("git"), dict) else {}
            repo_value = git_info.get("repo_path")
            repo = Path(repo_value).expanduser() if isinstance(repo_value, str) and repo_value.strip() else workspace_root
            valid, errors = PoEValidator.validate_poe_block(poe, workspace_root=repo)
            if not valid:
                raise ValueError("PoE validation failed: " + "; ".join(errors))
        elif state in _ARTIFACT_STATES:
            errors = _verify_artifacts(proof, workspace_root)
            if errors:
                raise ValueError("artifact verification failed: " + "; ".join(errors))
            reason = proof.get("reason")
            if state in {"FAILED", "BLOCKED"} and not str(reason or "").strip():
                raise ValueError("reason is required for FAILED and BLOCKED")
        else:
            raise ValueError(f"state {state} does not require execution evidence")

        canonical = json.dumps(proof, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {
            "verified": True,
            "verifier": "nougen_shards.execution_proof",
            "checked_at": checked_at,
            "evidence_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "normalized_evidence": proof,
            "errors": [],
        }
    except (ValueError, OSError) as exc:
        return {
            "verified": False,
            "verifier": "nougen_shards.execution_proof",
            "checked_at": checked_at,
            "evidence_sha256": None,
            "errors": [str(exc)],
        }
