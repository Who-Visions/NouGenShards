"""Hugging Face Space orchestration bridge.

This module is intentionally additive: local handoff JSON and handoffs.db remain
the source of truth. The Space is treated as a remote control-plane/rendezvous
surface for Hyperion and other nodes.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from . import keymaker


DEFAULT_SPACE_ID = "WhoVisions/nga_hgf_Space"
DEFAULT_TOKEN_KEYS = (
    "Yuki_HGF_key",
    "HUGGINGFACE_API_KEY",
    "HF_TOKEN",
    "Agy_HF_Api",
)
VALID_LOG_KINDS = {"run", "build"}


@dataclass(frozen=True)
class SpaceCredential:
    """Resolved HF credential metadata. The token value is never serialized."""

    key: Optional[str]
    token: Optional[str]

    @property
    def present(self) -> bool:
        return bool(self.token)

    def redacted_header(self) -> Dict[str, str]:
        if not self.present:
            return {}
        return {"Authorization": f"Bearer <redacted:{self.key}>"}


def normalize_space_id(space_id: Optional[str] = None) -> str:
    """Return owner/name for a Hugging Face Space."""
    value = (space_id or os.getenv("NOUGEN_HF_SPACE_ID") or DEFAULT_SPACE_ID).strip()
    prefixes = (
        "https://huggingface.co/spaces/",
        "https://huggingface.co/api/spaces/",
    )
    for prefix in prefixes:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value.strip("/")


def space_log_url(kind: str = "run", space_id: Optional[str] = None) -> str:
    """Return the SSE log URL for the configured Space."""
    if kind not in VALID_LOG_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_LOG_KINDS)}")
    return f"https://huggingface.co/api/spaces/{normalize_space_id(space_id)}/logs/{kind}"


def resolve_hf_credential(token_key: Optional[str] = None) -> SpaceCredential:
    """Resolve the first configured HF token from Keymaker or environment."""
    ordered_keys = []
    if token_key:
        ordered_keys.append(token_key)
    env_key = os.getenv("NOUGEN_HF_TOKEN_KEY")
    if env_key and env_key not in ordered_keys:
        ordered_keys.append(env_key)
    ordered_keys.extend(key for key in DEFAULT_TOKEN_KEYS if key not in ordered_keys)

    for key in ordered_keys:
        token = keymaker.get_secret(key) or os.getenv(key)
        if token:
            return SpaceCredential(key=key, token=token)
    return SpaceCredential(key=None, token=None)


def build_log_request(kind: str = "run", space_id: Optional[str] = None,
                      token_key: Optional[str] = None) -> Dict[str, Any]:
    """Build redacted request metadata for Space log access."""
    credential = resolve_hf_credential(token_key)
    return {
        "space_id": normalize_space_id(space_id),
        "kind": kind,
        "url": space_log_url(kind, space_id),
        "token_key": credential.key,
        "token_present": credential.present,
        "headers": credential.redacted_header(),
    }


def _redact_token(text: str, credential: SpaceCredential) -> str:
    if credential.token:
        return text.replace(credential.token, f"<redacted:{credential.key}>")
    return text


def fetch_log_snapshot(kind: str = "run", space_id: Optional[str] = None,
                       token_key: Optional[str] = None, max_bytes: int = 65536,
                       timeout: float = 10.0) -> Dict[str, Any]:
    """Fetch a bounded snapshot from the Space SSE log endpoint."""
    credential = resolve_hf_credential(token_key)
    req = urllib.request.Request(space_log_url(kind, space_id), method="GET")
    if credential.present:
        req.add_header("Authorization", f"Bearer {credential.token}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = _redact_token(
                res.read(max(1, max_bytes)).decode("utf-8", errors="replace"),
                credential,
            )
            return {
                "status": "ok",
                "space_id": normalize_space_id(space_id),
                "kind": kind,
                "url": space_log_url(kind, space_id),
                "token_key": credential.key,
                "token_present": credential.present,
                "body": body,
            }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "status": "error",
            "space_id": normalize_space_id(space_id),
            "kind": kind,
            "url": space_log_url(kind, space_id),
            "token_key": credential.key,
            "token_present": credential.present,
            "error": f"{type(exc).__name__}: {exc}",
        }


def get_space_orchestration_anchor(limit: int = 5, max_chars: int = 8000,
                                   space_id: Optional[str] = None,
                                   token_key: Optional[str] = None) -> str:
    """Return a compact anchor that layers HF Space over local handoffs."""
    from . import hooks  # Local import avoids a hooks -> bridge import cycle.

    credential = resolve_hf_credential(token_key)
    local_anchor = hooks.get_latest_anchor(limit=limit, max_chars=max_chars // 2)
    lines = [
        "[HF_SPACE_ORCHESTRATION]",
        "Mode: additive control-plane; local handoff JSON and handoffs.db remain source of truth.",
        f"Space: {normalize_space_id(space_id)}",
        f"Run logs: {space_log_url('run', space_id)}",
        f"Build logs: {space_log_url('build', space_id)}",
        f"Credential: key={credential.key or 'missing'}; present={str(credential.present).lower()}",
        "Protocol: read local handoff -> checkpoint/start locally -> mirror/rendezvous through Space -> keep raw tokens in Keymaker.",
        "",
        local_anchor,
    ]
    anchor = "\n".join(lines).strip()
    if len(anchor) > max_chars:
        anchor = anchor[: max(0, max_chars - 28)].rstrip() + "\n[SPACE_ANCHOR_TRUNCATED]"
    return anchor


def snapshot_json(**kwargs: object) -> str:
    """Serialize redacted Space request metadata for scripts/hooks."""
    return json.dumps(build_log_request(**kwargs), indent=2)
