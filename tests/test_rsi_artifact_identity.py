from dataclasses import replace
import os
import subprocess

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nougen_shards.rsi_artifact_identity import (
    artifact_hash, evaluate_artifact, verify_decision,
)
from nougen_shards.rsi_evaluation_ledger import (
    EvaluationContext, EvaluationLedger, EvaluationPending,
)


CONTEXT = EvaluationContext("epoch", "evaluator", "dataset", "parent", "task", "env")
KEY = Ed25519PrivateKey.generate()  # Ephemeral test key, never a service credential.
PUBLIC_KEY = KEY.public_key()


@pytest.fixture
def artifact(tmp_path):
    root = tmp_path / "candidate"
    root.mkdir()
    (root / "agent.py").write_text("result = True\n", encoding="utf-8")
    return root


@pytest.fixture
def ledger(tmp_path):
    value = EvaluationLedger(tmp_path / "private.db")
    value.start_epoch("epoch", "evaluator", "dataset", 5)
    return value


def test_hash_ignores_location_creation_order_and_mtime(artifact, tmp_path):
    (artifact / "empty").touch()
    other = tmp_path / "copy"
    other.mkdir()
    (other / "empty").touch()
    (other / "agent.py").write_bytes((artifact / "agent.py").read_bytes())
    os.utime(other / "agent.py", (1, 1))
    assert artifact_hash(artifact) == artifact_hash(other)


@pytest.mark.parametrize("change", ["byte", "rename", "empty_file", "empty_dir"])
def test_hash_binds_content_names_and_structure(artifact, change):
    prior = artifact_hash(artifact)
    if change == "byte":
        (artifact / "agent.py").write_text("result = False\n")
    elif change == "rename":
        (artifact / "agent.py").rename(artifact / "renamed.py")
    elif change == "empty_file":
        (artifact / "extra").touch()
    else:
        (artifact / "extra").mkdir()
    assert artifact_hash(artifact) != prior


def test_reject_symlink_escape_and_link_root(artifact, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "data").write_text("outside bytes")
    try:
        (artifact / "link").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Symlink creation unavailable: {error.winerror if hasattr(error, 'winerror') else error.errno}")
    with pytest.raises(ValueError, match="links"):
        artifact_hash(artifact)
    with pytest.raises(ValueError, match="links"):
        artifact_hash(artifact / "link")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_reject_windows_junction(artifact, tmp_path):
    outside = tmp_path / "junction-target"
    outside.mkdir()
    junction = artifact / "junction"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with pytest.raises(ValueError, match="reparse"):
        artifact_hash(artifact)


def test_real_evaluator_bit_signed_and_duplicate_not_rescored(artifact, ledger):
    calls = []
    def evaluate(root):
        calls.append(root)
        return False
    receipt = evaluate_artifact(ledger, CONTEXT, artifact, "A", evaluate, KEY)
    assert receipt.decision is False
    assert not hasattr(receipt, "token")
    assert verify_decision(receipt, CONTEXT, artifact_hash(artifact), PUBLIC_KEY)
    replay = evaluate_artifact(ledger, CONTEXT, artifact, "B", evaluate, KEY)
    assert replay == receipt
    assert calls == [artifact]
    assert ledger.spent("epoch") == 1


def test_tampered_bit_identity_context_or_key_fails(artifact, ledger):
    receipt = evaluate_artifact(ledger, CONTEXT, artifact, "A", lambda _: True, KEY)
    digest = artifact_hash(artifact)
    for fake in [replace(receipt, decision=False), replace(receipt, receipt_id="forged"),
                 replace(receipt, signature="0" * 128), replace(receipt, candidate_hash="fake"),
                 replace(receipt, signature="\u2603" * 128)]:
        assert not verify_decision(fake, CONTEXT, digest, PUBLIC_KEY)
    assert not verify_decision(receipt, replace(CONTEXT, parent_hash="other"), digest, PUBLIC_KEY)
    assert not verify_decision(receipt, CONTEXT, digest, Ed25519PrivateKey.generate().public_key())


@pytest.mark.parametrize("key", [None, b"", PUBLIC_KEY])
def test_missing_key_refuses_before_spending(artifact, ledger, key):
    with pytest.raises(ValueError, match="signing key"):
        evaluate_artifact(ledger, CONTEXT, artifact, "A", lambda _: True, key)
    assert ledger.spent("epoch") == 0


@pytest.mark.parametrize("field", ["epoch", "evaluator_hash", "dataset_hash",
                                  "parent_hash", "task_hash", "environment_hash"])
def test_signed_decision_cannot_replay_into_another_context(artifact, ledger, field):
    receipt = evaluate_artifact(ledger, CONTEXT, artifact, "A", lambda _: True, KEY)
    other = replace(CONTEXT, **{field: "different"})
    assert not verify_decision(receipt, other, artifact_hash(artifact), PUBLIC_KEY)
    assert not hasattr(PUBLIC_KEY, "sign")


def test_nonboolean_evaluator_result_is_not_authenticated(artifact, ledger):
    with pytest.raises(ValueError, match="boolean"):
        evaluate_artifact(ledger, CONTEXT, artifact, "A", lambda _: {"score": 1}, KEY)
    assert ledger.feedback(CONTEXT, artifact_hash(artifact)) is None
    assert ledger.spent("epoch") == 1


def test_mutation_during_evaluation_remains_spent_without_decision(artifact, ledger):
    original = artifact_hash(artifact)
    def mutate(root):
        (root / "agent.py").write_text("changed")
        return True
    with pytest.raises(ValueError, match="changed during"):
        evaluate_artifact(ledger, CONTEXT, artifact, "A", mutate, KEY)
    assert ledger.spent("epoch") == 1
    assert ledger.feedback(CONTEXT, original) is None
    with pytest.raises(EvaluationPending):
        ledger.reserve(CONTEXT, original, "retry")


def test_evaluator_exception_remains_spent(artifact, ledger):
    def failed(_):
        raise RuntimeError("Evaluator unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        evaluate_artifact(ledger, CONTEXT, artifact, "A", failed, KEY)
    assert ledger.spent("epoch") == 1
    assert ledger.feedback(CONTEXT, artifact_hash(artifact)) is None
