"""The authenticated gateway probe must use Python's packaged trust roots."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "tools" / "gateway_probe.py"
    spec = importlib.util.spec_from_file_location("gateway_probe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_post_installs_https_handler_when_ca_bundle_is_available(monkeypatch):
    probe = _module()
    sentinel = object()
    captured = []

    class Opener:
        def open(self, request, timeout):
            raise RuntimeError("stop after opener construction")

    monkeypatch.setattr(probe, "_ssl_context", lambda: sentinel)
    monkeypatch.setattr(
        probe.urllib.request,
        "HTTPSHandler",
        lambda *, context: ("https", context),
    )
    monkeypatch.setattr(
        probe.urllib.request,
        "build_opener",
        lambda *handlers: captured.extend(handlers) or Opener(),
    )

    try:
        probe.post("/register", {})
    except RuntimeError as exc:
        assert str(exc) == "stop after opener construction"

    assert ("https", sentinel) in captured


def test_post_keeps_platform_default_when_certifi_is_unavailable(monkeypatch):
    probe = _module()
    captured = []

    class Opener:
        def open(self, request, timeout):
            raise RuntimeError("stop after opener construction")

    monkeypatch.setattr(probe, "_ssl_context", lambda: None)
    monkeypatch.setattr(
        probe.urllib.request,
        "build_opener",
        lambda *handlers: captured.extend(handlers) or Opener(),
    )

    try:
        probe.post("/register", {})
    except RuntimeError as exc:
        assert str(exc) == "stop after opener construction"

    assert captured == [probe.NoRedirect]
