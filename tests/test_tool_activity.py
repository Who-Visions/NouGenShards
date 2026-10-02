"""Tests for bounded session tool activity tracking and secret redaction."""

from nougen_shards.tool_activity import (
    SessionToolActivityTracker,
    redact_secrets,
)
from nougen_shards.kaedra_tools import run_tool_loop


def test_redact_secrets():
    prefix_g = "AIza"
    prefix_gh = "ghp_"
    raw = f"My key is {prefix_g}SyD-1234567890abcdefghijklmnopqrst and token {prefix_gh}123456789012345678901234567890123456"
    redacted = redact_secrets(raw)
    assert prefix_g not in redacted
    assert "[REDACTED_GOOGLE_KEY]" in redacted
    assert prefix_gh not in redacted
    assert "[REDACTED_GH_TOKEN]" in redacted


def test_tracker_bounding():
    tracker = SessionToolActivityTracker("sess_test_001", max_records=5)
    for i in range(10):
        tracker.record_call(
            tool_name=f"tool_{i % 3}",
            arguments={"query": f"test {i}"},
            ok=True,
            result_size=100,
            duration_ms=10.5,
        )

    assert tracker.total_calls == 10
    records = tracker.get_records()
    assert len(records) == 5  # Bounded to max_records
    assert records[-1].arguments["query"] == "test 9"


def test_tracker_summarize_and_projection():
    prefix_sk = "sk-"
    tracker = SessionToolActivityTracker("sess_test_hud", max_records=10)
    tracker.record_call("shards_search", {"query": "tensor", "key": f"{prefix_sk}123456789012345678901"}, ok=True, result_size=250, duration_ms=12.0)
    tracker.record_call("shards_recall", {"locator": "phoebus:1#100"}, ok=False, result_size=50, duration_ms=4.0, error="not found")

    summary = tracker.summarize()
    assert summary["session_id"] == "sess_test_hud"
    assert summary["total_calls"] == 2
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 1
    assert summary["tools_used"] == {"shards_search": 1, "shards_recall": 1}

    hud = tracker.project_bounded_context(max_tokens_approx=100)
    assert "[TOOL_ACTIVITY | Session: sess_test_hud]" in hud
    assert "Total: 2 calls" in hud
    assert "shards_search" in hud


def test_kaedra_tool_loop_tracker_integration():
    tracker = SessionToolActivityTracker("sess_loop_test")

    # Mock chat_fn that invokes fleet_whoami then returns text
    round_count = 0

    def mock_chat(model, msgs, tools=None):
        nonlocal round_count
        round_count += 1
        if round_count == 1:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "fleet_whoami",
                                "arguments": {},
                            }
                        }
                    ],
                }
            }
        else:
            return {
                "message": {
                    "role": "assistant",
                    "content": "Node identity retrieved.",
                }
            }

    final_text, call_log = run_tool_loop(
        chat_fn=mock_chat,
        model="dummy_model",
        messages=[{"role": "user", "content": "who are you"}],
        max_rounds=2,
        tracker=tracker,
    )

    assert "Node identity retrieved." in final_text
    assert len(call_log) == 1
    assert call_log[0]["tool"] == "fleet_whoami"
    assert tracker.total_calls == 1
    assert "fleet_whoami" in tracker.counts
