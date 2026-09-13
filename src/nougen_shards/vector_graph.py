"""
NouGen Vector Graph: Compatibility alias & topology helper forwarding to nougen_shards.graph.
"""

from .graph import (
    link_shards,
    related_shards,
    edge_count,
    get_node_centrality,
    init_graph_db,
    get_graph_db_path
)


def stats():
    """Returns vector graph connectivity statistics."""
    return {
        "edges": edge_count(),
        "db_path": str(get_graph_db_path()),
        "status": "active"
    }


__all__ = [
    "link_shards",
    "related_shards",
    "edge_count",
    "get_node_centrality",
    "init_graph_db",
    "get_graph_db_path",
    "stats"
]
