"""Immutable serendipity receipts. Content-addressed; optionally HMAC-signed.

The id is sha256 over canonical JSON of everything but the seal, so the same
evidence reproduces the same id. A signing key, if used, comes from the
caller (e.g. Keymaker) and is never stored in the receipt."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Dict, Optional

from .model import Config, Event, Snapshot


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str).encode("utf-8")


def _r(x: float) -> float:
    return round(float(x), 6)


def build_receipt(a: Event, b: Event, result: Dict, snap: Snapshot, cfg: Config) -> Dict:
    f, ev = result["features"], result["features"]["_evidence"]
    first, later = sorted((a, b), key=lambda e: (e.observed_at_ms, e.event_id))
    body = {
        "type": "serendipity.receipt.v1",
        "score": _r(result["score"]),
        "raw_score": _r(result["raw"]),
        "classification": result["classification"],
        "rejected": result["rejected"],
        "events": [first.event_id, later.event_id],
        "features": {k: _r(v) for k, v in f.items() if not k.startswith("_")},
        "independence_evidence": ev["independence"],
        "temporal_evidence": {"gap_hours": _r(abs(a.observed_at_ms - b.observed_at_ms) / 3_600_000),
                              "windows": ev["calendar"]},
        "semantic_bridge": sorted(a.terms() & b.terms()),
        "base_rate": ev["base_rate"],
        "disconfirming_checks": [{**p, "penalty": _r(p["penalty"])} for p in result["penalties"]],
        "why_it_matters": sorted(set(first.explicit_user_intent + later.explicit_user_intent)),
        "provenance": [e.provenance_hash for e in (first, later)],
        "determinism": {
            "engine": cfg.version, "model_hash": cfg.model_hash,
            "embedding_version": cfg.embedding_version, "corpus_revision": snap.base_rates.revision,
            "timestamp_source": snap.timestamp_source, "weights": dict(cfg.weights),
        },
        "created_at_ms": snap.as_of_ms,
    }
    return seal(body)


def seal(body: Dict, key: Optional[bytes] = None) -> Dict:
    core = {k: v for k, v in body.items() if k not in ("candidate_id", "signature")}
    blob = _canon(core)
    out = {**core, "candidate_id": hashlib.sha256(blob).hexdigest()}
    if key:
        out["signature"] = "hmac-sha256:" + hmac.new(key, blob, hashlib.sha256).hexdigest()
    return out


def verify(receipt: Dict, key: Optional[bytes] = None) -> bool:
    again = seal(receipt, key)
    if again["candidate_id"] != receipt.get("candidate_id"):
        return False
    if key is None:
        return True  # content id matches; an unsigned check says nothing about a signature
    return hmac.compare_digest(again.get("signature", ""), receipt.get("signature", ""))
