"""Artifact identity and deterministic content-addressed representations for RSI search.

Candidate proposals, models, code modifications, and benchmark environments must be
canonically identified before entering evaluation. This module provides:
1. Canonical content hashing with domain separation (prevents type confusion attacks).
2. Artifact metadata tracking (canonical paths, hashes, sizes, byte-level invariants).
3. Deterministic serialization guarantees for candidates across fleet machines.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


class InvalidArtifactError(ValueError):
    """Raised when an artifact fails content verification or schema constraints."""


@dataclass(frozen=True)
class ArtifactDescriptor:
    """Immutable, content-addressed descriptor of an RSI evaluation artifact."""
    artifact_type: str
    artifact_id: str
    content_hash: str
    byte_size: int
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.artifact_type or not isinstance(self.artifact_type, str):
            raise InvalidArtifactError("artifact_type must be a nonempty string")
        if not self.artifact_id or not isinstance(self.artifact_id, str):
            raise InvalidArtifactError("artifact_id must be a nonempty string")
        if not self.content_hash or len(self.content_hash) != 64:
            raise InvalidArtifactError("content_hash must be a valid 64-char hex SHA-256")
        if self.byte_size < 0:
            raise InvalidArtifactError("byte_size cannot be negative")


def canonical_json_bytes(data: Any) -> bytes:
    """Deterministic JSON byte representation ensuring identical hashes across all platforms."""
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def hash_artifact_bytes(artifact_type: str, raw_bytes: bytes) -> str:
    """Domain-separated SHA-256 digest of raw artifact bytes.

    Prefixes hash calculation with domain tag 'rsi:<artifact_type>:' to prevent
    collision/substitution across heterogeneous artifact classes.
    """
    domain_prefix = f"rsi:{artifact_type.strip().lower()}:".encode("utf-8")
    hasher = hashlib.sha256()
    hasher.update(domain_prefix)
    hasher.update(raw_bytes)
    return hasher.hexdigest()


def create_artifact_descriptor(
    artifact_type: str,
    artifact_id: str,
    content: bytes | str | Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactDescriptor:
    """Build a validated, content-addressed ArtifactDescriptor."""
    if isinstance(content, str):
        raw_bytes = content.encode("utf-8")
    elif isinstance(content, (dict, list)):
        raw_bytes = canonical_json_bytes(content)
    elif isinstance(content, bytes):
        raw_bytes = content
    else:
        raise InvalidArtifactError(f"Unsupported content payload type: {type(content)}")

    c_hash = hash_artifact_bytes(artifact_type, raw_bytes)
    meta = dict(metadata or {})
    return ArtifactDescriptor(
        artifact_type=artifact_type.strip().lower(),
        artifact_id=artifact_id.strip(),
        content_hash=c_hash,
        byte_size=len(raw_bytes),
        metadata=meta,
    )


def verify_artifact_integrity(
    descriptor: ArtifactDescriptor,
    content: bytes | str | Mapping[str, Any],
) -> bool:
    """Verify that a content payload strictly matches its content-addressed descriptor."""
    fresh = create_artifact_descriptor(
        artifact_type=descriptor.artifact_type,
        artifact_id=descriptor.artifact_id,
        content=content,
        metadata=descriptor.metadata,
    )
    return (
        fresh.content_hash == descriptor.content_hash
        and fresh.byte_size == descriptor.byte_size
    )
