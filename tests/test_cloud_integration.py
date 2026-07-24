"""Tests for cloud LLM clients and auth logic."""
import json
import os
import urllib.error
from unittest.mock import patch, MagicMock
import pytest
from nougen_shards.models_client import (
    OpenAIClient, AnthropicClient, GeminiClient, HuggingFaceClient,
    OpenRouterClient, DEFAULT_HTTP_TIMEOUT
)
from nougen_shards import keymaker

# Rule 0.2: the probe key is a test fixture, not a shipped constant.
API_KEY = os.environ.get("NOUGEN_TEST_API_KEY", "test-key-abc123")


@pytest.fixture
def mock_urlopen():
    with patch("urllib.request.urlopen") as mock:
        yield mock


def sent_request(mock):
    """Return the urllib Request object the client actually handed to urlopen."""
    assert mock.call_args is not None, "client never issued an HTTP request"
    args, _kwargs = mock.call_args
    return args[0]


def sent_headers(request):
    """Case-insensitive view of the outbound headers (urllib capitalizes keys)."""
    return {str(k).lower(): v for k, v in request.headers.items()}


def sent_body(request):
    return json.loads(request.data.decode())


def json_response(mock, payload):
    """Wire a decoded-JSON success body onto the patched urlopen context manager."""
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    mock.return_value.__enter__.return_value = response
    return response

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
        assert "Key missing" in resp


# ---------------------------------------------------------------------------
# Outbound-request contract: what actually goes on the wire.
#
# Every client below is exercised through a patched urllib.request.urlopen, so
# the ONLY way a dropped auth header or a wrong endpoint gets caught is by
# inspecting the Request object the client handed to urlopen. Asserting on the
# decoded reply alone is blind to auth (mutation audit: dropping Authorization /
# x-api-key was invisible to the previous suite).
# ---------------------------------------------------------------------------

def test_openai_chat_sends_bearer_authorization(mock_urlopen):
    """OpenAI chat must POST to the completions endpoint with a Bearer key."""
    json_response(mock_urlopen, {"choices": [{"message": {"content": "ok"}}]})

    client = OpenAIClient(api_key=API_KEY)
    messages = [{"role": "user", "content": "hi"}]
    resp = client.chat("gpt-4o", messages)
    assert resp == "ok"

    request = sent_request(mock_urlopen)
    assert request.get_method() == "POST"
    assert request.full_url.startswith("https://")
    assert request.full_url == f"{client.base_url}/chat/completions"

    headers = sent_headers(request)
    assert "authorization" in headers, "Authorization header was not sent"
    assert headers["authorization"] == f"Bearer {API_KEY}"
    assert API_KEY in headers["authorization"]
    assert headers["content-type"] == "application/json"

    body = sent_body(request)
    assert body["model"] == "gpt-4o"
    assert body["messages"] == messages
    assert mock_urlopen.call_args.kwargs.get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_anthropic_chat_sends_x_api_key(mock_urlopen):
    """Anthropic chat must POST to /messages with x-api-key and a version pin."""
    json_response(mock_urlopen, {"content": [{"text": "ok"}]})

    client = AnthropicClient(api_key=API_KEY)
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    resp = client.chat("claude-3-5-sonnet-latest", messages)
    assert resp == "ok"

    request = sent_request(mock_urlopen)
    assert request.get_method() == "POST"
    assert request.full_url.startswith("https://")
    assert request.full_url == f"{client.base_url}/messages"

    headers = sent_headers(request)
    assert "x-api-key" in headers, "x-api-key header was not sent"
    assert headers["x-api-key"] == API_KEY
    # Anthropic authenticates on x-api-key, never on a bearer token.
    assert "authorization" not in headers
    assert headers.get("anthropic-version")
    assert headers["content-type"] == "application/json"

    body = sent_body(request)
    assert body["model"] == "claude-3-5-sonnet-latest"
    assert body["system"] == "sys"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert mock_urlopen.call_args.kwargs.get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_openrouter_chat_sends_bearer_authorization(mock_urlopen):
    """OpenRouter chat must POST with a Bearer key plus attribution headers."""
    json_response(mock_urlopen, {"choices": [{"message": {"content": "ok"}}]})

    client = OpenRouterClient(api_key=API_KEY)
    messages = [{"role": "user", "content": "hi"}]
    resp = client.chat("openrouter/auto", messages)
    assert resp == "ok"

    request = sent_request(mock_urlopen)
    assert request.get_method() == "POST"
    assert request.full_url.startswith("https://")
    assert request.full_url == f"{client.base_url}/chat/completions"
    # OpenRouter must not inherit the parent OpenAI endpoint.
    assert client.base_url != OpenAIClient(api_key=API_KEY).base_url

    headers = sent_headers(request)
    assert "authorization" in headers, "Authorization header was not sent"
    assert headers["authorization"] == f"Bearer {API_KEY}"
    assert headers["content-type"] == "application/json"

    body = sent_body(request)
    assert body["model"] == "openrouter/auto"
    assert body["messages"] == messages
    assert mock_urlopen.call_args.kwargs.get("timeout") == DEFAULT_HTTP_TIMEOUT


