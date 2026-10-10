import os
import stat
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nougen_shards.rsi_artifact_identity import artifact_hash
from nougen_shards.rsi_evaluation_ledger import EvaluationContext, EvaluationLedger
from nougen_shards.rsi_receipts import (
    DecisionReceipt,
    check_key_permissions,
    create_receipt,
    generate_epoch_keypair,
    load_private_key,
    receipt_payload,
    sign_context_decision,
    sign_decision,
    verify_decision,
    verify_receipt,
)


@pytest.fixture
def tmp_key_file(tmp_path):
    key_path = tmp_path / "epoch_key.priv"
    key, pub_hex = generate_epoch_keypair(key_path)
    return key_path, key, pub_hex


@pytest.fixture
def sample_context():
    return EvaluationContext(
        epoch="epoch-2026-10-06",
        evaluator_hash="evaluator-sha256-abc123",
        dataset_hash="dataset-sha256-def456",
        parent_hash="parent-sha256-789",
        task_hash="task-sha256-012",
        environment_hash="env-sha256-345",
    )


def test_public_key_alone_verifies_signed_bit(tmp_key_file):
    key_path, key, pub_hex = tmp_key_file

    receipt_id = "receipt-001"
    epoch = "epoch-2026-10-06"
    evaluator_hash = "eval-hash-123"
    dataset_hash = "data-hash-456"

    # Test True decision
    sig_true = sign_decision(
        key=key,
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=True,
    )
    assert isinstance(sig_true, str)
    assert len(sig_true) == 128

    # Verify with hex string public key
    assert verify_decision(
        public_key=pub_hex,
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=True,
        signature=sig_true,
    )

    # Verify with Ed25519PublicKey instance
    pub_obj = key.public_key()
    assert verify_decision(
        public_key=pub_obj,
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=True,
        signature=sig_true,
    )

    # Verify with raw 32-byte bytes
    raw_pub = bytes.fromhex(pub_hex)
    assert verify_decision(
        public_key=raw_pub,
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=True,
        signature=sig_true,
    )

    # Test False decision
    sig_false = sign_decision(
        key=key,
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=False,
    )
    assert verify_decision(
        public_key=pub_hex,
        receipt_id=receipt_id,
        epoch=epoch,
        evaluator_hash=evaluator_hash,
        dataset_hash=dataset_hash,
        decision=False,
        signature=sig_false,
    )


def test_flipped_decision_fails(tmp_key_file):
    _, key, pub_hex = tmp_key_file
    receipt_id = "receipt-002"
    epoch = "epoch-1"
    evaluator_hash = "eval-1"
    dataset_hash = "data-1"

    # Sign True, verify False -> fails
    sig_true = sign_decision(key, receipt_id, epoch, evaluator_hash, dataset_hash, decision=True)
    assert not verify_decision(pub_hex, receipt_id, epoch, evaluator_hash, dataset_hash, decision=False, signature=sig_true)

    # Sign False, verify True -> fails
    sig_false = sign_decision(key, receipt_id, epoch, evaluator_hash, dataset_hash, decision=False)
    assert not verify_decision(pub_hex, receipt_id, epoch, evaluator_hash, dataset_hash, decision=True, signature=sig_false)


def test_tampered_context_fails(tmp_key_file):
    _, key, pub_hex = tmp_key_file
    receipt_id = "receipt-003"
    epoch = "epoch-1"
    evaluator_hash = "eval-1"
    dataset_hash = "data-1"

    sig = sign_decision(key, receipt_id, epoch, evaluator_hash, dataset_hash, decision=True)

    # Wrong receipt_id
    assert not verify_decision(pub_hex, "wrong-receipt", epoch, evaluator_hash, dataset_hash, decision=True, signature=sig)
    # Wrong epoch
    assert not verify_decision(pub_hex, receipt_id, "epoch-2", evaluator_hash, dataset_hash, decision=True, signature=sig)
    # Wrong evaluator_hash
    assert not verify_decision(pub_hex, receipt_id, epoch, "eval-tampered", dataset_hash, decision=True, signature=sig)
    # Wrong dataset_hash
    assert not verify_decision(pub_hex, receipt_id, epoch, evaluator_hash, "data-tampered", decision=True, signature=sig)


