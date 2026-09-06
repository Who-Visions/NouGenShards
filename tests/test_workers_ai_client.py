"""Tests for the Cloudflare Workers AI lane (no network)."""
import io
import json
import re
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nougen_shards import workers_ai_client as wac
from nougen_shards.workers_ai_client import NeuronBudgetGuard, WorkersAIClient, kaedra_cloud_fallback

FAKE_ACCOUNT = "acct-placeholder"
FAKE_TOKEN = "token-placeholder"


@pytest.fixture(name="guard")
def fixture_guard(tmp_path):
    return NeuronBudgetGuard(limit=10000, state_path=tmp_path / "neurons.json")


@pytest.fixture(name="client")
def fixture_client(guard):
    return WorkersAIClient(account_id=FAKE_ACCOUNT, token=FAKE_TOKEN,
                           base_url="https://example.invalid/client/v4", timeout_s=5, guard=guard)


def _fake_urlopen(body: dict):
    mock = MagicMock()
    mock.read.return_value = json.dumps(body).encode()
    ctx = MagicMock()
    ctx.__enter__.return_value = mock
    return ctx


def test_request_shaping_with_tools(client):
    tools = [{"type": "function", "function": {"name": "fleet_whoami", "parameters": {"type": "object", "properties": {}}}}]
    captured = {}

    def fake(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["payload"] = json.loads(req.data.decode())
        return _fake_urlopen({"choices": [{"message": {"role": "assistant", "content": "hi"}}], "usage": {}})

    with patch("urllib.request.urlopen", side_effect=fake):
        out = client.chat(messages=[{"role": "user", "content": "who am I"}], tools=tools,
                          temperature=0.1, max_tokens=64)
    assert captured["url"] == f"https://example.invalid/client/v4/accounts/{FAKE_ACCOUNT}/ai/v1/chat/completions"
    assert captured["auth"] == f"Bearer {FAKE_TOKEN}"
    p = captured["payload"]
    assert p["model"] == client.model and p["tools"] == tools and p["stream"] is False
    assert p["temperature"] == 0.1 and p["max_tokens"] == 64
    assert out["message"]["content"] == "hi" and out["lane"] == "workers-ai" and out["done"] is True


def test_response_normalisation_tool_calls(client):
    raw = {
        "model": "@cf/test",
        "choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "call_1", "type": "function",
                            "function": {"name": "fleet_whoami", "arguments": "{\"verbose\": true}"}}]}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }
    with patch("urllib.request.urlopen", return_value=_fake_urlopen(raw)):
        out = client.chat(messages=[{"role": "user", "content": "x"}], tools=[{"type": "function"}])
    calls = out["message"]["tool_calls"]
    assert calls == [{"function": {"name": "fleet_whoami", "arguments": {"verbose": True}}, "id": "call_1"}]
    assert out["message"]["content"] == "" and out["done_reason"] == "tool_calls"
    assert out["neurons_estimated"] is True
    expected = (100 * 9091 + 20 * 27273) / 1_000_000
    assert out["neurons"] == pytest.approx(expected, abs=1e-3)
    assert client.guard.spent_today() == pytest.approx(expected, abs=1e-3)


def test_http_error_returns_status(client):
    err = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"{\"success\":false}"))
    with patch("urllib.request.urlopen", side_effect=err):
        out = client.chat(messages=[{"role": "user", "content": "x"}])
    assert out["status"] == 403 and out["error"].startswith("HTTP 403")


def test_budget_guard_refuses_over_limit(tmp_path):
    guard = NeuronBudgetGuard(limit=50, state_path=tmp_path / "n.json")
    guard.record(49.5)
    client = WorkersAIClient(account_id=FAKE_ACCOUNT, token=FAKE_TOKEN, guard=guard)
    with patch("urllib.request.urlopen") as mocked:
        out = client.chat(messages=[{"role": "user", "content": "x" * 400}], max_tokens=100)
        mocked.assert_not_called()
    assert out["budget_refused"] is True and "NOUGEN_CF_AI_DAILY_NEURONS" in out["error"]


def test_budget_guard_resets_on_day_change(tmp_path):
    path = tmp_path / "n.json"
    guard = NeuronBudgetGuard(limit=100, state_path=path)
    guard.record(90)
    assert guard.would_exceed(20)
    stale = json.loads(path.read_text())
    stale["day"] = "2000-01-01"
    path.write_text(json.dumps(stale))
    assert guard.spent_today() == 0
    assert not guard.would_exceed(20)
    guard.record(5)
    assert json.loads(path.read_text())["day"] == date.today().isoformat()


def test_env_defaults_logged_fallbacks(monkeypatch):
    for name in (wac.ENV_DAILY_NEURONS, wac.ENV_MODEL, wac.ENV_BASE_URL, wac.ENV_TIMEOUT_S):
        monkeypatch.delenv(name, raising=False)
    guard = NeuronBudgetGuard(state_path=Path("unused.json"))
    assert guard.limit == 10000
    client = WorkersAIClient(account_id=FAKE_ACCOUNT, token=FAKE_TOKEN, guard=guard)
    assert client.model == "@cf/google/gemma-4-26b-a4b-it"
    assert client.base_url.startswith("https://api.cloudflare.com/client/v4")
    monkeypatch.setenv(wac.ENV_DAILY_NEURONS, "123")
    monkeypatch.setenv(wac.ENV_MODEL, "@cf/other")
    assert NeuronBudgetGuard(state_path=Path("unused.json")).limit == 123
    assert WorkersAIClient(account_id=FAKE_ACCOUNT, token=FAKE_TOKEN, guard=guard).model == "@cf/other"


def test_unconfigured_lane_returns_error(monkeypatch, guard):
    for name in (wac.ENV_ACCOUNT_ID, wac.ENV_TOKEN):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(wac.keymaker, "get_secret", lambda key: None)
    client = WorkersAIClient(guard=guard)
    assert not client.is_alive()
    assert client.list_models() == wac.FREE_TOOL_MODELS_SEED
    out = kaedra_cloud_fallback([{"role": "user", "content": "x"}], client=client)
    assert "error" in out and out["lane"] == "workers-ai"


def test_list_models_parses_catalogue(client):
    raw = {"result": [{"name": "@cf/a"}, {"name": "@cf/b"}, {"nope": 1}]}
    with patch("urllib.request.urlopen", return_value=_fake_urlopen(raw)):
        assert client.list_models() == ["@cf/a", "@cf/b"]


def test_no_secret_shaped_literals_in_new_files():
    root = Path(__file__).resolve().parents[1]
    files = [root / "src" / "nougen_shards" / "workers_ai_client.py", Path(__file__),
             root / "wargames" / "cf-workers-ai-lane.md"]
    hex32 = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")
    tokenish = re.compile(r"(?<![A-Za-z0-9_/-])[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_/-])")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not hex32.search(text), f"32-hex literal in {path.name}"
        suspects = [m for m in tokenish.findall(text) if re.search(r"\d", m) and re.search(r"[A-Za-z]", m)]
        assert not suspects, f"token-shaped literal in {path.name}"
        for dash in (chr(0x2014), chr(0x2013)):
            assert dash not in text, f"dash in {path.name}"


def test_registry_lists_workers_ai_as_free():
    root = Path(__file__).resolve().parents[1]
    reg = json.loads((root / "src" / "nougen_shards" / "canon" / "provider_registry.json").read_text(encoding="utf-8"))
    lane = next(p for p in reg["providers"] if p["lane"] == "workers-ai")
    assert lane["cost_class"] == "free" and "tools" in lane["capabilities"]
