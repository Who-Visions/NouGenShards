"""
Unit tests for OpenRouter production router.
"""
import json
import os
import pytest
from unittest.mock import MagicMock, patch
from nougen_shards.router import RouterConfig, build_cache_friendly_messages, make_session_id
from nougen_shards.models_client import OpenRouterClient

# Rule 0.2: fixture data, resolved from env with a logged-fallback constant, so
# a vendor rename is a one-line env change rather than a suite-wide edit. The
# value is only ever an *input* / an echo of the mocked upstream reply — never a
# vendor fact this suite claims to be true.
SERVED_MODEL = os.environ.get("NOUGEN_TEST_SERVED_MODEL", "vendor-a/served-model")


def test_router_config_defaults():
    """Rule 0.2: assert the SHAPE of the routing defaults, not pinned vendor slugs.

    Vendor model ids drift (a 3.5 becomes a 4.x); a test that pins them starts
    failing for a rename instead of for a regression. What must hold is the
    contract: a provider-qualified primary, a non-empty distinct fallback chain
    that does not merely repeat the primary, and healing on by default.
    """
    config = RouterConfig()

    assert isinstance(config.primary_model, str) and config.primary_model
    # Every OpenRouter id is provider-qualified ("<provider>/<model>").
    provider, _, name = config.primary_model.partition("/")
    assert provider and name, f"primary_model is not provider-qualified: {config.primary_model}"

    assert isinstance(config.fallback_models, list)
    assert len(config.fallback_models) > 1, "a single-entry chain is not a fallback chain"
    assert len(set(config.fallback_models)) == len(config.fallback_models), "duplicate fallbacks"
    for candidate in config.fallback_models:
        candidate_provider, _, candidate_name = candidate.partition("/")
        assert candidate_provider and candidate_name, f"unqualified fallback: {candidate}"
    assert config.primary_model not in config.fallback_models
    # More than one vendor, or the "fallback" cannot survive a vendor outage.
    assert len({m.split("/")[0] for m in config.fallback_models}) > 1

    assert config.enable_response_healing is True
    # Defaults must not silently pin sampling; callers own those knobs.
    assert config.temperature is None
    assert config.max_tokens is None
    assert config.stream is False


def test_router_config_defaults_are_isolated_per_instance():
    """A mutable default shared across configs would cross-contaminate routes."""
    first = RouterConfig()
    second = RouterConfig()
    assert first.fallback_models == second.fallback_models
    first.fallback_models.append("mutated/model")
    assert "mutated/model" not in RouterConfig().fallback_models
    assert "mutated/model" not in second.fallback_models

def test_cache_friendly_messages():
    sys_prompt = "Permanent System Prompt"
    task_msgs = [{"role": "user", "content": "Task message"}]
    messages = build_cache_friendly_messages(sys_prompt, task_msgs)
    
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == sys_prompt
    assert messages[1]["content"] == "Task message"

def test_make_session_id():
    sid = make_session_id("project-x", "agent-y")
    assert sid == "nougen:project-x:agent-y"
    
    sid_with_thread = make_session_id("project-x", "agent-y", "thread-z")
    assert sid_with_thread.startswith("nougen:project-x:agent-y:")
    assert len(sid_with_thread) == len("nougen:project-x:agent-y:") + 8

@patch('urllib.request.urlopen')
@patch('nougen_shards.keymaker.get_secret', return_value="fake-key")
def test_openrouter_chat_with_fallback(mock_get_secret, mock_urlopen):
    # Mock response
    mock_res = MagicMock()
    mock_res.read.return_value = json.dumps({
        "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
        "model": SERVED_MODEL,
        "usage": {"total_tokens": 10},
    }).encode()
    mock_res.__enter__.return_value = mock_res
    mock_urlopen.return_value = mock_res
    
    client = OpenRouterClient()
    primary = RouterConfig().primary_model
    res = client.chat_with_fallback(primary, [{"role": "user", "content": "Hi"}])

    assert res["content"] == "Hello"
    # The routed model is whatever the upstream reports, not the requested one.
    assert res["model"] == SERVED_MODEL
    assert res["model"] != primary
    assert res["usage"]["total_tokens"] == 10

    # Verify call
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    body = json.loads(req.data.decode())
    assert body["model"] == primary
    assert "models" in body
    assert len(body["models"]) > 0

    # Outbound auth contract: without this the key can be dropped silently.
    assert req.get_method() == "POST"
    assert req.full_url == f"{client.base_url}/chat/completions"
    headers = {str(k).lower(): v for k, v in req.headers.items()}
    assert "authorization" in headers, "Authorization header was not sent"
    assert headers["authorization"] == "Bearer fake-key"


@patch('urllib.request.urlopen')
@patch('nougen_shards.keymaker.get_secret', return_value="fake-key")
def test_lane_calls_are_timeout_bounded(mock_get_secret, mock_urlopen):
    """Hardening: every network lane call must pass a finite timeout so a
    hung/unreachable upstream fails over instead of blocking the router."""
    from nougen_shards.models_client import DEFAULT_HTTP_TIMEOUT

    mock_res = MagicMock()
    mock_res.read.return_value = b'{"choices": [{"message": {"content": "ok"}}], "model": "m"}'
    mock_res.__enter__.return_value = mock_res
    mock_urlopen.return_value = mock_res

    client = OpenRouterClient()
    client.chat_with_fallback("openrouter/auto", [{"role": "user", "content": "Hi"}])

    _args, kwargs = mock_urlopen.call_args
    assert kwargs.get("timeout") == DEFAULT_HTTP_TIMEOUT
    assert DEFAULT_HTTP_TIMEOUT and DEFAULT_HTTP_TIMEOUT > 0
