"""Signed per-hop receipts.

Every hop that touches an envelope writes a receipt: which node, which state,
when, signed with that node's receipt key (HMAC-SHA256 over the envelope's
canonical bytes plus the receipt fields). A sender can show exactly where a
message is, and nobody without the key can forge one.

Every receipt names its ``scheme``, so a reader knows what the signature
proves:

- ``node``: a dedicated per-node NOUGEN_WIRE_RECEIPT_KEY. Proof that node wrote it.
- ``shared-key``: the fallback, the fleet's shared /msg token. Proof only that
  some holder of that token wrote it; one lane could forge another's hop.
- ``unsigned``: no key resolved. Proves nothing; ``verify`` is always False.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

STATES = ("accepted", "refused", "pushed", "delivered", "acked", "answered", "expired", "failed")


def resolve_key(explicit: Optional[str] = None) -> Tuple[bytes, str]:
    """(key, scheme): a dedicated receipt key first, then the shared /msg token."""
    for cand in (explicit, os.environ.get("NOUGEN_WIRE_RECEIPT_KEY")):
        if cand:
            return cand.encode("utf-8"), "node"
    for name, scheme in (("NOUGEN_WIRE_RECEIPT_KEY", "node"), ("NOUGEN_AGY_MSG_TOKEN", "shared-key")):
        try:
            from nougen_shards.keymaker import get_secret
            val = get_secret(name)
        except Exception:  # pylint: disable=broad-except
            val = None
        if val:
            return val.encode("utf-8"), scheme
    return b"", "unsigned"


def node_key(path: str) -> bytes:
    """This node's own receipt key, made on first start and kept beside the
    wire db (0600). Only this node signs and verifies its receipts, so a local
    key is real per-node proof with zero setup. Raises if it can't be kept."""
    try:
        with open(path, "rb") as f:
            key = f.read().strip()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    import secrets
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    key = secrets.token_hex(32).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


def receipt_key(explicit: Optional[str] = None) -> bytes:
    return resolve_key(explicit)[0]


def _mac(key: bytes, env_canon: bytes, fields: Dict[str, Any]) -> str:
    body = env_canon + b"|" + json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def sign(key: bytes, env_canon: bytes, env_id: str, node: str, state: str, detail: str = "",
         ts: Optional[float] = None, scheme: str = "node") -> Dict[str, Any]:
    if state not in STATES:
        raise ValueError(f"unknown receipt state {state!r}")
    fields = {"id": env_id, "node": node, "state": state, "detail": detail[:300],
              "ts": round(time.time() if ts is None else ts, 3),
              "scheme": scheme if key else "unsigned"}
    fields["sig"] = _mac(key, env_canon, fields) if key else ""
    return fields


def verify(key: bytes, env_canon: bytes, receipt: Dict[str, Any]) -> bool:
    if not key or not receipt.get("sig"):
        return False
    if receipt.get("scheme") == "unsigned":
        return False
    fields = {k: receipt[k] for k in ("id", "node", "state", "detail", "ts", "scheme") if k in receipt}
    return hmac.compare_digest(_mac(key, env_canon, fields), str(receipt["sig"]))
