"""Tests for models_client.py."""
import json
import socket
from unittest.mock import patch, MagicMock
import urllib.error
import pytest
from nougen_shards.models_client import OllamaClient, LMStudioClient, get_best_available_client

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
    """Test find_best_model_from_list with various scenarios."""
    from nougen_shards.models_client import find_best_model_from_list

    # Scenario 1: Known custom system model (Tier 1: low temp, tight context)
    models = ["gemma4:latest", "dav1d:e2b", "random-model"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "dav1d:e2b"
    assert config.n_ctx == 2048
    assert config.temperature == 0.2

    # Scenario 2: User custom model (not starting with official prefixes) over official default
    models = ["llama3:latest", "my-finetuned-gemma", "gemma4:latest"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "my-finetuned-gemma"
    assert config.n_ctx == 4096
    assert config.temperature == 0.7

    # Scenario 2b: User custom model with dynamic context tag
    models = ["llama3:latest", "my-finetuned-gemma-8k", "gemma4:latest"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "my-finetuned-gemma-8k"
    assert config.n_ctx == 8192
    assert config.temperature == 0.7

    # Scenario 3: Path-based user custom model over default
    models = ["gemma4:e4b", "C:\\models\\custom-brain-v1.gguf", "llama3"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "C:\\models\\custom-brain-v1.gguf"
    assert config.n_ctx == 4096

    # Scenario 4: Official Gemma 4 default over other fallbacks
    models = ["llama3", "gemma4:e4b", "gemma:latest"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "gemma4:e4b"
    assert config.n_ctx == 4096

    # Scenario 5: Fallback to first if all official
    models = ["llama3", "mistral"]
    config = find_best_model_from_list(models)
    assert config is not None
    assert config.model_name == "llama3"
    assert config.n_ctx == 4096

    # Scenario 6: None if empty
    assert find_best_model_from_list([]) is None
