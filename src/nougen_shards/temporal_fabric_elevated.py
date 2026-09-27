"""
Elevated Vector Clock & Causal Concurrency Subsystem.
Extends temporal_fabric.py with multi-node Vector Clocks, partial order causal matrices, and concurrency analysis.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional



@dataclass
class VectorClock:
    """Vector Clock V in N^K space for multi-node event ordering."""
    clock_vector: Dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str) -> VectorClock:
        """Increments node_id logical tick."""
        new_vec = dict(self.clock_vector)
        new_vec[node_id] = new_vec.get(node_id, 0) + 1
        return VectorClock(new_vec)

    def merge(self, other: VectorClock) -> VectorClock:
        """Elementwise max across all nodes."""
        merged = dict(self.clock_vector)
        for node, count in other.clock_vector.items():
            merged[node] = max(merged.get(node, 0), count)
        return VectorClock(merged)

    def compare(self, other: VectorClock) -> str:
        """
        Determines causal relationship between self (V_A) and other (V_B):
        - "definitely_before": V_A <= V_B and V_A != V_B
        - "definitely_after": V_B <= V_A and V_A != V_B
        - "identical": V_A == V_B
        - "concurrent": V_A || V_B (uncomparable partial order)
        """
        all_nodes = set(self.clock_vector.keys()) | set(other.clock_vector.keys())
        
        less_or_equal = True
        greater_or_equal = True

        for node in all_nodes:
            val_a = self.clock_vector.get(node, 0)
            val_b = other.clock_vector.get(node, 0)

            if val_a > val_b:
                less_or_equal = False
            if val_a < val_b:
                greater_or_equal = False

        if less_or_equal and greater_or_equal:
            return "identical"
        if less_or_equal:
            return "definitely_before"
        if greater_or_equal:
            return "definitely_after"
        return "concurrent"


def compute_causal_matrix(clocks: Dict[str, VectorClock]) -> Dict[Tuple[str, str], str]:
    """Computes full NxN pairwise causal matrix across named event clocks."""
    matrix = {}
    keys = sorted(clocks.keys())
    for i in range(len(keys)):
        for j in range(len(keys)):
            k1, k2 = keys[i], keys[j]
            matrix[(k1, k2)] = clocks[k1].compare(clocks[k2])
    return matrix
