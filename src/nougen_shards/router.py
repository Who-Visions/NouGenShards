"""
OpenRouter Production Router for NouGenShards.
Handles model fallback, session sticky routing, and prompt caching.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import hashlib

@dataclass
class RouterConfig:
    """Configuration for an OpenRouter request."""
    primary_model: str = "openrouter/auto"
    fallback_models: List[str] = field(default_factory=lambda: [
        "anthropic/claude-3.5-sonnet",
        "google/gemini-2.0-flash-001",
        "deepseek/deepseek-chat",
        "openai/gpt-4o-mini"
    ])
    session_id: Optional[str] = None
    enable_response_healing: bool = True
    structured: bool = False
    json_schema: Optional[dict] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    extra_body: dict = field(default_factory=dict)

from .hooks import pre_tool_use_hook

def build_cache_friendly_messages(system_prompt: str, task_messages: List[dict]) -> List[dict]:
    """
    Module 19: Stabilize Reasoning.
    Constructs a message list optimized for prompt caching.
    Ensures stable prefix (System prompt) is at the front.
    Applies Play 2: Pointer Compaction via Reversed Hooks.
    """
    messages = []
    # 1. Permanent System Instruction (The Anchor)
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    # 2. Append Task-Specific Messages
    messages.extend(task_messages)
    
    # 3. Apply Reversed Hooks for Pointer Compaction (Play 2)
    return pre_tool_use_hook(messages)

def make_session_id(project: str, agent: str, thread: Optional[str] = None) -> str:
    """
    Generates a stable session_id for sticky provider routing.
    Format: nougen:{project}:{agent}:{thread_hash}
    """
    base = f"nougen:{project}:{agent}"
    if thread:
        thread_hash = hashlib.sha256(thread.encode()).hexdigest()[:8]
        return f"{base}:{thread_hash}"
    return base
