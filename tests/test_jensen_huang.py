"""JensenHuang: 50-lane fan-out, failure isolation, and the no-key path.

All NIM calls are stubbed; no live key or network is needed. The one
exception is the missing-key test, which uses the real client with no key
resolved — on a keyless box that path never touches the network.
"""
import json
import threading
import time

import pytest

from nougen_shards import jensen_huang as jh
from nougen_shards.nvidia_nim import VERIFIED_CHAT_MODELS, NvidiaNimClient


def _agent(monkeypatch, chat):
    """A JensenHuang whose lanes all answer through stub ``chat``."""
    monkeypatch.setattr(NvidiaNimClient, "chat", chat)
    return jh.JensenHuang(api_key="test-key")


def _tasks(n, prefix="task"):
    return [{"id": f"{prefix}-{i}", "prompt": f"say {i}"} for i in range(n)]


def test_fifty_tasks_complete_and_aggregate(monkeypatch):
    def fake_chat(self, model, messages, max_tokens=1024, fallbacks=None):
        self.last_model = "stub-model"
        return "answer"

    agent = _agent(monkeypatch, fake_chat)
    results = agent.fan_out(_tasks(50), lanes=50)
    assert len(results) == 50
    assert [r["id"] for r in results] == [f"task-{i}" for i in range(50)]
    assert all(r["status"] == "ok" for r in results)
    assert all(r["content"] == "answer" for r in results)
    summary = jh.JensenHuang.summarize(results)
    assert summary == {
        "total": 50,
        "succeeded": 50,
        "failed": 0,
        "per_model": {"stub-model": 50},
        "total_latency_s": summary["total_latency_s"],
        "mean_latency_s": summary["mean_latency_s"],
        "failed_ids": [],
    }
    assert summary["total_latency_s"] >= 0
    assert summary["mean_latency_s"] >= 0


def test_concurrency_is_real_and_lanes_are_honored(monkeypatch):
    active = {"n": 0, "max": 0}
    lock = threading.Lock()

    def fake_chat(self, model, messages, max_tokens=1024, fallbacks=None):
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
        time.sleep(0.3)
        with lock:
            active["n"] -= 1
        return "answer"

    agent = _agent(monkeypatch, fake_chat)
    started = time.perf_counter()
    results = agent.fan_out(_tasks(50), lanes=50)
    wall = time.perf_counter() - started
    assert len(results) == 50
    assert all(r["status"] == "ok" for r in results)
    # Sequential would take 50 x 0.3 = 15s; 50 lanes finish in about one sleep.
    assert wall < 5.0, f"50 tasks took {wall:.2f}s — not parallel"
    assert active["max"] >= 20, f"peak concurrency only {active['max']}"

    # A 5-lane cap is a real cap: never more than 5 in flight at once.
    active["max"] = 0
    results = agent.fan_out(_tasks(10), lanes=5)
    assert len(results) == 10
    assert active["max"] <= 5


def test_one_failing_task_is_isolated(monkeypatch):
    def fake_chat(self, model, messages, max_tokens=1024, fallbacks=None):
        prompt = messages[-1]["content"]
        if prompt == "say 7":
            raise RuntimeError("boom")
        if prompt == "say 9":
            return "Error: no NVIDIA model answered (stub=503)"
        self.last_model = "stub-model"
        return "answer"

    agent = _agent(monkeypatch, fake_chat)
    tasks = _tasks(10)
    results = agent.fan_out(tasks, lanes=10)
    summary = jh.JensenHuang.summarize(results)
    assert summary["succeeded"] == 8
    assert summary["failed"] == 2
    assert summary["failed_ids"] == ["task-7", "task-9"]
    by_id = {r["id"]: r for r in results}
    assert by_id["task-7"]["error"].startswith("RuntimeError: boom")
    assert by_id["task-9"]["error"].startswith("Error: no NVIDIA model answered")
    assert by_id["task-0"]["status"] == "ok"


