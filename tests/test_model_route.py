"""tools/model_route.py: Ollama cloud models are never picked; nvidia: goes to NIM."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import model_route  # noqa: E402


def test_pick_prefers_installed_local_model(monkeypatch):
    monkeypatch.setattr(model_route, "nvidia_available", lambda: False)
    got = model_route.pick(["nvidia:auto", "gemma4:e4b-it-qat"], ["gemma4:e4b-it-qat"])
    assert got == "gemma4:e4b-it-qat"


def test_pick_uses_nvidia_when_key_present(monkeypatch):
    monkeypatch.setattr(model_route, "nvidia_available", lambda: True)
    assert model_route.pick(["nvidia:auto", "gemma4:e4b-it-qat"], ["gemma4:e4b-it-qat"]) == "nvidia:auto"


def test_pick_never_returns_an_unlisted_cloud_tag(monkeypatch):
    monkeypatch.setattr(model_route, "nvidia_available", lambda: False)
    assert model_route.pick(["gemma4:e2b-it-qat"], ["gemma4:31b-cloud"]) is None


def test_chat_nvidia_goes_to_nim(monkeypatch):
    calls = {}

    class Fake:
        def chat_detail(self, model, messages, max_tokens=1024, timeout=None):
            calls["model"] = model
            calls["timeout"] = timeout
            return {"content": "ok", "errors": {}}

    monkeypatch.setattr(model_route, "_client", lambda: Fake())
    assert model_route.chat("nvidia:auto", "hi", "http://unused", timeout=900) == "ok"
    assert calls["model"] is None
    assert calls["timeout"] == 900  # the tool's own limit reaches NVIDIA, not the 60 s default
    model_route.chat("nvidia:nvidia/nemotron-3-ultra-550b-a55b", "hi", "http://unused")
    assert calls["model"] == "nvidia/nemotron-3-ultra-550b-a55b"


def test_chat_nvidia_no_answer_raises(monkeypatch):
    class Fake:
        def chat_detail(self, model, messages, max_tokens=1024, timeout=None):
            return {"content": "", "errors": {"x": "503"}}

    monkeypatch.setattr(model_route, "_client", lambda: Fake())
    with pytest.raises(RuntimeError):
        model_route.chat("nvidia:auto", "hi", "http://unused")


def test_default_fallback_is_nvidia_not_ollama_cloud():
    assert model_route.NVIDIA_DEFAULT.startswith("nvidia:")
    for name in ("arxiv_digest_day", "arxiv_weekly_digest", "atomize_handoffs",
                 "atomize_journal_shards", "dream_deep"):
        src = open(os.path.join(os.path.dirname(__file__), "..", "tools", name + ".py"),
                   encoding="utf-8").read()
        assert "31b-cloud" not in src, name
