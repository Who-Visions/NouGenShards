from __future__ import annotations

from .models import (
    VaultId,
    PeerState,
    VaultPeer,
    NodeIdentity,
    VaultHealth,
    FleetHealth,
    VaultRecallResult,
    FederatedRecall,
    LocalCoverage,
    FleetCoverage,
    MatrixCell,
)
from .config import load_vault_peers, load_identity
from .client import FederationClient
from .service import FederationService
from .dedupe import logical_hash, dedupe_federated_hits
from .coverage import fetch_local_coverage, fleet_coverage
from .matrix import run_cell, run_matrix, assert_matrix_green
from .legacy import (
    federated_retrieve,
    FederatedResult,
    _lane_pool_size,
    _lane_executor,
)

__all__ = [
    "VaultId",
    "PeerState",
    "VaultPeer",
    "NodeIdentity",
    "VaultHealth",
    "FleetHealth",
    "VaultRecallResult",
    "FederatedRecall",
    "LocalCoverage",
    "FleetCoverage",
    "MatrixCell",
    "load_vault_peers",
    "load_identity",
    "FederationClient",
    "FederationService",
    "logical_hash",
    "dedupe_federated_hits",
    "fetch_local_coverage",
    "fleet_coverage",
    "run_cell",
    "run_matrix",
    "assert_matrix_green",
    "federated_retrieve",
    "FederatedResult",
    "_lane_pool_size",
    "_lane_executor",
]
