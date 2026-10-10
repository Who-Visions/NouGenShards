"""Ed25519 per-epoch receipt signing for RSI evaluation decisions.

Replaces HMAC env-key seal_decision with asymmetric Ed25519 digital signatures.
A per-epoch keypair is generated at epoch start: the private key is stored in a
0600 file outside candidate sandboxes, and the public key is published in the
epoch record. Verifiers require only the public key, preventing cross-process
or verifier forgery.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from dataclasses import asdict, dataclass
from typing import Any, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .rsi_evaluation_ledger import EvaluationContext, EvaluationLedger


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def export_public_key_hex(key: Union[Ed25519PublicKey, Ed25519PrivateKey]) -> str:
    """Export the raw 32-byte Ed25519 public key as a 64-character lowercase hex string."""
    pub = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    if not isinstance(pub, Ed25519PublicKey):
        raise ValueError("Key must be an Ed25519PrivateKey or Ed25519PublicKey")
    return pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def load_public_key(key: Union[Ed25519PublicKey, str, bytes]) -> Ed25519PublicKey:
    """Load an Ed25519 public key from an instance, hex string, raw bytes, or PEM."""
    if isinstance(key, Ed25519PublicKey):
        return key
    if isinstance(key, str):
        cleaned = key.strip()
        if cleaned.startswith("-----BEGIN"):
            return serialization.load_pem_public_key(cleaned.encode("utf-8"))  # type: ignore[return-value]
        if len(cleaned) == 64 and all(c in "0123456789abcdefABCDEF" for c in cleaned):
            return Ed25519PublicKey.from_public_bytes(bytes.fromhex(cleaned))
        raise ValueError(f"Invalid public key string format (length={len(cleaned)})")
    if isinstance(key, (bytes, bytearray)):
        raw = bytes(key)
        if raw.startswith(b"-----BEGIN"):
            return serialization.load_pem_public_key(raw)  # type: ignore[return-value]
        if len(raw) == 32:
            return Ed25519PublicKey.from_public_bytes(raw)
        raise ValueError(f"Invalid public key byte length: expected 32, got {len(raw)}")
    raise TypeError(f"Unsupported public key type: {type(key).__name__}")


def check_key_permissions(mode: int) -> None:
    """Validate that key file permissions are strictly owner-only (0600 / 0400).

    Rejects if any group (0o070) or others (0o007) bits are set.
    """
    if mode & 0o077 != 0:
        mode_oct = oct(stat.S_IMODE(mode))
        raise PermissionError(
            f"Signing key file permissions too open ({mode_oct}); must be 0600 (owner only)"
        )


def load_private_key(key_path: Union[str, Path], check_permissions: bool = True) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from a file, enforcing 0600 file permissions.

    Refuses if the file does not exist, is not a regular file, or has group/other
    permissions set (mode & 0o077 != 0 on POSIX).
    """
    path = Path(key_path)
    if not path.exists():
        raise FileNotFoundError(f"Signing key file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Signing key path is not a regular file: {path}")

    if check_permissions and os.name != "nt":
        check_key_permissions(path.stat().st_mode)

    data = path.read_bytes()
    if data.startswith(b"-----BEGIN"):
        loaded = serialization.load_pem_private_key(data, password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError("Loaded PEM key is not an Ed25519 private key")
        return loaded
    if len(data) == 32:
        return Ed25519PrivateKey.from_private_bytes(data)
    # Check if stored as hex string
    try:
        decoded_text = data.decode("ascii").strip()
        if len(decoded_text) == 64:
            return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(decoded_text))
    except Exception:
        pass

    raise ValueError(f"Unrecognized private key file format in {path}")


