"""Tests for models_client.py."""
import json
import os
import socket
from unittest.mock import patch, MagicMock
import urllib.error
import pytest
from nougen_shards import models_client
from nougen_shards.models_client import (
    OllamaClient, LMStudioClient, ModelBudgetConfig, get_best_available_client,
    OpenAIClient
)

# Rule 0.2: the budget baseline is read from the dataclass the code itself uses,
# so a retune of the default window/temperature is asserted against its own
# source rather than against magic numbers copied into the test.
_DEFAULT_BUDGET = ModelBudgetConfig(model_name="probe")
DEFAULT_N_CTX = _DEFAULT_BUDGET.n_ctx
DEFAULT_TEMPERATURE = _DEFAULT_BUDGET.temperature

# Vendor tags are fixture INPUTS (env-overridable), not vendor facts this suite
# asserts to be true; a roster rename is a one-line env change.
SYSTEM_TAG_MODELS = tuple(
    tag.strip()
    for tag in os.environ.get(
        "NOUGEN_TEST_SYSTEM_MODELS", "dav1d:e2b,sol-ai:e2b,griot:e2b"
    ).split(",")
    if tag.strip()
)
SYSTEM_TAG_MODEL = SYSTEM_TAG_MODELS[0]
OFFICIAL_DEFAULT_MODEL = os.environ.get("NOUGEN_TEST_DEFAULT_MODEL", "gemma4:e4b")
OFFICIAL_LATEST_MODEL = os.environ.get("NOUGEN_TEST_LATEST_MODEL", "gemma4:latest")

@pytest.fixture(name="mock_urlopen")
def fixture_mock_urlopen():
    """Mock urllib.request.urlopen."""
    with patch("urllib.request.urlopen") as mock:
        yield mock

def test_ollama_is_alive(mock_urlopen):
    """Test OllamaClient.is_alive."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OllamaClient()
    assert client.is_alive() is True

    mock_urlopen.side_effect = ConnectionRefusedError
    assert client.is_alive() is False

def test_ollama_list_models(mock_urlopen):
    """Test OllamaClient.list_models."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_data = json.dumps({"models": [{"name": "mdl1"}, {"name": "mdl2"}]}).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OllamaClient()
    models = client.list_models()
    assert models == ["mdl1", "mdl2"]

def test_ollama_chat_no_stream(mock_urlopen):
    """Test OllamaClient.chat without streaming."""
    mock_response = MagicMock()
    mock_data = json.dumps({"message": {"content": "hello"}}).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OllamaClient()
    resp = client.chat("mdl", [{"role": "user", "content": "hi"}], stream=False)
    assert resp == "hello"

def test_ollama_chat_stream(mock_urlopen):
    """Test OllamaClient.chat with streaming."""
    lines = [
        json.dumps({"message": {"content": "he"}}).encode("utf-8"),
        json.dumps({"message": {"content": "llo"}}).encode("utf-8")
    ]
    mock_response = MagicMock()
    mock_response.__iter__.return_value = lines
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OllamaClient()
    resp = client.chat("mdl", [{"role": "user", "content": "hi"}], stream=True)
    assert resp == "hello"

def test_ollama_chat_error(mock_urlopen):
    """Test OllamaClient.chat with error."""
    mock_urlopen.side_effect = urllib.error.URLError("failed")
    client = OllamaClient()
    resp = client.chat("mdl", [], stream=False)
    assert "Error" in resp

def test_ollama_find_best_edge_model(mock_urlopen):
    """Test OllamaClient.find_best_edge_model."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_data = json.dumps({
        "models": [{"name": "llama3"}, {"name": "dav1d:e2b"}]
    }).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OllamaClient()
    config = client.find_best_edge_model()
    assert config is not None
    assert config.model_name == "dav1d:e2b"

def test_ollama_pull_model(mock_urlopen):
    """Test OllamaClient.pull_model."""
    lines = [
        json.dumps({"status": "downloading", "completed": 50, "total": 100}).encode("utf-8"),
        json.dumps({"status": "success"}).encode("utf-8")
    ]
    mock_response = MagicMock()
    mock_response.__iter__.return_value = lines
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OllamaClient()
    assert client.pull_model("mdl") is True

def test_lmstudio_is_alive(mock_urlopen):
    """Test LMStudioClient.is_alive."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = LMStudioClient()
    assert client.is_alive() is True

