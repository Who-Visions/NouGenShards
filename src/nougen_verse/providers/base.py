"""Optional GENERATE adapter interface.

GENERATE is disabled by default. Nothing in this package calls a network or a
paid model. To use generation you must both set the environment variable
``NOUGEN_VERSE_ENABLE_GENERATE=1`` and register your own provider object with
:func:`register_provider`. The deterministic core (plan, compile, analyze,
score, repair) never imports this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..config import ENV_ENABLE_GENERATE


class GenerationDisabled(RuntimeError):
    """Raised when GENERATE is requested while it is switched off."""


@dataclass
class ProviderResult:
    provider: str
    text: str
    raw: Any = None
    meta: dict = field(default_factory=dict)


@runtime_checkable
class Provider(Protocol):
    name: str

    def generate(self, prompt: Any, **options: Any) -> ProviderResult:  # pragma: no cover - interface
        ...


_REGISTRY: dict[str, Provider] = {}


def register_provider(provider: Provider) -> None:
    if not isinstance(provider, Provider):
        raise TypeError("provider must have a name attribute and a generate(prompt, **options) method")
    _REGISTRY[provider.name] = provider


def unregister_provider(name: str) -> None:
    _REGISTRY.pop(name, None)


def registered_providers() -> list[str]:
    return sorted(_REGISTRY)


def generation_enabled(env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(ENV_ENABLE_GENERATE, "")).strip().lower() in ("1", "true", "yes", "on")


def get_provider(name: str) -> Provider:
    if name not in _REGISTRY:
        raise KeyError(f"no provider named {name!r} is registered; registered: {registered_providers() or 'none'}")
    return _REGISTRY[name]


class EchoProvider:
    """Offline stand-in for tests. It returns bar placeholders, never lyrics."""

    name = "echo"

    def generate(self, prompt: Any, **options: Any) -> ProviderResult:
        packet = getattr(prompt, "constraint_packet", {}) or {}
        lines = [f"(placeholder for bar {o['bar']}: {o['job']})" for o in packet.get("bar_objectives", [])]
        return ProviderResult(self.name, "\n".join(lines), meta={"offline": True})


def generate_verse(blueprint: Any, provider: str, prompt_format: str = "chat", **options: Any) -> dict:
    """Compile a prompt and send it to a registered provider. Off unless explicitly enabled."""
    if not generation_enabled():
        raise GenerationDisabled(
            f"GENERATE is off by default. Set {ENV_ENABLE_GENERATE}=1 and register a provider with register_provider() to use it."
        )
    from ..analyzer import analyze_verse
    from ..compiler import compile_prompt

    prompt = compile_prompt(blueprint, prompt_format)
    result = get_provider(provider).generate(prompt, **options)
    return {"provider": result.provider, "text": result.text, "analysis": analyze_verse(result.text).to_dict(), "meta": result.meta}
