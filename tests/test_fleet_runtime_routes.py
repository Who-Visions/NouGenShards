"""Fleet node routes follow runtime identity instead of stale literals."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_fleet():
    path = Path(__file__).parents[1] / "tools" / "fleet.py"
    spec = importlib.util.spec_from_file_location("fleet_runtime_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_blade_route_defaults_to_mdns_and_installed_model(monkeypatch):
    monkeypatch.delenv("NOUGEN_BLADE_HOST", raising=False)
    monkeypatch.delenv("NOUGEN_BLADE_MODEL", raising=False)
    fleet = _load_fleet()
    route = next(r for r in fleet.LOCAL_ROUTES if r["name"] == "local-ollama-blade")
    assert route["url"] == "http://blade1tb.local:11434/v1"
    assert route["model"] == "gemma4:e2b"


def test_blade_route_allows_runtime_overrides(monkeypatch):
    monkeypatch.setenv("NOUGEN_BLADE_HOST", "blade.test")
    monkeypatch.setenv("NOUGEN_BLADE_MODEL", "installed:test")
    fleet = _load_fleet()
    route = next(r for r in fleet.LOCAL_ROUTES if r["name"] == "local-ollama-blade")
    assert route["url"] == "http://blade.test:11434/v1"
    assert route["model"] == "installed:test"