def test_lmstudio_list_models(mock_urlopen):
    """Test LMStudioClient.list_models."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_data = json.dumps({"data": [{"id": "mdl1"}]}).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = LMStudioClient()
    assert client.list_models() == ["mdl1"]

def test_lmstudio_chat_no_stream(mock_urlopen):
    """Test LMStudioClient.chat without streaming."""
    mock_response = MagicMock()
    mock_data = json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = LMStudioClient()
    assert client.chat("mdl", [], stream=False) == "hi"

def test_lmstudio_chat_stream(mock_urlopen):
    """Test LMStudioClient.chat with streaming."""
    lines = [
        b"data: " + json.dumps({"choices": [{"delta": {"content": "h"}}]}).encode("utf-8"),
        b"data: " + json.dumps({"choices": [{"delta": {"content": "i"}}]}).encode("utf-8"),
        b"data: [DONE]"
    ]
    mock_response = MagicMock()
    mock_response.__iter__.return_value = lines
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = LMStudioClient()
    assert client.chat("mdl", [], stream=True) == "hi"

def test_get_best_available_client():
    """Test get_best_available_client."""
    with patch("nougen_shards.models_client.OllamaClient.is_alive", return_value=True):
        client = get_best_available_client()
        assert isinstance(client, OllamaClient)

    with patch("nougen_shards.models_client.OllamaClient.is_alive", return_value=False):
        with patch("nougen_shards.models_client.LMStudioClient.is_alive", return_value=True):
            client = get_best_available_client()
            assert isinstance(client, LMStudioClient)

def test_ollama_pull_model_fail(mock_urlopen):
    """Test OllamaClient.pull_model failure."""
    mock_urlopen.side_effect = urllib.error.URLError("fail")
    client = OllamaClient()
    assert client.pull_model("mdl") is False

def test_lmstudio_find_best_edge_model(mock_urlopen):
    """Test LMStudioClient.find_best_edge_model."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_data = json.dumps({"data": [{"id": "path/to/model-2b-q4"}]}).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = LMStudioClient()
    config = client.find_best_edge_model()
    assert config is not None
    assert config.model_name == "path/to/model-2b-q4"

def test_ollama_list_models_empty(mock_urlopen):
    """Test OllamaClient.list_models with empty response."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_response.read.return_value = b"{}"
    mock_urlopen.return_value.__enter__.return_value = mock_response
    client = OllamaClient()
    assert client.list_models() == []

def test_ollama_find_best_edge_model_no_pref(mock_urlopen):
    """Test OllamaClient.find_best_edge_model when no preference matches."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_data = json.dumps({"models": [{"name": "random"}]}).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response
    client = OllamaClient()
    config = client.find_best_edge_model()
    assert config is not None
    assert config.model_name == "random"

def test_ollama_find_best_edge_model_none(mock_urlopen):
    """Test OllamaClient.find_best_edge_model when no models exist."""
    mock_urlopen.return_value.__enter__.return_value.read.return_value = b'{"models": []}'
    mock_urlopen.return_value.__enter__.return_value.getcode.return_value = 200
    client = OllamaClient()
    assert client.find_best_edge_model() is None

def test_lm_studio_chat_error(mock_urlopen):
    """Test LMStudioClient.chat error."""
    mock_urlopen.side_effect = socket.timeout()
    client = LMStudioClient()
    assert "Error" in client.chat("mdl", [])

def test_lm_studio_list_models_error(mock_urlopen):
    """Test LMStudioClient.list_models error."""
    mock_urlopen.side_effect = urllib.error.URLError("fail")
    client = LMStudioClient()
    assert client.list_models() == []

