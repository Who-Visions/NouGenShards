"""Signed per-hop receipts.

Every hop that touches an envelope writes a receipt: which node, which state,
when, signed with that node's receipt key (HMAC-SHA256 over the envelope's
canonical bytes plus the receipt fields). A sender can show exactly where a
message is, and nobody can forge an "acked" from outside the fleet.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

STATES = ("accepted", "refused", "pushed", "delivered", "acked", "answered", "expired", "failed")


def receipt_key(explicit: Optional[str] = None) -> bytes:
    """The node's receipt key: explicit, env, Keymaker, then the /msg token."""
    for cand in (explicit, os.environ.get("NOUGEN_WIRE_RECEIPT_KEY")):
        if cand:
            return cand.encode("utf-8")
    for name in ("NOUGEN_WIRE_RECEIPT_KEY", "NOUGEN_AGY_MSG_TOKEN"):
        try:
            from nougen_shards.keymaker import get_secret
            val = get_secret(name)
        except Exception:  # pylint: disable=broad-except
            val = None
        if val:
            return val.encode("utf-8")
    return b""


def _mac(key: bytes, env_canon: bytes, fields: Dict[str, Any]) -> str:
    body = env_canon + b"|" + json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def sign(key: bytes, env_canon: bytes, env_id: str, node: str, state: str, detail: str = "",
         ts: Optional[float] = None) -> Dict[str, Any]:
    if state not in STATES:
        raise ValueError(f"unknown receipt state {state!r}")
    fields = {"id": env_id, "node": node, "state": state, "detail": detail[:300],
              "ts": round(time.time() if ts is None else ts, 3)}
    fields["sig"] = _mac(key, env_canon, fields) if key else ""
    return fields


def verify(key: bytes, env_canon: bytes, receipt: Dict[str, Any]) -> bool:
    if not key or not receipt.get("sig"):
        return False
    fields = {k: receipt[k] for k in ("id", "node", "state", "detail", "ts") if k in receipt}
    return hmac.compare_digest(_mac(key, env_canon, fields), str(receipt["sig"]))
