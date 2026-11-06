"""NOUGEN_LOCAL_E2B_MODEL lets a node fill the stock e2b slot with its own build."""
import importlib
import json
import urllib.request

import pytest

from nougen_shards import nougenmsg, ollama_host, vram_gate
from nougen_shards.chat_service import chat, discover_chat_model

SLOT_MODEL = "example/custom-build:e2b"
LIVE_URL = "http://127.0.0.1:11999"


def _serve_tags(monkeypatch, names):
    class Tags:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size):
            return json.dumps({"models": [{"name": n} for n in names]}).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: Tags())


def test_chat_discovers_slot_model(monkeypatch):
    monkeypatch.setenv("NOUGEN_LOCAL_E2B_MODEL", SLOT_MODEL)
    _serve_tags(monkeypatch, [SLOT_MODEL])
    assert discover_chat_model() == SLOT_MODEL


def test_chat_default_without_slot_is_stock(monkeypatch):
    monkeypatch.delenv("NOUGEN_LOCAL_E2B_MODEL", raising=False)
    _serve_tags(monkeypatch, ["gemma4:e2b"])
    assert discover_chat_model() == "gemma4:e2b"


def test_chat_allows_configured_slot_model(monkeypatch):
    monkeypatch.setenv("NOUGEN_LOCAL_E2B_MODEL", SLOT_MODEL)
    assert discover_chat_model(SLOT_MODEL) == SLOT_MODEL


def test_nougenmsg_slot_applies_only_to_the_local_node(monkeypatch):
    monkeypatch.setenv("NOUGEN_LOCAL_E2B_MODEL", SLOT_MODEL)
    monkeypatch.setattr(nougenmsg, "get_current_node", lambda: "thisnode")
    pinger = nougenmsg.AgentPinger
    assert pinger._default_ollama_model("local") == SLOT_MODEL
    assert pinger._default_ollama_model("thisnode") == SLOT_MODEL
    assert pinger._default_ollama_model("othernode") == pinger._OLLAMA_FALLBACK
    assert pinger._default_ollama_model("whoart") == "gemma4:e2b-qat"


def _capture_urls(monkeypatch, body):
    seen = []

    class Reply:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size=-1): return json.dumps(body).encode()

    def fake_urlopen(request, timeout=None):
        seen.append(getattr(request, "full_url", request))
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def _live_at(monkeypatch, url):
    monkeypatch.setattr(ollama_host, "discover_ollama_url", lambda **kwargs: url)


def test_vram_gate_dials_the_discovered_port(monkeypatch):
    seen = _capture_urls(monkeypatch, {"models": []})
    _live_at(monkeypatch, LIVE_URL)
    assert vram_gate._residents() == []
    assert seen == [f"{LIVE_URL}/api/ps"]


def test_vram_gate_falls_back_when_nothing_answers(monkeypatch):
    seen = _capture_urls(monkeypatch, {"models": []})
    _live_at(monkeypatch, None)
    monkeypatch.setenv("NOUGEN_OLLAMA_URL", "http://127.0.0.1:1")
    vram_gate._residents()
    assert seen == ["http://127.0.0.1:1/api/ps"]


def test_chat_discovery_dials_the_discovered_port(monkeypatch):
    monkeypatch.setenv("NOUGEN_LOCAL_E2B_MODEL", SLOT_MODEL)
    monkeypatch.delenv("NOUGEN_CHAT_MODEL", raising=False)
    seen = _capture_urls(monkeypatch, {"models": [{"name": SLOT_MODEL}]})
    _live_at(monkeypatch, LIVE_URL)
    assert discover_chat_model() == SLOT_MODEL
    assert seen == [f"{LIVE_URL}/api/tags"]


def test_chat_generation_dials_the_discovered_port(monkeypatch):
    monkeypatch.delenv("NOUGEN_CHAT_MODEL", raising=False)
    seen = _capture_urls(monkeypatch, {"models": [{"name": "gemma4:e2b"}],
                                       "message": {"content": "hi there"}})
    _live_at(monkeypatch, LIVE_URL)
    chat({"messages": [{"role": "user", "content": "hello"}]})
    assert f"{LIVE_URL}/api/chat" in seen
    assert not [u for u in seen if ":11434" in u]


@pytest.mark.parametrize("raw, expected", [
    (None, 7.51), ("", 7.51), ("1.59", 1.59),
    ("garbage", 7.51), ("0", 7.51), ("-2", 7.51), ("nan", 7.51), ("inf", 7.51),
])
def test_vram_gate_slot_size_is_measured_or_stock(monkeypatch, raw, expected):
    monkeypatch.setenv("NOUGEN_LOCAL_E2B_MODEL", SLOT_MODEL)
    if raw is None:
        monkeypatch.delenv("NOUGEN_LOCAL_E2B_LOAD_GB", raising=False)
    else:
        monkeypatch.setenv("NOUGEN_LOCAL_E2B_LOAD_GB", raw)
    try:
        gate = importlib.reload(vram_gate)
        assert gate.MEASURED_LOAD_GB[SLOT_MODEL] == expected
        assert gate.MEASURED_LOAD_GB["gemma4:e2b"] == 7.51
        assert gate.MEASURED_LOAD_GB["nomic-embed-text:latest"] == 0.4
    finally:
        monkeypatch.delenv("NOUGEN_LOCAL_E2B_MODEL")
        monkeypatch.delenv("NOUGEN_LOCAL_E2B_LOAD_GB", raising=False)
        importlib.reload(vram_gate)
