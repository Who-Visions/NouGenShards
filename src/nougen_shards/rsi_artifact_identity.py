"""Artifact-bound, authenticated decisions for a trusted evaluator service.

Candidate code must not have access to this service's signing key or ledger.
evaluate_artifact copies the candidate into an evaluator-owned snapshot, hashes the COPY for
the receipt and runs the evaluator on the copy only, so a concurrent writer on the source
cannot change what was scored (CWE-367). Residual: code running as the evaluator's own uid
can mutate and restore the snapshot undetected; that needs a separate uid or read-only mount.
Ed25519 authenticates the evaluator's assertion, not the correctness of its test.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .rsi_artifact_snapshot import evaluator_readonly_snapshot
from .rsi_evaluation_ledger import EvaluationContext, EvaluationLedger


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _checked_stat(path: Path) -> os.stat_result:
    info = path.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
        raise ValueError("Artifact links and reparse points are forbidden")
    return info


def artifact_hash(root: str | Path) -> str:
    """Digest sorted relative names, structure, bytes and executable flags.

    Location and timestamps are excluded. Empty files/directories are included;
    symlinks, Windows reparse points and special files are rejected. This is a
    content identifier for an immutable snapshot, not a filesystem access jail.
    """
    root = Path(root)
    if not stat.S_ISDIR(_checked_stat(root).st_mode):
        raise ValueError("Artifact root must be a directory")
    canonical_root = root.resolve()
    entries = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in sorted(dirs + files):
            path = base / name
            info = _checked_stat(path)
            try:
                path.resolve().relative_to(canonical_root)
            except ValueError as error:
                raise ValueError("Artifact path escapes its root") from error
            relative = path.relative_to(root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                entries.append((relative, "directory"))
            elif stat.S_ISREG(info.st_mode):
                digest = hashlib.sha256()
                with path.open("rb") as source:
                    opened = os.fstat(source.fileno())
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise ValueError("Artifact changed while hashing")
                    for chunk in iter(lambda: source.read(65536), b""):
                        digest.update(chunk)
                    closed = os.fstat(source.fileno())
                after = _checked_stat(path)
                def identity(value):
                    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
                            value.st_mode)
                if identity(info) != identity(closed) or identity(info) != identity(after):
                    raise ValueError("Artifact changed while hashing")
                entries.append((relative, "file", digest.hexdigest(),
                                bool(info.st_mode & stat.S_IXUSR)))
            else:
                raise ValueError("Artifact special files are forbidden")
    return hashlib.sha256(_encode(sorted(entries))).hexdigest()


def _key(key: Ed25519PrivateKey | None) -> Ed25519PrivateKey:
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("An evaluator-private Ed25519 signing key is required")
    return key


@dataclass(frozen=True)
class SignedDecision:
    receipt_id: str
    context: EvaluationContext
    candidate_hash: str
    decision: bool
    signature: str


def _payload(receipt_id: str, context: EvaluationContext,
             candidate_hash: str, decision: bool) -> bytes:
    return _encode({"version": 1, "receipt_id": receipt_id,
                    "context": asdict(context), "candidate_hash": candidate_hash,
                    "decision": decision})


def verify_decision(
    receipt: SignedDecision, expected_context: EvaluationContext,
    expected_candidate_hash: str, public_key: Ed25519PublicKey
) -> bool:
    """Verify attribution and exact context; False decisions can be authentic.

    The pinned public key belongs to the expected evaluator epoch; do not trust
    a public key supplied by the candidate or embedded in an untrusted receipt.
    """
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("A pinned evaluator public key is required")
    if (receipt.context != expected_context
            or receipt.candidate_hash != expected_candidate_hash
            or type(receipt.decision) is not bool
            or not isinstance(receipt.signature, str)
            or len(receipt.signature) != 128
            or any(c not in "0123456789abcdef" for c in receipt.signature)):
        return False
    expected_id = EvaluationLedger.receipt_id(expected_context, expected_candidate_hash)
    if receipt.receipt_id != expected_id:
        return False
    try:
        public_key.verify(bytes.fromhex(receipt.signature),
                          _payload(receipt.receipt_id, receipt.context,
                                   receipt.candidate_hash, receipt.decision))
    except InvalidSignature:
        return False
    return True


def evaluate_artifact(
    ledger: EvaluationLedger, context: EvaluationContext, root: str | Path,
    lineage: str, evaluator: Callable[[Path], bool], signing_key: Ed25519PrivateKey
) -> SignedDecision:
    """Trusted evaluator entry point; never expose completion tokens.

    Context/evaluator are selected by service configuration, not candidate input.
    The service must measure evaluator/dataset hashes and isolate execution.
    Errors or mutations leave the reservation spent; no decision is signed.
    """
    key = _key(signing_key)
    _checked_stat(Path(root))  # a link or reparse-point root is refused before anything is copied
    # Snapshot before reserving: a refused tree (symlink, hardlink, FIFO) never spends a query.
    with evaluator_readonly_snapshot(root) as (snapshot, _digest):
        candidate = artifact_hash(snapshot)
        reservation = ledger.reserve(context, candidate, lineage)
        if reservation.cached:
            decision = reservation.decision
        else:
            decision = evaluator(snapshot)
            if type(decision) is not bool:
                raise ValueError("Evaluator must return only a boolean decision")
            if artifact_hash(snapshot) != candidate:
                raise ValueError("Artifact changed during evaluation")
            ledger.finish(reservation, decision)
    signature = key.sign(_payload(reservation.receipt_id, context, candidate,
                                  decision)).hex()
    return SignedDecision(reservation.receipt_id, context, candidate, decision, signature)
