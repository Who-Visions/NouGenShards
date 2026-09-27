"""
Elevated Knowledge Distillation & Compression Ratio Subsystem.
Extends distill.py with information compression ratios and knowledge density metrics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional

from .distill import ATOM_TYPES, ENTITY_KINDS, norm_entity


@dataclass
class DistillationMetrics:
    """Quantitative metrics for distillation quality and compression ratio."""
    raw_character_count: int = 0
    atom_character_count: int = 0
    atom_count: int = 0
    entity_count: int = 0
    relation_count: int = 0

    @property
    def compression_ratio(self) -> float:
        """Information compression ratio: 1 - (atom_chars / raw_chars)."""
        if self.raw_character_count <= 0:
            return 0.0
        ratio = 1.0 - (self.atom_character_count / float(self.raw_character_count))
        return round(max(0.0, min(1.0, ratio)), 4)

    @property
    def knowledge_density(self) -> float:
        """Knowledge density score per 1,000 raw characters."""
        if self.raw_character_count <= 0:
            return 0.0
        return round((self.atom_count * 1000.0) / float(self.raw_character_count), 4)


def compute_distillation_metrics(
    raw_text: str,
    atoms: List[Dict[str, str]],
    entities: List[Dict[str, str]],
    relations: List[Dict[str, str]]
) -> DistillationMetrics:
    """Computes formal DistillationMetrics tensor."""
    raw_len = len(raw_text)
    atom_len = sum(len(a.get("text", "")) for a in atoms)
    valid_entities = [e for e in entities if norm_entity(e.get("name", ""))]

    return DistillationMetrics(
        raw_character_count=raw_len,
        atom_character_count=atom_len,
        atom_count=len(atoms),
        entity_count=len(valid_entities),
        relation_count=len(relations)
    )