def test_another_epoch_key_fails(tmp_path):
    key1_path = tmp_path / "epoch1.key"
    key2_path = tmp_path / "epoch2.key"

    key1, pub1_hex = generate_epoch_keypair(key1_path)
    _, pub2_hex = generate_epoch_keypair(key2_path)

    sig1 = sign_decision(key1, "r-1", "epoch-1", "eval-1", "data-1", decision=True)

    # Key 1 verifies
    assert verify_decision(pub1_hex, "r-1", "epoch-1", "eval-1", "data-1", decision=True, signature=sig1)
    # Key 2 fails
    assert not verify_decision(pub2_hex, "r-1", "epoch-1", "eval-1", "data-1", decision=True, signature=sig1)


def test_signer_refuses_missing_key_file(tmp_path):
    nonexistent = tmp_path / "nonexistent.key"
    with pytest.raises(FileNotFoundError, match="not found"):
        load_private_key(nonexistent)
    with pytest.raises(FileNotFoundError, match="not found"):
        sign_decision(nonexistent, "r", "e", "ev", "d", True)


def test_signer_refuses_over_permissive_key_file(tmp_path):
    key_file = tmp_path / "insecure.key"
    key, _ = generate_epoch_keypair(key_file)

    # Test permission check validator directly on various permission modes
    with pytest.raises(PermissionError, match="too open"):
        check_key_permissions(0o644)
    with pytest.raises(PermissionError, match="too open"):
        check_key_permissions(0o660)
    with pytest.raises(PermissionError, match="too open"):
        check_key_permissions(0o777)
    with pytest.raises(PermissionError, match="too open"):
        check_key_permissions(stat.S_IFREG | 0o644)

    # Clean permissions pass without error
    check_key_permissions(0o600)
    check_key_permissions(0o400)
    check_key_permissions(stat.S_IFREG | 0o600)

    # If running on a POSIX platform with real chmod
    if os.name != "nt":
        os.chmod(key_file, 0o644)
        with pytest.raises(PermissionError, match="too open"):
            load_private_key(key_file, check_permissions=True)

        os.chmod(key_file, 0o600)
        loaded = load_private_key(key_file, check_permissions=True)
        assert isinstance(loaded, Ed25519PrivateKey)
    else:
        loaded = load_private_key(key_file, check_permissions=True)
        assert isinstance(loaded, Ed25519PrivateKey)


def test_decision_receipt_dataclass_and_serialization(tmp_key_file):
    key_path, key, pub_hex = tmp_key_file

    receipt = create_receipt(
        key=key_path,
        receipt_id="rec-42",
        epoch="epoch-beta",
        evaluator_hash="ev-hash-99",
        dataset_hash="ds-hash-88",
        decision=True,
    )

    assert isinstance(receipt, DecisionReceipt)
    assert receipt.public_key == pub_hex
    assert verify_receipt(receipt)
    assert verify_receipt(receipt, expected_public_key=pub_hex)

    # Test dictionary serialization round-trip
    d = receipt.to_dict()
    assert verify_receipt(d)
    restored = DecisionReceipt.from_dict(d)
    assert restored == receipt


def test_composition_with_context_and_ledger(tmp_key_file, sample_context, tmp_path):
    _, key, pub_hex = tmp_key_file

    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    (candidate_dir / "solution.py").write_text("def solve(): return 42\n", encoding="utf-8")

    c_hash = artifact_hash(candidate_dir)
    expected_receipt_id = EvaluationLedger.receipt_id(sample_context, c_hash)

    receipt = sign_context_decision(
        key=key,
        context=sample_context,
        candidate_hash=c_hash,
        decision=True,
    )

    assert receipt.receipt_id == expected_receipt_id
    assert receipt.epoch == sample_context.epoch
    assert receipt.evaluator_hash == sample_context.evaluator_hash
    assert receipt.dataset_hash == sample_context.dataset_hash
    assert receipt.decision is True
    assert verify_receipt(receipt, pub_hex)


def test_malformed_inputs_gracefully_rejected(tmp_key_file):
    _, key, pub_hex = tmp_key_file

    # Non-bool decision
    with pytest.raises(ValueError, match="boolean"):
        receipt_payload("r", "e", "ev", "ds", 1)  # type: ignore

    # Corrupted signature string
    assert not verify_decision(pub_hex, "r", "e", "ev", "ds", True, signature="not-hex")
    assert not verify_decision(pub_hex, "r", "e", "ev", "ds", True, signature="a" * 127)  # wrong length
    assert not verify_decision(pub_hex, "r", "e", "ev", "ds", True, signature=b"short-bytes")
    assert not verify_decision("invalid-pubkey", "r", "e", "ev", "ds", True, signature="a" * 128)
