"""NouGenShards: Persistent local memory for coding agents."""
from .core import capture, retrieve, mark_shard, compile_recall_packet

__version__ = "1.0.0"
__all__ = ["capture", "retrieve", "mark_shard", "compile_recall_packet"]