def test_find_best_model_from_list():
    """Test find_best_model_from_list with various scenarios.

    Rule 0.2: budgets are asserted RELATIVE to ``ModelBudgetConfig``'s own
    defaults rather than against pinned magic numbers, and the vendor tags are
    named fixtures resolved from env. A retune of the default budget then shows
    up as a real signal instead of as five unrelated literal failures.
    """
    from nougen_shards.models_client import find_best_model_from_list

    # Scenario 1: Known custom system model (Tier 1: low temp, tight context)
    models = [OFFICIAL_LATEST_MODEL, SYSTEM_TAG_MODEL, "random-model"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == SYSTEM_TAG_MODEL
    # Tier 1 is deliberately tighter than the module default budget.
    assert config.n_ctx == DEFAULT_N_CTX // 2
    assert config.n_ctx < DEFAULT_N_CTX
    assert 0 < config.temperature < DEFAULT_TEMPERATURE

    # Every known system tag must share that one tier-1 budget: a per-tag drift
    # (one tag quietly retuned) fails here rather than passing unnoticed.
    tier_one = config
    for tag in SYSTEM_TAG_MODELS:
        tagged = find_best_model_from_list([OFFICIAL_LATEST_MODEL, tag])
        assert tagged is not None
        assert tagged.model_name == tag
        assert tagged.n_ctx == tier_one.n_ctx
        assert tagged.temperature == tier_one.temperature

    # Scenario 2: User custom model (not starting with official prefixes) over official default
    models = ["llama3:latest", "my-finetuned-gemma", OFFICIAL_LATEST_MODEL]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "my-finetuned-gemma"
    assert config.n_ctx == DEFAULT_N_CTX
    assert config.temperature == DEFAULT_TEMPERATURE

    # Scenario 2b: User custom model with dynamic context tag
    models = ["llama3:latest", "my-finetuned-gemma-8k", OFFICIAL_LATEST_MODEL]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "my-finetuned-gemma-8k"
    # An 8k tag doubles the default window; it must not silently stay default.
    assert config.n_ctx == DEFAULT_N_CTX * 2
    assert config.n_ctx > DEFAULT_N_CTX
    assert config.temperature == DEFAULT_TEMPERATURE

    # Scenario 2c: a 2k tag narrows it symmetrically.
    config = find_best_model_from_list(["my-finetuned-gemma-2k"])
    assert config is not None
    assert config.n_ctx == DEFAULT_N_CTX // 2
    assert config.n_ctx < DEFAULT_N_CTX

    # Scenario 3: Path-based user custom model over default
    models = [OFFICIAL_DEFAULT_MODEL, "C:\\models\\custom-brain-v1.gguf", "llama3"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "C:\\models\\custom-brain-v1.gguf"
    assert config.n_ctx == DEFAULT_N_CTX

    # Scenario 4: Official Gemma 4 default over other fallbacks
    models = ["llama3", OFFICIAL_DEFAULT_MODEL, "gemma:latest"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == OFFICIAL_DEFAULT_MODEL
    assert config.n_ctx == DEFAULT_N_CTX
    assert config.temperature == DEFAULT_TEMPERATURE

    # Scenario 5: Fallback to first if all official
    models = ["llama3", "mistral"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "llama3"
    assert config.n_ctx == DEFAULT_N_CTX

    # Scenario 6: None if empty
    assert find_best_model_from_list([]) is None


def test_openai_batch_embed(mock_urlopen):
    """Test OpenAIClient.batch_embed."""
    from nougen_shards.models_client import OpenAIClient
    mock_response = MagicMock()
    mock_data = json.dumps({
        "data": [
            {"index": 0, "embedding": [0.1, 0.2]},
            {"index": 1, "embedding": [0.3, 0.4]}
        ]
    }).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OpenAIClient(api_key="test_key")
    res = client.batch_embed("text-embedding-3-small", ["hello", "world"])
    assert res == [[0.1, 0.2], [0.3, 0.4]]


def test_gemini_batch_embed(mock_urlopen):
    """Test GeminiClient.batch_embed."""
    from nougen_shards.models_client import GeminiClient
    mock_response = MagicMock()
    mock_data = json.dumps({
        "embeddings": [
            {"values": [0.5, 0.6]},
            {"values": [0.7, 0.8]}
        ]
    }).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = GeminiClient(api_key="test_key")
    res = client.batch_embed("text-embedding-004", ["hello", "world"])
    assert res == [[0.5, 0.6], [0.7, 0.8]]


def test_ollama_batch_embed(mock_urlopen):
    """Test OllamaClient.batch_embed."""
    mock_response = MagicMock()
    mock_data = json.dumps({
        "embeddings": [
            [0.11, 0.12],
            [0.13, 0.14]
        ]
    }).encode("utf-8")
    mock_response.read.return_value = mock_data
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OllamaClient()
    res = client.batch_embed("nomic-embed-text", ["hello", "world"])
    assert res == [[0.11, 0.12], [0.13, 0.14]]


def test_ollama_batch_embed_fallback(mock_urlopen):
    """Test OllamaClient.batch_embed falling back to sequential embed."""
    # First call to /api/embed raises an error (e.g. 404 or connection refused)
    # Subsequent calls to /api/embeddings succeed
    mock_response1 = MagicMock()
    mock_response1.read.return_value = json.dumps({"embedding": [0.15, 0.16]}).encode("utf-8")
    
    mock_response2 = MagicMock()
    mock_response2.read.return_value = json.dumps({"embedding": [0.17, 0.18]}).encode("utf-8")

    mock_urlopen.side_effect = [
        urllib.error.URLError("Not Found"), # /api/embed
        MagicMock(**{"__enter__.return_value": mock_response1}), # first /api/embeddings
        MagicMock(**{"__enter__.return_value": mock_response2})  # second /api/embeddings
    ]

    client = OllamaClient()
    res = client.batch_embed("nomic-embed-text", ["hello", "world"])
    assert res == [[0.15, 0.16], [0.17, 0.18]]


# --- OpenAI model roster discovery (Rule 0.2: probe, don't assume) ------------
# Never a live call: every test below patches urllib.request.urlopen. The key is
# a fixture string, not a credential.
FAKE_OPENAI_KEY = "sk-test-fixture-not-a-real-key"


@pytest.fixture(name="clean_roster_cache")
def fixture_clean_roster_cache(monkeypatch):
    """Isolate the process-wide roster cache and its env knobs per test."""
    monkeypatch.delenv(models_client.MODEL_ROSTER_TTL_ENV, raising=False)
    monkeypatch.delenv(models_client.MODEL_ROSTER_TIMEOUT_ENV, raising=False)
    monkeypatch.delenv(OpenAIClient.MODELS_ENV_VAR, raising=False)
    monkeypatch.setattr(models_client, "_MODEL_ROSTER_CACHE", {})
    yield models_client._MODEL_ROSTER_CACHE


def _json_response(payload):
    """Build a urlopen context-manager double returning `payload` as JSON."""
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    ctx = MagicMock()
    ctx.__enter__.return_value = response
    return ctx


def test_openai_list_models_probes_the_live_endpoint(mock_urlopen, clean_roster_cache):
    """The roster must come from GET /v1/models, with bearer auth on the right URL."""
    probed = ["gpt-probe-alpha", "gpt-probe-beta"]
    mock_urlopen.return_value = _json_response(
        {"data": [{"id": mid} for mid in probed]}
    )

    client = OpenAIClient(api_key=FAKE_OPENAI_KEY)
    assert client.list_models() == probed

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == f"{client.base_url}/models"
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == f"Bearer {FAKE_OPENAI_KEY}"


def test_openai_list_models_ignores_ids_missing_from_the_payload(
    mock_urlopen, clean_roster_cache
):
    """Malformed catalogue entries are dropped, not surfaced as empty model IDs."""
    mock_urlopen.return_value = _json_response(
        {"data": [{"id": "gpt-probe-alpha"}, {"object": "model"}, {"id": ""}]}
    )
    assert OpenAIClient(api_key=FAKE_OPENAI_KEY).list_models() == ["gpt-probe-alpha"]


def test_openai_list_models_caches_within_ttl_then_refreshes(
    mock_urlopen, clean_roster_cache
):
    """The common path must not re-probe on every call, and refresh must force one."""
    mock_urlopen.side_effect = [
        _json_response({"data": [{"id": "gpt-probe-first"}]}),
        _json_response({"data": [{"id": "gpt-probe-second"}]}),
    ]
    client = OpenAIClient(api_key=FAKE_OPENAI_KEY)

    assert client.list_models() == ["gpt-probe-first"]
    assert client.list_models() == ["gpt-probe-first"]
    assert mock_urlopen.call_count == 1, "cached roster still hit the network"

    assert client.list_models(refresh=True) == ["gpt-probe-second"]
    assert mock_urlopen.call_count == 2


def test_openai_roster_ttl_is_env_configurable(mock_urlopen, clean_roster_cache, monkeypatch):
    """A zero TTL from the environment must expire the cache immediately."""
    monkeypatch.setenv(models_client.MODEL_ROSTER_TTL_ENV, "0")
    mock_urlopen.side_effect = [
        _json_response({"data": [{"id": "gpt-probe-first"}]}),
        _json_response({"data": [{"id": "gpt-probe-second"}]}),
    ]
    client = OpenAIClient(api_key=FAKE_OPENAI_KEY)

    assert client.list_models() == ["gpt-probe-first"]
    assert client.list_models() == ["gpt-probe-second"]
    assert mock_urlopen.call_count == 2


def test_openai_roster_timeout_is_env_configurable(mock_urlopen, clean_roster_cache, monkeypatch):
    """The probe's socket bound comes from the environment, not a magic number."""
    monkeypatch.setenv(models_client.MODEL_ROSTER_TIMEOUT_ENV, "3")
    mock_urlopen.return_value = _json_response({"data": [{"id": "gpt-probe-alpha"}]})

    OpenAIClient(api_key=FAKE_OPENAI_KEY).list_models()
    assert mock_urlopen.call_args.kwargs["timeout"] == 3

    # And the shipped default applies when the env knob is absent.
    monkeypatch.delenv(models_client.MODEL_ROSTER_TIMEOUT_ENV)
    OpenAIClient(api_key=FAKE_OPENAI_KEY).list_models(refresh=True)
    assert (
        mock_urlopen.call_args.kwargs["timeout"]
        == models_client.DEFAULT_MODEL_ROSTER_TIMEOUT
    )


def test_openai_env_override_pins_the_roster_without_probing(
    mock_urlopen, clean_roster_cache, monkeypatch
):
    """An explicit operator override wins over the probe (env -> config -> probe)."""
    monkeypatch.setenv(OpenAIClient.MODELS_ENV_VAR, "pinned-a, pinned-b")
    assert OpenAIClient(api_key=FAKE_OPENAI_KEY).list_models() == ["pinned-a", "pinned-b"]
    assert mock_urlopen.call_count == 0


def test_openai_list_models_falls_back_and_logs_when_the_probe_fails(
    mock_urlopen, clean_roster_cache, capsys
):
    """A failed probe returns the static seed AND says so on stderr."""
    mock_urlopen.side_effect = urllib.error.URLError("offline")

    models = OpenAIClient(api_key=FAKE_OPENAI_KEY).list_models()
    assert models == models_client.OPENAI_MODEL_SEED
    assert models is not models_client.OPENAI_MODEL_SEED, "seed handed out by reference"

    stderr = capsys.readouterr().err
    assert "Live model discovery failed" in stderr
    assert "falling back to static roster" in stderr
    assert "offline" in stderr
    assert FAKE_OPENAI_KEY not in stderr, "the API key leaked into the log line"


def test_openai_list_models_falls_back_and_logs_when_the_roster_is_empty(
    mock_urlopen, clean_roster_cache, capsys
):
    """A 200 with no models is a failed discovery, not an empty live roster."""
    mock_urlopen.return_value = _json_response({"data": []})

    assert OpenAIClient(api_key=FAKE_OPENAI_KEY).list_models() == models_client.OPENAI_MODEL_SEED
    assert "falling back to static roster" in capsys.readouterr().err
    assert clean_roster_cache == {}, "a failed discovery must not populate the cache"


def test_openai_list_models_falls_back_and_logs_without_a_key(
    mock_urlopen, clean_roster_cache, capsys
):
    """No key means no probe at all — fall back, log the reason, touch no socket."""
    assert OpenAIClient(api_key="").list_models() == models_client.OPENAI_MODEL_SEED
    assert mock_urlopen.call_count == 0
    assert "no API key configured" in capsys.readouterr().err
