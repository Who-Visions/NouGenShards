"""NouGenShards: Persistent local memory for coding agents.

Engine: Valerion — The Metameric Memory Engine (21-step cognitive architecture).
"""
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from .core import capture, retrieve, mark_shard, compile_recall_packet
from .federation import federated_retrieve
from .history import HistoryEngine, log_event, init_history_db
from .graph import link_shards, related_shards
from .gatekeeper import check_mutation_gate

# Read from installed package metadata rather than restated here. The v1.2.0
# release bumped pyproject.toml and left this line at 1.1.0, so `nougen
# --version` reported a version that had not shipped for two releases — the one
# number whose whole job is to be trustworthy. One source, no drift.
try:
    __version__ = _pkg_version("nougen-shards")
except PackageNotFoundError:  # running from a source tree, never installed
    __version__ = "0.0.0+unknown"
VALERION_ENGINE = "Valerion"

__all__ = [
    "capture",
    "retrieve",
    "mark_shard",
    "compile_recall_packet",
    "federated_retrieve",
    "HistoryEngine",
    "log_event",
    "init_history_db",
    "link_shards",
    "related_shards",
    "check_mutation_gate",
]
