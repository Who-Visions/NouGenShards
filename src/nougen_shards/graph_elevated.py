"""
Elevated Shard Graph Topology & PageRank Subsystem.
Extends graph.py with power iteration PageRank centrality and topological density metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set


@dataclass
class GraphTopologyMetrics:
    """Topology metrics for shard graph network."""
    node_count: int = 0
    edge_count: int = 0
    density: float = 0.0
    pagerank: Dict[str, float] = field(default_factory=dict)


def compute_pagerank(
    edges: List[Tuple[str, str]],
    d: float = 0.85,
    max_iter: int = 50,
    tol: float = 1e-6
) -> Dict[str, float]:
    """
    Computes PageRank centrality vector over directed edge tuples (src, dst).
    Returns normalized dictionary mapping node_hash -> PageRank score in [0.0, 1.0].
    """
    nodes: Set[str] = set()
    out_edges: Dict[str, List[str]] = {}
    in_edges: Dict[str, List[str]] = {}

    for src, dst in edges:
        nodes.add(src)
        nodes.add(dst)
        out_edges.setdefault(src, []).append(dst)
        in_edges.setdefault(dst, []).append(src)

    num_nodes = len(nodes)
    if num_nodes == 0:
        return {}

    # Initialize uniform PageRank vector
    pr: Dict[str, float] = {node: 1.0 / num_nodes for node in nodes}
    base_rank = (1.0 - d) / num_nodes

    for iteration in range(max_iter):
        next_pr: Dict[str, float] = {}
        diff = 0.0

        for node in nodes:
            incoming = in_edges.get(node, [])
            rank_sum = 0.0
            for src in incoming:
                deg = len(out_edges.get(src, []))
                if deg > 0:
                    rank_sum += pr[src] / deg
            
            val = base_rank + d * rank_sum
            next_pr[node] = val
            diff += abs(val - pr[node])

        pr = next_pr
        if diff < tol:
            break

    # Normalize rank sum to 1.0
    total = sum(pr.values()) or 1.0
    return {node: round(score / total, 4) for node, score in pr.items()}


def compute_graph_density(node_count: int, edge_count: int, directed: bool = True) -> float:
    """Computes graph topological density score in [0.0, 1.0]."""
    if node_count <= 1:
        return 0.0
    max_edges = node_count * (node_count - 1) if directed else (node_count * (node_count - 1)) / 2.0
    if max_edges == 0:
        return 0.0
    return round(min(1.0, edge_count / max_edges), 4)
