"""
Elevated Control Loop & Intent Alignment Transfer Subsystem.
Extends control_loop.py with alignment transfer matrices and priority displacement metrics.
"""
from __future__ import annotations

import math
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional

from .control_loop import intent_alignment_check, ALIGNED, CONFLICTED, UNKNOWN


@dataclass
class AlignmentVector:
    """Vector representation of goal constraints vs execution reality."""
    failover_score: float = 1.0       # 1.0 = green, 0.0 = red pinned conflict
    canon_score: float = 1.0          # 1.0 = no stale branches
    budget_score: float = 1.0         # 1.0 = within budget
    duplicate_score: float = 1.0      # 1.0 = no duplicate claims

    @property
    def total_alignment_index(self) -> float:
        """Geometric mean of constraint alignment scores."""
        prod = self.failover_score * self.canon_score * self.budget_score * self.duplicate_score
        return round(prod ** (1.0 / 4.0), 4)


def compute_alignment_transfer(
    goal: Dict[str, Any],
    execution: Dict[str, Any],
    now: Optional[datetime] = None
) -> Tuple[AlignmentVector, str]:
    """
    Computes vector alignment index between goal and execution plane.
    Returns (alignment_vector, overall_status).
    """
    res = intent_alignment_check(goal, execution, now=now)
    status = res.get("verdict", UNKNOWN)

    conflicts = res.get("conflicts", [])
    unknowns = res.get("unknowns", [])

    failover_sc = 0.0 if any(c.get("check") == "provider_affinity" for c in conflicts) else 1.0
    canon_sc = 0.0 if any(c.get("check") == "canon_state" for c in conflicts) else 1.0
    budget_sc = 0.0 if any(c.get("check") == "lease_budget" for c in conflicts) else 1.0
    duplicate_sc = 0.0 if any(c.get("check") == "duplicate_claim" for c in conflicts) else 1.0

    if unknowns and not conflicts:
        failover_sc = 0.5 if any(u.get("check") == "provider_affinity" for u in unknowns) else failover_sc
        budget_sc = 0.5 if any(u.get("check") == "lease_budget" for u in unknowns) else budget_sc

    vec = AlignmentVector(
        failover_score=failover_sc,
        canon_score=canon_sc,
        budget_score=budget_sc,
        duplicate_score=duplicate_sc
    )
    return vec, status
