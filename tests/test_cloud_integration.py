"""Tests for cloud LLM clients and auth logic."""
import json
from unittest.mock import patch, MagicMock
import pytest
from nougen_shards.models_client import (
    OpenAIClient, AnthropicClient, GeminiClient, HuggingFaceClient
)
from nougen_shards import keymaker

@pytest.fixture
def mock_urlopen():
    with patch("urllib.request.urlopen") as mock:
        yield mock

def test_openai_client_chat(mock_urlopen):
    """Test OpenAIClient chat."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "choices": [{"message": {"content": "Hello from OpenAI"}}]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = OpenAIClient(api_key="test-key")
    resp = client.chat("gpt-4o", [{"role": "user", "content": "hi"}])
    assert resp == "Hello from OpenAI"

def test_anthropic_client_chat(mock_urlopen):
    """Test AnthropicClient chat."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "content": [{"text": "Hello from Anthropic"}]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = AnthropicClient(api_key="test-key")
    resp = client.chat("claude-3-5-sonnet-latest", [{"role": "user", "content": "hi"}])
    assert resp == "Hello from Anthropic"

def test_gemini_client_chat(mock_urlopen):
    """Test GeminiClient chat."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "candidates": [{"content": {"parts": [{"text": "Hello from Gemini"}]}}]
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = GeminiClient(api_key="test-key")
    resp = client.chat("gemini-1.5-flash", [{"role": "user", "content": "hi"}])
    assert resp == "Hello from Gemini"

def test_huggingface_client_chat(mock_urlopen):
    """Test HuggingFaceClient chat."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps([
        {"generated_text": "Hello from Hugging Face"}
    ]).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    client = HuggingFaceClient(api_key="test-key")
    resp = client.chat("meta-llama/Llama-3.2-3B-Instruct", [{"role": "user", "content": "hi"}])
    assert resp == "Hello from Hugging Face"

@patch("nougen_shards.keymaker.get_secret")
def test_cloud_clients_no_key(mock_get_secret):
    """Test behavior when no key is found."""
    mock_get_secret.return_value = None
    
    clients = [OpenAIClient(), AnthropicClient(), GeminiClient(), HuggingFaceClient()]
    for client in clients:
        assert client.is_alive() is False
        resp = client.chat("any-model", [])
        assert "Error:" in resp
        assert "not configured" in resp
