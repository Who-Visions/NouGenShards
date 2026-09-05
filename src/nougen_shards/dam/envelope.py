"""Canonical event envelope for the shard capture dam.

The dam preserves INTENT, not truth. An event sealed here is durable but is
not yet a shard, and nothing in this module may present it as one -- that
distinction is the whole reason the dam is safe to build.

Encryption is AES-256-GCM. The plaintext shard body never leaves the trusted
node: the dam stores ciphertext plus routing metadata, so a reader with full
access to the HF repo learns operation, lane and timing but not content.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCHEMA = "nougen.shard-spool.v1"

# Operations the dam will accept. Everything else is refused at the gate, not
# filtered later -- an allowlist cannot be widened by a malformed payload.
SPOOLABLE = frozenset({"shards_capture", "shards_amend"})

# Refused unconditionally, even if a caller names them explicitly.
# shards_forget is irreversible and must never be replayed from a queue;
# vault/secret operations must never have their payload stored off-node.
NEVER_SPOOL = frozenset({
    "shards_forget", "vault_put", "vault_list", "keymaker_ingest",
})


class NotSpoolable(Exception):
    """Operation is not permitted into the dam. Never auto-retried."""


class TamperError(Exception):
    """Envelope failed signature, schema or AAD binding checks."""


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(txt: str) -> bytes:
    return base64.b64decode(txt.encode("ascii"))


def canonical_json(obj: Any) -> bytes:
    """Byte-stable JSON. Two callers building the same request must agree."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def compute_event_id(operation: str, payload: Dict[str, Any],
                     idempotency_key: Optional[str] = None) -> str:
    """sha256 over the canonical request.

    Identity is derived from the REQUEST, not from wall-clock or a random id,
    so the same failed write submitted twice produces one event rather than
    two -- acceptance test C depends on this.
    """
    basis = canonical_json({
        "operation": operation,
        "payload": payload,
        "idempotency_key": idempotency_key or "",
    })
    return "sha256:" + hashlib.sha256(basis).hexdigest()


def aad_for(event_id: str, operation: str, lane: str, created_utc: str) -> bytes:
    """Additional authenticated data. Binds ciphertext to its own metadata.

    Without this, an attacker who could rewrite the plaintext metadata of a
    stored object could replay a capture as an amendment, or attribute one
    lane's event to another, while the ciphertext still decrypted cleanly.
    """
    return canonical_json({
        "event_id": event_id, "operation": operation,
        "lane": lane, "created_utc": created_utc,
    })


def key_fingerprint(key: bytes) -> str:
    """Non-secret identifier for an envelope key, safe to store and log."""
    return hashlib.sha256(b"nougen-dam-fpr\x00" + key).hexdigest()[:16]


def seal(operation: str, payload: Dict[str, Any], *, key: bytes, lane: str,
         idempotency_key: Optional[str] = None,
         hmac_key: Optional[bytes] = None,
         created_utc: Optional[str] = None) -> Dict[str, Any]:
    """Build an encrypted, signed envelope. Raises NotSpoolable when refused."""
    if operation in NEVER_SPOOL:
        raise NotSpoolable(f"{operation} may never enter the dam")
    if operation not in SPOOLABLE:
        raise NotSpoolable(f"{operation} is not a spoolable operation")
    if len(key) != 32:
        raise ValueError("envelope key must be 32 bytes (AES-256)")

    created = created_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    event_id = compute_event_id(operation, payload, idempotency_key)
    aad = aad_for(event_id, operation, lane, created)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, canonical_json(payload), aad)

    env = {
        "schema": SCHEMA,
        "event_id": event_id,
        "idempotency_key": idempotency_key or event_id,
        "operation": operation,
        "created_utc": created,
        "lane": lane,
        "fleet_key_fingerprint": key_fingerprint(key),
        "target": "primary-shards",
        "payload_ciphertext": _b64(ct),
        "nonce": _b64(nonce),
        "aad_hash": hashlib.sha256(aad).hexdigest(),
        "attempt": 0,
        "status": "pending",
    }
    if hmac_key:
        env["ingress_sig"] = sign(env, hmac_key)
    return env


def signing_basis(env: Dict[str, Any]) -> bytes:
    """Fields covered by the ingress signature.

    Deliberately excludes `attempt` and `status`: the drainer updates those on
    every retry, and a signature that broke on a legitimate retry would be
    indistinguishable from tampering.
    """
    return canonical_json({k: env.get(k) for k in (
        "schema", "event_id", "idempotency_key", "operation", "created_utc",
        "lane", "fleet_key_fingerprint", "target", "payload_ciphertext",
        "nonce", "aad_hash",
    )})


def sign(env: Dict[str, Any], hmac_key: bytes) -> str:
    return hmac.new(hmac_key, signing_basis(env), hashlib.sha256).hexdigest()


def verify_signature(env: Dict[str, Any], hmac_key: bytes) -> bool:
    got = str(env.get("ingress_sig") or "")
    return bool(got) and hmac.compare_digest(got, sign(env, hmac_key))


def open_envelope(env: Dict[str, Any], *, key: bytes,
                  hmac_key: Optional[bytes] = None) -> Dict[str, Any]:
    """Verify and decrypt. Raises TamperError on any mismatch.

    Every failure mode here is a quarantine, never a retry: a payload that
    does not authenticate will not authenticate on the next attempt either,
    and replaying it blindly is how corrupted content reaches the reservoir.
    """
    if env.get("schema") != SCHEMA:
        raise TamperError(f"unknown schema {env.get('schema')!r}")
    op = str(env.get("operation") or "")
    if op in NEVER_SPOOL or op not in SPOOLABLE:
        raise TamperError(f"operation {op!r} is not replayable")
    if hmac_key is not None and not verify_signature(env, hmac_key):
        raise TamperError("ingress signature mismatch")

    aad = aad_for(str(env.get("event_id")), op, str(env.get("lane")),
                  str(env.get("created_utc")))
    if hashlib.sha256(aad).hexdigest() != env.get("aad_hash"):
        raise TamperError("aad_hash does not match envelope metadata")

    try:
        pt = AESGCM(key).decrypt(_unb64(str(env["nonce"])),
                                 _unb64(str(env["payload_ciphertext"])), aad)
    except Exception as exc:  # InvalidTag and friends
        raise TamperError(f"ciphertext failed authentication: {type(exc).__name__}")

    payload = json.loads(pt.decode("utf-8"))

    # Identity must survive the round trip: a decrypted payload whose hash no
    # longer matches the stored event_id means the object was swapped.
    expect = compute_event_id(op, payload, str(env.get("idempotency_key") or ""))
    if expect != env.get("event_id"):
        # idempotency_key defaults to event_id at seal time; retry that form.
        if compute_event_id(op, payload, None) != env.get("event_id"):
            raise TamperError("payload does not match event_id")
    return payload