def test_missing_key_records_clean_per_task_errors():
    # Real client, no key resolves on this box: chat() answers with the
    # missing-key error string and makes no network call.
    agent = jh.JensenHuang()
    assert not agent._new_client().is_alive()
    results = agent.fan_out(_tasks(3), lanes=3)
    assert len(results) == 3
    assert all(r["status"] == "error" for r in results)
    assert all("NVIDIA_API_KEY missing" in (r["error"] or "") for r in results)
    summary = jh.JensenHuang.summarize(results)
    assert summary["succeeded"] == 0
    assert summary["failed"] == 3
    assert summary["failed_ids"] == ["task-0", "task-1", "task-2"]


def test_bad_task_dict_does_not_kill_the_batch(monkeypatch):
    def fake_chat(self, model, messages, max_tokens=1024, fallbacks=None):
        return "answer"

    agent = _agent(monkeypatch, fake_chat)
    tasks = [{"id": "good", "prompt": "hi"}, {"id": "bad"}, {"id": "also-good", "prompt": "yo"}]
    results = agent.fan_out(tasks, lanes=3)
    assert [r["status"] for r in results] == ["ok", "error", "ok"]
    assert "bad task" in results[1]["error"]
    assert jh.JensenHuang.summarize(results)["failed_ids"] == ["bad"]


def test_messages_tasks_and_per_task_model(monkeypatch):
    seen = []

    def fake_chat(self, model, messages, max_tokens=1024, fallbacks=None):
        seen.append((model, messages))
        return "answer"

    agent = _agent(monkeypatch, fake_chat)
    results = agent.fan_out([
        {"id": "m", "messages": [{"role": "user", "content": "from messages"}]},
        {"id": "p", "prompt": "from prompt", "model": "some/model"},
    ], lanes=2)
    assert all(r["status"] == "ok" for r in results)
    assert seen[0] == ("auto", [{"role": "user", "content": "from messages"}])
    assert seen[1][0] == "some/model"
    assert seen[1][1] == [{"role": "user", "content": "from prompt"}]


def test_summarize_empty_results():
    assert jh.JensenHuang.summarize([]) == {
        "total": 0,
        "succeeded": 0,
        "failed": 0,
        "per_model": {},
        "total_latency_s": 0.0,
        "mean_latency_s": 0.0,
        "failed_ids": [],
    }


def test_lanes_validation_and_env_override(monkeypatch):
    with pytest.raises(ValueError):
        jh.JensenHuang(lanes=0)
    with pytest.raises(ValueError):
        jh.JensenHuang().fan_out(_tasks(1), lanes=0)
    monkeypatch.setenv("NOUGEN_JENSEN_LANES", "7")
    assert jh.JensenHuang().lanes == 7
    monkeypatch.setenv("NOUGEN_JENSEN_LANES", "not-a-number")
    assert jh.JensenHuang().lanes == jh.DEFAULT_LANES


def test_default_lanes_and_models():
    agent = jh.JensenHuang(api_key="test-key")
    assert agent.lanes == 50
    assert agent.models == VERIFIED_CHAT_MODELS


def test_cli_help_exits_zero():
    with pytest.raises(SystemExit) as excinfo:
        jh.main(["--help"])
    assert excinfo.value.code == 0


def test_cli_writes_results_json(monkeypatch, tmp_path):
    def fake_chat(self, model, messages, max_tokens=1024, fallbacks=None):
        return "answer"

    monkeypatch.setattr(NvidiaNimClient, "chat", fake_chat)
    task_file = tmp_path / "tasks.jsonl"
    task_file.write_text(
        '{"id": "a", "prompt": "one"}\n'
        '{"id": "b", "prompt": "two"}\n'
        'not json at all\n'
        '{"id": "c", "messages": [{"role": "user", "content": "three"}]}\n',
        encoding="utf-8",
    )
    out_file = tmp_path / "results.json"
    assert jh.main(["--tasks", str(task_file), "--lanes", "3", "--out", str(out_file)]) == 0
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 4
    assert payload["summary"]["succeeded"] == 3
    assert payload["summary"]["failed"] == 1
    assert payload["summary"]["failed_ids"] == ["line-3"]
    assert [r["id"] for r in payload["results"]] == ["a", "b", "line-3", "c"]


def test_cli_probe_reports_key_missing(capsys):
    # No key on this box: probe must say so and exit 0 without network.
    assert jh.main(["--probe"]) == 0
    assert "NVIDIA_API_KEY missing" in capsys.readouterr().out
