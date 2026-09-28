"""Optional provider adapters. GENERATE is disabled by default; see base.py."""

from .base import (
    EchoProvider,
    GenerationDisabled,
    Provider,
    ProviderResult,
    generate_verse,
    generation_enabled,
    get_provider,
    register_provider,
    registered_providers,
    unregister_provider,
)

__all__ = [
    "EchoProvider", "GenerationDisabled", "Provider", "ProviderResult", "generate_verse", "generation_enabled",
    "get_provider", "register_provider", "registered_providers", "unregister_provider",
]