def generate_epoch_keypair(key_path: Union[str, Path]) -> tuple[Ed25519PrivateKey, str]:
    """Generate a fresh Ed25519 keypair for an epoch, storing the private key securely.

    The private key is saved with strict 0600 permissions. Returns (private_key, public_key_hex).
    """
    path = Path(key_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    key = Ed25519PrivateKey.generate()
    raw_private = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Write securely with 0600
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    fd = os.open(str(path), flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw_private)
    except Exception:
        os.close(fd)
        raise

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

    public_key_hex = export_public_key_hex(key)
    return key, public_key_hex


def receipt_payload(
    receipt_id: str,
    epoch: str,
    evaluator_hash: str,
    dataset_hash: str,
    decision: bool,
) -> bytes:
    """Construct the canonical binary payload signed for an RSI evaluation decision."""
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        raise ValueError("receipt_id must be a nonempty string")
    if not isinstance(epoch, str) or not epoch.strip():
        raise ValueError("epoch must be a nonempty string")
    if not isinstance(evaluator_hash, str) or not evaluator_hash.strip():
        raise ValueError("evaluator_hash must be a nonempty string")
    if not isinstance(dataset_hash, str) or not dataset_hash.strip():
        raise ValueError("dataset_hash must be a nonempty string")
    if type(decision) is not bool:
        raise ValueError("decision must be a boolean")

    return _encode({
        "dataset_hash": dataset_hash,
        "decision": decision,
        "epoch": epoch,
        "evaluator_hash": evaluator_hash,
        "receipt_id": receipt_id,
        "version": 1,
    })


@dataclass(frozen=True)
class DecisionReceipt:
    """Authenticated evaluator receipt carrying an Ed25519 digital signature."""
    receipt_id: str
    epoch: str
    evaluator_hash: str
    dataset_hash: str
    decision: bool
    signature: str
    public_key: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionReceipt:
        return cls(
            receipt_id=str(data["receipt_id"]),
            epoch=str(data["epoch"]),
            evaluator_hash=str(data["evaluator_hash"]),
            dataset_hash=str(data["dataset_hash"]),
            decision=bool(data["decision"]),
            signature=str(data["signature"]),
            public_key=str(data["public_key"]),
        )


def sign_decision(
    key: Union[Ed25519PrivateKey, str, Path],
    receipt_id: str,
    epoch: str,
    evaluator_hash: str,
    dataset_hash: str,
    decision: bool,
) -> str:
    """Sign an evaluator decision bit with an Ed25519 private key.

    Returns the signature as a 128-character lowercase hex string.
    """
    if isinstance(key, (str, Path)):
        private_key = load_private_key(key)
    elif isinstance(key, Ed25519PrivateKey):
        private_key = key
    else:
        raise TypeError(f"Unsupported signing key type: {type(key).__name__}")

    payload = receipt_payload(
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=decision,
    )
    return private_key.sign(payload).hex()


def verify_decision(
    public_key: Union[Ed25519PublicKey, str, bytes],
    receipt_id: str,
    epoch: str,
    evaluator_hash: str,
    dataset_hash: str,
    decision: bool,
    signature: Union[str, bytes],
) -> bool:
    """Verify an Ed25519-signed evaluator decision using only the public key.

    Returns True if valid, False if signature is invalid or any field was tampered.
    """
    if type(decision) is not bool:
        return False
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        return False
    if not isinstance(epoch, str) or not epoch.strip():
        return False
    if not isinstance(evaluator_hash, str) or not evaluator_hash.strip():
        return False
    if not isinstance(dataset_hash, str) or not dataset_hash.strip():
        return False

    try:
        pub = load_public_key(public_key)
    except Exception:
        return False

    if isinstance(signature, str):
        sig_str = signature.strip()
        if len(sig_str) != 128 or any(c not in "0123456789abcdefABCDEF" for c in sig_str):
            return False
        try:
            sig_bytes = bytes.fromhex(sig_str)
        except ValueError:
            return False
    elif isinstance(signature, (bytes, bytearray)):
        sig_bytes = bytes(signature)
        if len(sig_bytes) != 64:
            return False
    else:
        return False

    try:
        payload = receipt_payload(
            receipt_id=receipt_id,
            epoch=epoch,
            evaluator_hash=evaluator_hash,
            dataset_hash=dataset_hash,
            decision=decision,
        )
        pub.verify(sig_bytes, payload)
        return True
    except (InvalidSignature, ValueError):
        return False


def create_receipt(
    key: Union[Ed25519PrivateKey, str, Path],
    receipt_id: str,
    epoch: str,
    evaluator_hash: str,
    dataset_hash: str,
    decision: bool,
) -> DecisionReceipt:
    """Sign and wrap a decision into a complete DecisionReceipt."""
    if isinstance(key, (str, Path)):
        private_key = load_private_key(key)
    elif isinstance(key, Ed25519PrivateKey):
        private_key = key
    else:
        raise TypeError(f"Unsupported signing key type: {type(key).__name__}")

    signature = sign_decision(
        key=private_key,
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=decision,
    )
    pub_hex = export_public_key_hex(private_key)
    return DecisionReceipt(
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=decision,
        signature=signature,
        public_key=pub_hex,
    )


def verify_receipt(
    receipt: Union[DecisionReceipt, dict[str, Any]],
    expected_public_key: Union[Ed25519PublicKey, str, bytes, None] = None,
) -> bool:
    """Verify a DecisionReceipt against an expected public key (or its embedded public key)."""
    if isinstance(receipt, dict):
        try:
            receipt = DecisionReceipt.from_dict(receipt)
        except Exception:
            return False
    elif not isinstance(receipt, DecisionReceipt):
        return False

    pub_to_use = expected_public_key if expected_public_key is not None else receipt.public_key
    return verify_decision(
        public_key=pub_to_use,
        receipt_id=receipt.receipt_id,
        epoch=receipt.epoch,
        evaluator_hash=receipt.evaluator_hash,
        dataset_hash=receipt.dataset_hash,
        decision=receipt.decision,
        signature=receipt.signature,
    )


def sign_context_decision(
    key: Union[Ed25519PrivateKey, str, Path],
    context: EvaluationContext,
    candidate_hash: str,
    decision: bool,
) -> DecisionReceipt:
    """Compose with EvaluationContext and EvaluationLedger to sign an artifact decision."""
    receipt_id = EvaluationLedger.receipt_id(context, candidate_hash)
    return create_receipt(
        key=key,
        receipt_id=receipt_id,
        epoch=context.epoch,
        evaluator_hash=context.evaluator_hash,
        dataset_hash=context.dataset_hash,
        decision=decision,
    )
