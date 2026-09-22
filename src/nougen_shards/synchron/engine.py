"""Candidate detection over one snapshot: every cross-source pair, scored,
debiased, sealed, and sorted. Deterministic ordering throughout."""
from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Optional

from .model import Config, Snapshot
from .receipt import build_receipt, seal
from .score import score_pair


def detect(snap: Snapshot, cfg: Optional[Config] = None, *, include_rejected: bool = False,
           key: Optional[bytes] = None) -> List[Dict]:
    cfg = cfg or Config()
    events = sorted(snap.events, key=lambda e: (e.observed_at_ms, e.event_id))
    out = []
    for a, b in combinations(events, 2):
        if a.source_id == b.source_id:
            continue  # not cross-source: never a candidate
        result = score_pair(a, b, snap, cfg)
        if result["rejected"] and not include_rejected:
            continue
        r = build_receipt(a, b, result, snap, cfg)
        out.append(seal(r, key) if key else r)
    return sorted(out, key=lambda r: (-r["score"], r["candidate_id"]))
