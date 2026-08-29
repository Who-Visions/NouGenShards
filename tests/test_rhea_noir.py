"""Unit & regression tests for rhea_noir inference routing and agent loop."""
import json
import pytest
import rhea_noir


def test_rhea_status_and_tool_call(monkeypatch):
    """Test successful tool calling loop and response contract."""
    rounds = [
        # First round: model emits a tool call to 'health'
        json.dumps({"tool": "health"}),
        # Second round: model returns the finished answer
        json.dumps({"answer": "Grid is active with verified shards."}),
    ]

    def fake_chat(messages, diagnostics=None):
        return rounds.pop(0), "test:mock-brain"

    monkeypatch.setattr(rhea_noir, "_chat", fake_chat)
    monkeypatch.setattr(rhea_noir, "_run_tool", lambda c: {"total_shards": 840})

    res = rhea_noir.ask("test query")
    assert res["status"] == "ok"
    assert res["brain"] == "test:mock-brain"
    assert "verified shards" in res["answer"]
    assert res["tools_used"] == ["health"]


def test_rhea_rollover_when_primary_free_model_fails(monkeypatch):
    """Test rollover to subsequent free models when primary route 429s/fails."""
    attempts = []

    def fake_openai_call(url, token, model, messages):
        attempts.append(model)
        if model == rhea_noir.DEFAULT_FREE_MODELS[0]:
            import urllib.error
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return json.dumps({"answer": f"Answer from {model}"})

    monkeypatch.setattr(rhea_noir, "_get_secret", lambda name: "fake-key" if name == "OPENROUTER_API_KEY" else None)
    monkeypatch.setattr(rhea_noir, "_try_local", lambda msg: None)  # simulate local offline
    monkeypatch.setattr(rhea_noir, "_openai_call", fake_openai_call)

    res = rhea_noir.ask("hello")
    assert res["status"] == "ok"
    assert len(attempts) >= 2
    assert attempts[0] == rhea_noir.DEFAULT_FREE_MODELS[0]
    assert attempts[1] == rhea_noir.DEFAULT_FREE_MODELS[1]
    assert res["brain"] == f"free:{rhea_noir.DEFAULT_FREE_MODELS[1]}"


def test_rhea_degraded_when_all_routes_fail(monkeypatch):
    """Test graceful degraded output when all local and cloud routes are down."""
    monkeypatch.setattr(rhea_noir, "_try_local", lambda msg: None)
    monkeypatch.setattr(rhea_noir, "_get_secret", lambda name: None)

    res = rhea_noir.ask("status check")
    assert res["status"] == "degraded"
    assert res["brain"] == "none"
    assert "unavailable" in res["answer"]
    assert isinstance(res.get("diagnostics"), dict)


def test_free_model_ids_are_completion_tested_shape():
    """Guard the rollover list against retired ids creeping back in.

    Five of the seven ids this list once held returned HTTP 404 on
    2026-08-29 — a rollover chain of one working model wearing a costume.
    """
    assert len(rhea_noir.DEFAULT_FREE_MODELS) >= 5
    assert len(set(rhea_noir.DEFAULT_FREE_MODELS)) == len(rhea_noir.DEFAULT_FREE_MODELS)
    for mid in rhea_noir.DEFAULT_FREE_MODELS:
        assert mid.endswith(":free"), mid
        assert "/" in mid, mid
    retired = {
        "openai/gpt-oss-20b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
        "mistralai/mistral-small-24b-instruct-2501:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
    }
    assert not retired & set(rhea_noir.DEFAULT_FREE_MODELS)


def test_ollama_cloud_lane_catches_free_and_kimi_outage(monkeypatch):
    """The 13 healthy Ollama Cloud routes must be reachable as a lane."""
    monkeypatch.setattr(rhea_noir, "_try_local", lambda msg: None)
    monkeypatch.setattr(rhea_noir, "_try_free", lambda msg, diagnostics=None: None)
    monkeypatch.setattr(rhea_noir, "_try_kimi", lambda msg, diagnostics=None: None)
    monkeypatch.setattr(
        rhea_noir, "_get_secret",
        lambda name: "k1,k2" if name == "NOUGEN_OLLAMA_CLOUD_KEYS" else None)

    seen = []

    def fake_openai_call(url, token, model, messages):
        seen.append(token)
        if token == "k1":
            import urllib.error
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return json.dumps({"answer": "cloud lane answered"})

    monkeypatch.setattr(rhea_noir, "_openai_call", fake_openai_call)

    res = rhea_noir.ask("status check")
    assert res["status"] == "ok"
    assert res["brain"].startswith("ollama-cloud:")
    assert seen == ["k1", "k2"], "an exhausted key must roll to the next"


def test_all_routes_down_error_names_each_lane(monkeypatch):
    """'all down' with no per-route detail is what made the outage opaque."""
    monkeypatch.setattr(rhea_noir, "_try_local", lambda msg: None)
    monkeypatch.setattr(rhea_noir, "_get_secret", lambda name: None)

    with pytest.raises(RuntimeError) as exc:
        rhea_noir._chat([{"role": "user", "content": "hi"}], {})
    msg = str(exc.value)
    assert "ollama-cloud" in msg
    assert "openrouter" in msg or "kimi" in msg, msg
