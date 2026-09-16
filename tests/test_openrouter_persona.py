"""Verify OpenRouterClient and model lanes dynamically inject persona.py system prompts."""

from unittest.mock import MagicMock, patch
from nougen_shards.models_client import OpenRouterClient
from nougen_shards.persona import Signals, resolve


def test_openrouter_injects_persona():
    """Verify OpenRouterClient._inject_persona prepends system persona when missing."""
    client = OpenRouterClient(api_key="mock-key")
    messages = [{"role": "user", "content": "Check fleet status and relay open batons."}]
    
    injected = client._inject_persona(messages)
    assert len(injected) == 2
    assert injected[0]["role"] == "system"
    assert "fleet-operator" in injected[0]["content"] or "member" in injected[0]["content"]
    assert injected[1]["role"] == "user"


def test_openrouter_preserves_explicit_system_prompt():
    """Verify OpenRouterClient._inject_persona does not overwrite existing system prompts."""
    client = OpenRouterClient(api_key="mock-key")
    messages = [
        {"role": "system", "content": "Custom explicit system prompt."},
        {"role": "user", "content": "Hello."}
    ]
    
    injected = client._inject_persona(messages)
    assert len(injected) == 2
    assert injected[0]["content"] == "Custom explicit system prompt."
