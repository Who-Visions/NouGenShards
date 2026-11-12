"""Unit tests for tools/davos_cloud_chat.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import davos_cloud_chat as dcc


def test_resolve_api_key_prefers_env_and_raises_generic_error(monkeypatch):
    monkeypatch.delenv("NOUGEN_OLLAMA_CLOUD_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        dcc._resolve_api_key()
    msg = str(exc.value)
    assert "NOUGEN_OLLAMA_CLOUD_KEY" in msg
    assert "OLLAMA_API_KEY" in msg
    assert "keyfor.py" not in msg

    monkeypatch.setenv("OLLAMA_API_KEY", "fallback-key")
    assert dcc._resolve_api_key() == "fallback-key"

    monkeypatch.setenv("NOUGEN_OLLAMA_CLOUD_KEY", "primary-key")
    assert dcc._resolve_api_key() == "primary-key"


def test_cloud_chat_fn_and_chat_loop(monkeypatch):
    monkeypatch.setenv("NOUGEN_OLLAMA_CLOUD_KEY", "test-key")
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"message": {"role": "assistant", "content": "Vault looks clean."}}).encode("utf-8")

    def fake_urlopen(req, timeout=60):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setattr(dcc.urllib.request, "urlopen", fake_urlopen)
    reply, calls = dcc.chat("Check status")
    assert reply == "Vault looks clean."
    assert calls == []
    assert captured["url"] == dcc.OLLAMA_CHAT_URL
    assert captured["auth"] == "Bearer test-key"
    assert isinstance(captured["body"].get("tools"), list)
