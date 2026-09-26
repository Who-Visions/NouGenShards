"""Privacy mode refuses cloud routes structurally; the no-progress breaker
stops a prompt that keeps failing on every lane (openhuman moves, clean-room)."""
import io
import json
import urllib.error

import pytest

from tools import fleet


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("NOUGEN_PRIVACY", raising=False)
    fleet.breaker_reset()
    yield
    fleet.breaker_reset()


def _cfg(tmp_path):
    p = tmp_path / "routes.json"
    p.write_text(json.dumps({"mcpServers": {
        "openrouter-a": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "m1"},
        "hf-space-b": {"type": "openai-compatible", "url": "https://x.hf.space/v1", "model": "m2"},
    }}))
    return str(p)


@pytest.mark.parametrize("url,ok", [
    ("http://whoart.local:11434/v1", True),
    ("http://127.0.0.1:1234/v1", True),
    ("http://192.168.1.5/v1", True),
    ("http://blade1tb:11434/v1", True),
    ("https://openrouter.ai/api/v1", False),
    ("https://x.hf.space/v1", False),
    ("https://8.8.8.8/v1", False),
])
def test_is_private_url(url, ok):
    assert fleet.is_private_url(url) is ok


def test_privacy_mode_drops_cloud_and_vertex_at_load(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_PRIVACY", "1")
    monkeypatch.setattr(fleet, "LOCAL_ROUTES", [{
        "name": "local-ollama-node",
        "url": "http://127.0.0.1:11434/v1",
        "model": "local-model",
        "headers": {},
        "kind": "local",
    }])
    f = fleet.Fleet(_cfg(tmp_path), include_local=True, include_vertex=True)
    assert f.routes and all(fleet.is_private_url(r["url"]) for r in f.routes)


def test_privacy_call_refuses_before_any_network(tmp_path, monkeypatch):
    f = fleet.Fleet(_cfg(tmp_path), include_local=False, include_vertex=False)
    monkeypatch.setenv("NOUGEN_PRIVACY", "1")

    def boom(*a, **k):
        raise AssertionError("network touched")
    monkeypatch.setattr(fleet.urllib.request, "urlopen", boom)
    with pytest.raises(fleet.PrivacyError):
        f._call(f.routes[0], "hi")


def test_breaker_stops_a_repeatedly_failing_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "BREAKER_MAX", 2)
    monkeypatch.setattr(fleet.time, "sleep", lambda s: None)
    f = fleet.Fleet(_cfg(tmp_path), include_local=False, include_vertex=False)
    calls = []

    def fail(route, prompt, **kw):
        calls.append(route["name"])
        raise urllib.error.HTTPError(route["url"], 429, "rate", {}, io.BytesIO(b"rate limited"))
    monkeypatch.setattr(f, "_call", fail)
    for _ in range(2):
        assert f.map(["same"], retries=0)[0][1].startswith("FAILED(HTTPError 429")
    n = len(calls)
    out = f.map(["same"], retries=0)
    assert len(calls) == n, "breaker must stop dispatch"
    assert "breaker" in out[0][1] and "diversify" in out[0][1]
    f.map(["other"], retries=0)
    assert len(calls) == n + 1, "a different prompt is unaffected"


def test_breaker_resets_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "BREAKER_MAX", 2)
    f = fleet.Fleet(_cfg(tmp_path), include_local=False, include_vertex=False)
    state = {"ok": False}
    monkeypatch.setattr(f, "_call", lambda route, prompt, **kw: "fine" if state["ok"] else "")
    f.map(["p"], retries=0)
    state["ok"] = True
    assert f.map(["p"], retries=0)[0][2] == "fine"
    state["ok"] = False
    f.map(["p"], retries=0)
    assert "breaker" not in f.map(["p"], retries=0)[0][1]


def test_consensus_run_is_one_failure_not_one_per_lane(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "BREAKER_MAX", 2)
    f = fleet.Fleet(_cfg(tmp_path), include_local=False, include_vertex=False)
    monkeypatch.setattr(f, "_call", lambda route, prompt, **kw: "")
    out = f.map(["q"] * 5, retries=0)
    assert all("breaker" not in name for _, name, _ in out)
    assert fleet._breaker_open(fleet._prompt_key("q")) is None
