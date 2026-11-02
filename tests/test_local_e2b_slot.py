"""NOUGEN_LOCAL_E2B_MODEL lets a node fill the stock e2b slot with its own build."""
import importlib
import json
import urllib.request

from nougen_shards import nougenmsg, vram_gate
from nougen_shards.chat_service import discover_chat_model

SLOT_MODEL = "example/custom-build:e2b"


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


def test_nougenmsg_fallback_uses_slot_but_keeps_node_defaults(monkeypatch):
    monkeypatch.setenv("NOUGEN_LOCAL_E2B_MODEL", SLOT_MODEL)
    pinger = nougenmsg.AgentPinger
    assert pinger._default_ollama_model("somenode") == SLOT_MODEL
    assert pinger._default_ollama_model("whoart") == "gemma4:e2b-qat"


def test_vram_gate_admits_slot_at_stock_size(monkeypatch):
    monkeypatch.setenv("NOUGEN_LOCAL_E2B_MODEL", SLOT_MODEL)
    try:
        gate = importlib.reload(vram_gate)
        assert gate.MEASURED_LOAD_GB[SLOT_MODEL] == gate.MEASURED_LOAD_GB["gemma4:e2b"]
        assert gate.MEASURED_LOAD_GB["nomic-embed-text:latest"] == 0.4
    finally:
        monkeypatch.delenv("NOUGEN_LOCAL_E2B_MODEL")
        importlib.reload(vram_gate)
