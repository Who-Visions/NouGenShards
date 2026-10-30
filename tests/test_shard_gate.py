"""Unit and integration tests for Layer 4 Truth Anchor Shard Gate."""

import os
import pytest
from unittest.mock import patch

from nougen_shards.shard_gate import (
    ShardGate,
    ShardGateDecision,
    ShardEvidenceRejectionError,
)
from nougen_shards import core


class TestShardGateDetection:
    """Tests detection of task resolution / success claims."""

    def test_ordinary_note_not_claimed(self):
        is_claim, reason = ShardGate.is_success_claim(
            title="Overview of Transformer Architecture",
            content="Transformers use self-attention mechanisms to process sequential data in parallel.",
            event_type="concept_learning",
            tags=["nlp", "deep_learning"],
        )
        assert is_claim is False
        assert "no success claim" in reason

    def test_success_detected_by_event_type(self):
        for evt in ["fix", "bugfix", "completion", "resolution", "task_complete", "passed"]:
            is_claim, reason = ShardGate.is_success_claim(
                title="Routine database migration",
                content="Applied schema updates.",
                event_type=evt,
            )
            assert is_claim is True
            assert evt in reason

    def test_success_detected_by_tag(self):
        for tag in ["#fix", "#resolved", "#completed", "bugfix", "solution"]:
            is_claim, reason = ShardGate.is_success_claim(
                title="Database migration",
                content="Applied schema updates.",
                event_type="migration",
                tags=["infra", tag],
            )
            assert is_claim is True
            assert tag in reason

    def test_success_detected_by_title_pattern(self):
        claims = [
            "[FIX] Null pointer in query parser",
            "[RESOLVED] Port conflict on 8765",
            "Bug is fixed in session handler",
            "Issue resolved after cache invalidation",
            "Task is completed for user auth",
        ]
        for title in claims:
            is_claim, _ = ShardGate.is_success_claim(
                title=title,
                content="Investigation log details.",
                event_type="note",
            )
            assert is_claim is True, f"Failed to detect success claim in title: {title}"

    def test_success_detected_by_content_pattern(self):
        content = "All tests passed after applying the patch. Verified fix on blade."
        is_claim, _ = ShardGate.is_success_claim(
            title="Session notes",
            content=content,
            event_type="devlog",
        )
        assert is_claim is True


