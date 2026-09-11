from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VaultId(str, Enum):
    BLADE = "blade"
    PHOEBUS = "phoebus"
    WHOART = "whoart"


class PeerState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VaultPeer:
    vault_id: VaultId
    base_url: str
    enabled: bool = True
    health_path: str = "/v1/health/local"
    recall_path: str = "/v1/recall"
    coverage_path: str = "/v1/coverage/local"


@dataclass(frozen=True)
class NodeIdentity:
    machine_id: str
    vault_id: VaultId
    instance_id: str


@dataclass
class VaultHealth:
    vault_id: str
    reachable: bool
    healthy: bool
    current: bool
    verified: bool
    state: str
    latency_ms: float | None
    endpoint: str
    machine_id: str | None = None
    instance_id: str | None = None
    shard_count: int | None = None
    newest_timestamp: str | None = None
    db_count: int | None = None
    db_expected: int | None = None
    error_class: str | None = None
    error: str | None = None


@dataclass
class FleetHealth:
    healthy: bool
    reachable: bool
    complete: bool
    current: bool
    verified: bool
    cannot_determine: bool
    vaults_expected: int
    vaults_reachable: int
    vaults_healthy: int
    vaults_current: int
    vaults_verified: int
    vaults: list[VaultHealth] = field(default_factory=list)


@dataclass
class VaultRecallResult:
    vault_id: str
    ok: bool
    latency_ms: float
    hits: list[dict[str, Any]]
    error_class: str | None = None
    error: str | None = None


@dataclass
class FederatedRecall:
    query: str
    complete: bool
    cannot_determine: bool
    vaults_expected: int
    vaults_answered: int
    correlation_id: str
    hits: list[dict[str, Any]]
    per_vault: list[VaultRecallResult]


@dataclass
class LocalCoverage:
    vault_id: str
    machine_id: str
    db_present: int
    db_expected: int
    shard_count: int
    newest_timestamp: str | None
    oldest_timestamp: str | None


@dataclass
class FleetCoverage:
    complete: bool
    cannot_determine: bool
    vaults_expected: int
    vaults_answered: int
    deduplicated_fleet_total: int | None
    per_vault: dict[str, dict[str, Any]]


@dataclass
class MatrixCell:
    source: str
    target: str
    ok: bool
    identity_ok: bool
    sentinel_ok: bool
    latency_ms: float | None
    error: str | None = None
