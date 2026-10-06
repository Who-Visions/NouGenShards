"""Tests for bounded session tool activity tracking, secret redaction, and ActivitySink."""
import json
import pytest

from nougen_shards import kaedra_tools as tools
from nougen_shards.tool_activity import (
    ActivitySink,
    SessionToolActivityTracker,
    redact_secrets,
)


def chat_sequence(name, arguments=None):
    responses = iter([
        {"message": {"tool_calls": [{"function": {
            "name": name, "arguments": arguments or {}}}]}},
        {"message": {"content": "done"}},
    ])
    return lambda *args, **kwargs: next(responses)


def test_native_loop_activity_is_correlated_and_private(tmp_path, monkeypatch):
    name = next(iter(tools.TOOL_NAMES))
    monkeypatch.setattr(tools, "dispatch", lambda *_: {"text": "secret-result"})
    sink = ActivitySink(tmp_path)
    text, calls = tools.run_tool_loop(chat_sequence(name, {"token": "secret-token"}),
                                      "fake", [], observer=sink)
    sink.flush()
    sink.close()
    raw = sink.path.read_text()
    events = [json.loads(line) for line in raw.splitlines()]
    assert text == "done" and calls[0]["ok"]
    assert [e["phase"] for e in events] == ["start", "end", "loop_end"]
    assert events[0]["invocation_id"] == events[1]["invocation_id"]
    assert "secret-token" not in raw and "secret-result" not in raw


def test_observer_failure_preserves_result(monkeypatch):
    class Broken:
        def emit(self, *args, **kwargs):
            raise OSError("disk unavailable")
    name = next(iter(tools.TOOL_NAMES))
    monkeypatch.setattr(tools, "dispatch", lambda *_: {"ok": True})
    assert tools.run_tool_loop(chat_sequence(name), "fake", [], observer=Broken())[0] == "done"


def test_refusal_and_exception(tmp_path, monkeypatch):
    sink = ActivitySink(tmp_path)
    tools.run_tool_loop(chat_sequence("unknown-secret"), "fake", [], observer=sink)
    name = next(iter(tools.TOOL_NAMES))
    def fail(*_):
        raise RuntimeError("original")
    monkeypatch.setattr(tools, "dispatch", fail)
    with pytest.raises(RuntimeError, match="original"):
        tools.run_tool_loop(chat_sequence(name), "fake", [], observer=sink)
    sink.flush()
    sink.close()
    events = [json.loads(x) for x in sink.path.read_text().splitlines()]
    assert {e.get("outcome") for e in events} >= {"refused", "exception"}
    assert "unknown-secret" not in sink.path.read_text()


def test_disk_ceiling_and_invalid_session(tmp_path):
    with pytest.raises(ValueError):
        ActivitySink(tmp_path, "../escape")
    sink = ActivitySink(tmp_path, max_bytes=1)
    sink.emit("start", "test")
    sink.flush()
    sink.close()
    assert sink.path.stat().st_size <= 1
    assert sink.status()["dropped_event_count"] == 1


def test_round_limit(tmp_path):
    sink = ActivitySink(tmp_path)
    tools.run_tool_loop(chat_sequence("unknown"), "fake", [], max_rounds=0, observer=sink)
    sink.flush()
    sink.close()
    assert json.loads(sink.path.read_text())["outcome"] == "round_limit"


def test_queue_saturation_is_visible(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    sink = ActivitySink(tmp_path, capacity=1)
    sink.emit("start", "test")
    sink.emit("end", "test")
    assert sink.status()["dropped_event_count"] == 1
    assert sink.pending.qsize() == 1


def test_session_collision_rejected(tmp_path):
    sink = ActivitySink(tmp_path, "same")
    sink.close()
    with pytest.raises(FileExistsError):
        ActivitySink(tmp_path, "same")


def test_environment_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_TOOL_ACTIVITY_DIR", str(tmp_path))
    assert tools.run_tool_loop(lambda *a, **k: {"message": {"content": "done"}},
                               "fake", [])[0] == "done"
    import time
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        files = list(tmp_path.glob("*.jsonl"))
        if files and files[0].stat().st_size:
            assert json.loads(files[0].read_text())["outcome"] == "complete"
            break
        time.sleep(0.01)
    else:
        pytest.fail("configured native loop did not write activity")


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

    final_text, call_log = tools.run_tool_loop(
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
