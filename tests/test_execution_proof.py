"""Tests for nougen_shards.execution_proof lifecycle evidence validation."""

import hashlib
import json

import pytest

from nougen_shards import execution_proof as ep

ENV_KEYS = [
    "NOUGEN_WORKFLOW_VERSION",
    "NOUGEN_AGENT",
    "NOUGEN_LANE",
    "CODEX_MODEL",
    "NOUGEN_AGENT_MODEL",
    "NOUGEN_POLICY_SHA256",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _evidence(ws, ctx, kind="checkpoint", **extra):
    (ws / "out.txt").write_text("hello", encoding="utf-8")
    proof = {
        "message_id": "m1",
        "kind": kind,
        "execution_receipt": {
            "execution_id": "e1",
            "worker": "w1",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
        },
        "context_binding": ctx,
        "artifacts": [{"path": "out.txt", "sha256": hashlib.sha256(b"hello").hexdigest()}],
    }
    proof.update(extra)
    return proof


def _verify(state, proof, ws, ctx=None):
    return ep.verify_lifecycle_evidence(
        state, proof, message_id="m1", consumer="w1", workspace_root=ws, expected_context=ctx
    )


def test_create_context_binding_hash_matches_snapshot(monkeypatch):
    monkeypatch.setenv("NOUGEN_LANE", "lane-a")
    ctx = ep.create_context_binding("m1", "abc", "w1")
    snap = ctx["snapshot"]
    assert snap["lane"] == "lane-a"
    assert snap["agent"] == "w1"
    assert snap["workflow_version"] == "nougen-live-v1"
    material = json.dumps(snap, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert ctx["context_hash"] == hashlib.sha256(material.encode()).hexdigest()


def test_parse_evidence_rejects_bad_json_and_non_object():
    with pytest.raises(ValueError):
        ep._parse_evidence("{not json")
    with pytest.raises(ValueError):
        ep._parse_evidence("[1]")
    assert ep._parse_evidence('{"a": 1}') == {"a": 1}


def test_parse_time_requires_timezone():
    with pytest.raises(ValueError, match="timezone"):
        ep._parse_time("2026-01-01T00:00:00", "started_at")
    with pytest.raises(ValueError, match="required"):
        ep._parse_time("", "started_at")
    assert ep._parse_time("2026-01-01T00:00:00Z", "started_at").tzinfo is not None


def test_checkpoint_valid(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    result = _verify("checkpointed", _evidence(tmp_path, ctx), tmp_path, ctx)
    assert result["verified"] is True
    assert len(result["evidence_sha256"]) == 64
    assert result["errors"] == []


def test_accepts_json_string_evidence(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    result = _verify("CHECKPOINTED", json.dumps(_evidence(tmp_path, ctx)), tmp_path, ctx)
    assert result["verified"] is True


def test_message_id_mismatch(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    proof = _evidence(tmp_path, ctx)
    proof["message_id"] = "other"
    result = _verify("CHECKPOINTED", proof, tmp_path, ctx)
    assert result["verified"] is False
    assert "message_id" in result["errors"][0]


def test_worker_must_match_consumer(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    proof = _evidence(tmp_path, ctx)
    proof["execution_receipt"]["worker"] = "intruder"
    assert "worker" in _verify("CHECKPOINTED", proof, tmp_path, ctx)["errors"][0]


def test_finished_before_started(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    proof = _evidence(tmp_path, ctx)
    proof["execution_receipt"]["finished_at"] = "2025-12-31T00:00:00Z"
    assert "precedes" in _verify("CHECKPOINTED", proof, tmp_path, ctx)["errors"][0]


def test_context_changed_after_claim(tmp_path, monkeypatch):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    proof = _evidence(tmp_path, ctx)
    monkeypatch.setenv("NOUGEN_POLICY_SHA256", "new-policy")
    result = _verify("CHECKPOINTED", proof, tmp_path, ctx)
    assert result["verified"] is False
    assert "changed after claim" in result["errors"][0]


def test_context_binding_mismatch_with_expected(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    other = ep.create_context_binding("m1", "zzz", "w1")
    result = _verify("CHECKPOINTED", _evidence(tmp_path, other), tmp_path, ctx)
    assert "does not match the context captured" in result["errors"][0]


def test_bad_context_hash(tmp_path):
    ctx = {"workflow_version": "v", "context_hash": "short"}
    result = _verify("CHECKPOINTED", _evidence(tmp_path, ctx), tmp_path)
    assert "SHA-256" in result["errors"][0]


def test_wrong_kind_for_state(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    result = _verify("FAILED", _evidence(tmp_path, ctx, reason="x"), tmp_path, ctx)
    assert "evidence.kind must be 'failure'" in result["errors"][0]


def test_failed_requires_reason_and_passes_with_it(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    bad = _verify("FAILED", _evidence(tmp_path, ctx, kind="failure"), tmp_path, ctx)
    assert "reason is required" in bad["errors"][0]
    good = _verify("FAILED", _evidence(tmp_path, ctx, kind="failure", reason="boom"), tmp_path, ctx)
    assert good["verified"] is True


def test_terminal_requires_finished_at(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    proof = _evidence(tmp_path, ctx, kind="blocked", reason="r")
    del proof["execution_receipt"]["finished_at"]
    assert "finished_at is required" in _verify("BLOCKED", proof, tmp_path, ctx)["errors"][0]


def test_artifact_digest_mismatch_and_path_escape(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    proof = _evidence(tmp_path, ctx)
    proof["artifacts"][0]["sha256"] = "0" * 64
    assert "does not match" in _verify("CHECKPOINTED", proof, tmp_path, ctx)["errors"][0]
    proof["artifacts"][0] = {"path": "../x", "sha256": "0" * 64}
    assert "within workspace_root" in _verify("CHECKPOINTED", proof, tmp_path, ctx)["errors"][0]


def test_artifacts_missing_or_no_workspace(tmp_path):
    assert ep._verify_artifacts({}, tmp_path)
    assert "workspace_root is required" in ep._verify_artifacts({"artifacts": [{}]}, None)[0]


def test_unknown_state_rejected(tmp_path):
    ctx = ep.create_context_binding("m1", "abc", "w1")
    result = _verify("PENDING", _evidence(tmp_path, ctx), tmp_path, ctx)
    assert result["verified"] is False
