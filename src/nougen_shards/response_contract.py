"""Provider-independent response completeness and attribution helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

UNKNOWN_MODEL = "UNKNOWN"


@dataclass(frozen=True)
class ResponseMetadata:
    requested_model: str
    actual_model: str = UNKNOWN_MODEL
    finish_reason: str | None = None
    complete: bool = False
    status: str = "incomplete"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["identity_verified"] = (self.actual_model != UNKNOWN_MODEL
                                     and self.actual_model == self.requested_model)
        return data


def response_metadata(requested_model: str, actual_model: str | None,
                      content: str | None, finish_reason: str | None,
                      refusal: str | None = None) -> ResponseMetadata:
    """Classify an API response; model prose is deliberately never inspected."""
    actual = str(actual_model).strip() if actual_model else UNKNOWN_MODEL
    finish = str(finish_reason).strip().lower() if finish_reason else None
    body = content if isinstance(content, str) else ""
    if "content-safety" in (actual if actual != UNKNOWN_MODEL else requested_model).lower():
        return ResponseMetadata(requested_model, actual, finish, False,
                                "safety_only", "classification_model_not_generative_review")
    if refusal or finish in {"content_filter", "safety", "blocked"}:
        return ResponseMetadata(requested_model, actual, finish, False, "safety", "provider_safety")
    if not body.strip():
        return ResponseMetadata(requested_model, actual, finish, False, "empty", "empty_content")
    if finish in {"length", "max_tokens", "max_output_tokens"}:
        return ResponseMetadata(requested_model, actual, finish, False, "partial", "token_limit")
    if finish not in {"stop", "end_turn", "stop_sequence", "completed"}:
        return ResponseMetadata(requested_model, actual, finish, False, "incomplete", "missing_or_unfinished")
    if actual != UNKNOWN_MODEL and actual != requested_model:
        return ResponseMetadata(requested_model, actual, finish, False,
                                "identity_mismatch", "actual_model_differs_from_requested")
    return ResponseMetadata(requested_model, actual, finish, True, "complete")
