"""NouGenShards: Persistent local memory for coding agents.

Engine: Valerion — The Metameric Memory Engine (21-step cognitive architecture).
"""
from .core import capture, retrieve, mark_shard, compile_recall_packet
from .federation import federated_retrieve
from .history import HistoryEngine, log_event, init_history_db
from .graph import link_shards, related_shards
from .gatekeeper import check_mutation_gate

__version__ = "1.1.0"
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
