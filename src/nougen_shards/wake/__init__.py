"""NouGen Wake Fabric Module."""
from .adapters import (
    ProviderAdapter,
    ClaudeAdapter,
    AntigravityAdapter,
    CodexAdapter,
    OllamaAdapter,
    get_adapter,
    list_adapters,
)
from .manager import WakeManager, WakeDoctorReport
from .quota import QuotaWakeParser, NouGenWakeEngine

__all__ = [
    "ProviderAdapter",
    "ClaudeAdapter",
    "AntigravityAdapter",
    "CodexAdapter",
    "OllamaAdapter",
    "get_adapter",
    "list_adapters",
    "WakeManager",
    "WakeDoctorReport",
    "QuotaWakeParser",
    "NouGenWakeEngine",
]
