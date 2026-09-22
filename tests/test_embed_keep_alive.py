"""The embedder stays resident between recalls, and query embedding survives a cold load.

Before 2026-09-14 neither embed call sent keep_alive, so ollama evicted the
embedder after its 5-minute default, and the 3 s query budget was shorter than
a cold load. Most recalls after a quiet stretch silently ran keyword-only.
"""
import json
import urllib.request

from nougen_shards import embedding_backfill as eb


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture(monkeypatch, payload):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["body"] = json.loads(req.data.decode("utf-8"))
        seen["timeout"] = timeout
        return _Resp(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_embed_sends_default_keep_alive(monkeypatch):
    monkeypatch.delenv("NOUGEN_EMBED_KEEP_ALIVE", raising=False)
    seen = _capture(monkeypatch, {"embeddings": [[0.1, 0.2]]})
    assert eb.embed("hello", "nomic-embed-text", timeout=5) == [0.1, 0.2]
    assert seen["body"]["keep_alive"] == "30m"
    assert seen["body"]["model"] == "nomic-embed-text"


def test_embed_many_sends_keep_alive(monkeypatch):
    monkeypatch.setenv("NOUGEN_EMBED_KEEP_ALIVE", "2h")
    seen = _capture(monkeypatch, {"embeddings": [[1.0], [2.0]]})
    assert eb.embed_many(["a", "b"], "nomic-embed-text") == [[1.0], [2.0]]
    assert seen["body"]["keep_alive"] == "2h"


def test_keep_alive_accepts_integer_seconds(monkeypatch):
    monkeypatch.setenv("NOUGEN_EMBED_KEEP_ALIVE", "-1")
    assert eb._keep_alive() == -1
    monkeypatch.setenv("NOUGEN_EMBED_KEEP_ALIVE", "900")
    assert eb._keep_alive() == 900
    monkeypatch.setenv("NOUGEN_EMBED_KEEP_ALIVE", "  ")
    assert eb._keep_alive() == "30m"


def test_query_embedding_gets_room_for_a_cold_load(monkeypatch):
    from nougen_shards import core

    monkeypatch.delenv("NOUGEN_QUERY_EMBED_TIMEOUT", raising=False)
    monkeypatch.delenv("NOUGEN_EMBED_TIMEOUT", raising=False)
    seen = {}

    def fake_embed(text, model, timeout=None):
        seen["timeout"] = timeout
        return [3.0, 4.0]

    monkeypatch.setattr(eb, "embed", fake_embed)
    vec = core._embed_query("relay legs auto close")
    assert seen["timeout"] == 6.0
    assert vec is not None and abs(float((vec ** 2).sum()) - 1.0) < 1e-6