class TestShardGateEvidenceValidation:
    """Tests evaluation and validation of Scoreboard evidence."""

    def test_reject_unverified_claim(self):
        decision = ShardGate.evaluate_shard(
            title="Fixed latency spike in relay",
            content="Optimized database connection pooling and the bug is resolved.",
            event_type="bugfix",
        )
        assert decision.allowed is False
        assert decision.is_success_claim is True
        assert decision.evidence_found is False
        assert "REJECTED by Truth Anchor Shard Gate" in decision.reason

    def test_raise_on_unverified_claim(self):
        with pytest.raises(ShardEvidenceRejectionError) as exc_info:
            ShardGate.evaluate_shard(
                title="[FIX] Session memory leak",
                content="Cleaned up orphaned dict keys.",
                raise_on_reject=True,
            )
        assert "REJECTED by Truth Anchor Shard Gate" in str(exc_info.value)

    def test_reject_failing_exit_code(self):
        bad_evidence = {
            "command": "pytest tests/test_core.py",
            "exit_code": 1,
            "stdout": "1 failed, 12 passed in 1.2s",
        }
        decision = ShardGate.evaluate_shard(
            title="[FIX] Memory leak",
            content="Attempted patch.",
            event_type="fix",
            evidence=bad_evidence,
        )
        assert decision.allowed is False
        assert "failing exit_code" in decision.reason

    def test_reject_empty_output_or_command(self):
        # Empty command
        decision = ShardGate.evaluate_shard(
            title="[FIX] Memory leak",
            content="Attempted patch.",
            event_type="fix",
            evidence={"command": "", "exit_code": 0, "stdout": "ok"},
        )
        assert decision.allowed is False
        assert "missing non-empty 'command'" in decision.reason

        # Empty output
        decision2 = ShardGate.evaluate_shard(
            title="[FIX] Memory leak",
            content="Attempted patch.",
            event_type="fix",
            evidence={"command": "pytest", "exit_code": 0, "stdout": ""},
        )
        assert decision2.allowed is False
        assert "missing command stdout/output proof" in decision2.reason

    def test_allow_valid_structured_evidence(self):
        valid_evidence = {
            "command": "pytest tests/test_truth_anchor.py -v",
            "exit_code": 0,
            "stdout": "================ 5 passed in 0.42s ================",
        }
        decision = ShardGate.evaluate_shard(
            title="[FIX] Null pointer in session lookup",
            content="Patched defensive None check in core.py.",
            event_type="fix",
            evidence=valid_evidence,
        )
        assert decision.allowed is True
        assert decision.evidence_found is True
        assert decision.evidence_payload["exit_code"] == 0
        assert "pytest tests/test_truth_anchor.py" in decision.evidence_payload["command"]

    def test_allow_embedded_scoreboard_markdown_block(self):
        content = """# Bug Resolution Report

The issue was caused by an unbound TCP port.

```scoreboard
command: python -m pytest tests/test_network.py
exit_code: 0
output: 10 passed in 0.88s
```

All acceptance criteria satisfied.
"""
        decision = ShardGate.evaluate_shard(
            title="[RESOLVED] Port 8765 listener issue",
            content=content,
            event_type="resolution",
        )
        assert decision.allowed is True
        assert decision.evidence_found is True
        assert decision.evidence_payload["exit_code"] == 0
        assert "test_network.py" in decision.evidence_payload["command"]


class TestCoreCaptureIntegration:
    """Tests end-to-end enforcement through core.capture()."""

    def test_ordinary_shard_allowed(self):
        with patch.dict(os.environ, {"NOUGEN_SHARD_GATE_ENFORCE": "1"}):
            with patch("nougen_shards.core._get_dedup_connection") as mock_conn:
                mock_conn.return_value.execute.return_value.fetchone.return_value = (1,)
                # Non-completion note should not raise
                res = core.capture(
                    event_type="research_note",
                    title="Notes on SQLite WAL indexing",
                    content="WAL mode allows concurrent readers without blocking writes.",
                )
                assert res is not None

    def test_unverified_success_shard_rejected_by_core(self):
        with patch.dict(os.environ, {"NOUGEN_SHARD_GATE_ENFORCE": "1"}):
            with pytest.raises(ShardEvidenceRejectionError) as exc_info:
                core.capture(
                    event_type="fix",
                    title="Resolved critical caching bug",
                    content="Optimized memory caching without running tests.",
                )
            assert "REJECTED by Truth Anchor Shard Gate" in str(exc_info.value)

    def test_verified_success_shard_allowed_by_core(self):
        evidence = {
            "command": "pytest tests/test_cache.py",
            "exit_code": 0,
            "stdout": "3 passed in 0.15s",
        }
        with patch.dict(os.environ, {"NOUGEN_SHARD_GATE_ENFORCE": "1"}):
            with patch("nougen_shards.core._get_dedup_connection") as mock_conn:
                mock_conn.return_value.execute.return_value.fetchone.return_value = (1,)
                res = core.capture(
                    event_type="fix",
                    title="[FIX] Cache invalidation",
                    content="Added cache flush on mutation.",
                    evidence=evidence,
                )
                assert res is not None

    def test_bypass_when_gate_explicitly_disabled(self):
        with patch.dict(os.environ, {"NOUGEN_SHARD_GATE_ENFORCE": "0"}):
            with patch("nougen_shards.core._get_dedup_connection") as mock_conn:
                mock_conn.return_value.execute.return_value.fetchone.return_value = (1,)
                # Disabled gate allows write through
                res = core.capture(
                    event_type="fix",
                    title="Fix without evidence when gate off",
                    content="Bypassed by operator setting.",
                )
                assert res is not None
