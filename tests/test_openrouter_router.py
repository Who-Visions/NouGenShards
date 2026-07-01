"""
Unit tests for OpenRouter production router.
"""
from unittest.mock import MagicMock, patch
from nougen_shards.router import RouterConfig, build_cache_friendly_messages, make_session_id
from nougen_shards.models_client import OpenRouterClient

def test_router_config_defaults():
    config = RouterConfig()
    assert config.primary_model == "openrouter/auto"
    assert "anthropic/claude-3.5-sonnet" in config.fallback_models
    assert config.enable_response_healing is True

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
    mock_res.read.return_value = b'{"choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}], "model": "anthropic/claude-3.5-sonnet", "usage": {"total_tokens": 10}}'
    mock_res.__enter__.return_value = mock_res
    mock_urlopen.return_value = mock_res
    
    client = OpenRouterClient()
    res = client.chat_with_fallback("openrouter/auto", [{"role": "user", "content": "Hi"}])
    
    assert res["content"] == "Hello"
    assert res["model"] == "anthropic/claude-3.5-sonnet"
    assert res["usage"]["total_tokens"] == 10
    
    # Verify call
    args, kwargs = mock_urlopen.call_args
    req = args[0]
    import json
    body = json.loads(req.data.decode())
    assert body["model"] == "openrouter/auto"
    assert "models" in body
    assert len(body["models"]) > 0
