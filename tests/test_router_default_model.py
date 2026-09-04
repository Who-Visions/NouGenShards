"""The router's default model must be resolvable without a code edit.

It was hardcoded to "openrouter/auto" in five places — two call sites, two
argparse defaults, and the string `router doctor` printed. `doctor` therefore
reported the literal rather than what a call would actually use, so a stale
default could survive being explicitly checked.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nougen_shards import cli  # noqa: E402


def test_env_selects_the_model(monkeypatch):
    monkeypatch.setenv("NOUGEN_ROUTER_MODEL", "openai/gpt-5.6-luna")
    assert cli.resolve_router_model() == "openai/gpt-5.6-luna"


def test_fallback_is_unchanged(monkeypatch):
    monkeypatch.delenv("NOUGEN_ROUTER_MODEL", raising=False)
    assert cli.resolve_router_model() == "openrouter/auto"


def test_blank_env_is_not_a_model(monkeypatch):
    """An empty or whitespace var is an unset var, not a request for ''."""
    monkeypatch.setenv("NOUGEN_ROUTER_MODEL", "   ")
    assert cli.resolve_router_model() == "openrouter/auto"


def test_doctor_reports_what_a_call_would_use(monkeypatch):
    """The point of the check is that it cannot disagree with reality."""
    monkeypatch.setenv("NOUGEN_ROUTER_MODEL", "openai/gpt-5.6-luna")
    assert cli.resolve_router_model() == "openai/gpt-5.6-luna"
    monkeypatch.setenv("NOUGEN_ROUTER_MODEL", "moonshotai/kimi-k3")
    assert cli.resolve_router_model() == "moonshotai/kimi-k3"
