import json

import pytest

from nougen_shards import kaedra_tools as tools
from nougen_shards.tool_activity import ActivitySink


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