def test_huggingface_chat_sends_bearer_authorization(mock_urlopen):
    """Hugging Face inference must carry the Bearer key on the model endpoint."""
    response = MagicMock()
    response.read.return_value = json.dumps([{"generated_text": "ok"}]).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = response

    client = HuggingFaceClient(api_key=API_KEY)
    model = "meta-llama/Llama-3.2-3B-Instruct"
    assert client.chat(model, [{"role": "user", "content": "hi"}]) == "ok"

    request = sent_request(mock_urlopen)
    assert request.get_method() == "POST"
    assert request.full_url == f"{client.base_url}/{model}"
    headers = sent_headers(request)
    assert "authorization" in headers, "Authorization header was not sent"
    assert headers["authorization"] == f"Bearer {API_KEY}"


def test_gemini_chat_sends_goog_api_key(mock_urlopen):
    """Gemini authenticates on x-goog-api-key, and never leaks the key into the URL."""
    json_response(
        mock_urlopen,
        {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
    )

    client = GeminiClient(api_key=API_KEY)
    assert client.chat("gemini-1.5-flash", [{"role": "user", "content": "hi"}]) == "ok"

    request = sent_request(mock_urlopen)
    assert request.get_method() == "POST"
    assert request.full_url == f"{client.base_url}/gemini-1.5-flash:generateContent"
    headers = sent_headers(request)
    assert "x-goog-api-key" in headers, "x-goog-api-key header was not sent"
    assert headers["x-goog-api-key"] == API_KEY
    # Privacy: credentials belong in headers, not query strings.
    assert API_KEY not in request.full_url


@pytest.mark.parametrize(
    "client_factory",
    [
        lambda: OpenAIClient(api_key=API_KEY),
        lambda: AnthropicClient(api_key=API_KEY),
        lambda: OpenRouterClient(api_key=API_KEY),
        lambda: GeminiClient(api_key=API_KEY),
        lambda: HuggingFaceClient(api_key=API_KEY),
    ],
    ids=["openai", "anthropic", "openrouter", "gemini", "huggingface"],
)
def test_http_error_is_surfaced_not_swallowed_as_empty_success(mock_urlopen, client_factory):
    """A 401/500 must come back as an error string, never as an empty success."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="https://example.invalid/v1", code=401, msg="Unauthorized", hdrs=None, fp=None
    )

    client = client_factory()
    resp = client.chat("any-model", [{"role": "user", "content": "hi"}])

    assert resp != "", "API error was swallowed and returned as empty success"
    assert resp.strip(), "API error produced blank output instead of an error"
    assert "Error" in resp, f"error response was not surfaced as an error: {resp!r}"
    assert "401" in resp or "Unauthorized" in resp


@pytest.mark.parametrize(
    "client_factory",
    [
        lambda: OpenAIClient(api_key=API_KEY),
        lambda: AnthropicClient(api_key=API_KEY),
        lambda: OpenRouterClient(api_key=API_KEY),
    ],
    ids=["openai", "anthropic", "openrouter"],
)
def test_transport_error_is_surfaced_not_swallowed(mock_urlopen, client_factory):
    """A dead socket must surface too — no silent empty-string success."""
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")

    resp = client_factory().chat("any-model", [{"role": "user", "content": "hi"}])

    assert resp != ""
    assert "Error" in resp
    assert "connection refused" in resp


def test_openrouter_chat_with_fallback_surfaces_errors(mock_urlopen):
    """chat_with_fallback must not report a failed call as empty content."""
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="https://example.invalid/v1", code=500, msg="Server Error", hdrs=None, fp=None
    )

    result = OpenRouterClient(api_key=API_KEY).chat_with_fallback(
        "openrouter/auto", [{"role": "user", "content": "hi"}], fallback_models=["a/b"]
    )

    assert result["content"] != ""
    assert "Error" in result["content"]
    assert result["model"] == "error"
