"""NouGenShards: Persistent local memory for coding agents."""
from .core import capture, retrieve, mark_shard, compile_recall_packet
from .federation import federated_retrieve
from .history import HistoryEngine, log_event, init_history_db

__version__ = "1.0.0"
__all__ = [
    "capture", 
    "retrieve", 
    "mark_shard", 
    "compile_recall_packet", 
    "federated_retrieve",
    "HistoryEngine",
    "log_event",
    "init_history_db"
]
